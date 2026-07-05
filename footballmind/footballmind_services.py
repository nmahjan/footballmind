"""Shared read/query helpers used by Flask routes and the MCP server."""

from __future__ import annotations

import datetime as _dt
from datetime import date

KNOCKOUT_ORDER = ["final", "semi_final", "quarter_final", "round_of_16", "round_of_32"]
POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "?": 9}
_POS_WEIGHT = {"FWD": 1.0, "MID": 0.9, "DEF": 0.75, "GK": 0.65, "?": 0.8}
_STANDOUT_TEAM_CAP = 2          # max players per team in one standouts list


def normalize_position(raw: str | None) -> str | None:
    """Map football-data.org role strings to GK / DEF / MID / FWD."""
    if not raw:
        return None
    s = raw.lower()
    if "goal" in s:
        return "GK"
    if "def" in s or "back" in s:
        return "DEF"
    if "mid" in s:
        return "MID"
    if "off" in s or "forward" in s or "attack" in s or "wing" in s:
        return "FWD"
    return None


def _player_age(dob) -> int | None:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _row_player(name, team, pos, rating, dob, nationality=None,
                goals=None, assists=None, appearances=None,
                standout_rating=None, club_team=None):
    row = {
        "name": name,
        "team": team,
        "position": pos or "?",
        "team_rating": round(rating) if rating is not None else None,
        "age": _player_age(dob),
        "nationality": nationality,
    }
    if goals is not None:
        row["goals"] = goals
    if assists is not None:
        row["assists"] = assists
    if appearances is not None:
        row["appearances"] = appearances
    if standout_rating is not None:
        row["standout_rating"] = standout_rating
    if club_team:
        row["club_team"] = club_team
    return row


def _affil_kind_for_comp(conn, comp: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT type FROM competitions WHERE code = %s", (comp,))
        row = cur.fetchone()
    return "national" if row and row[0] == "international" else "club"


def _compute_standout_rating(team_rating, goals, assists, apps, position) -> float:
    """0–100 blend: national/club team strength + best club season form."""
    elo_n = min(1.0, max(0.0, ((team_rating or 1500) - 1400) / 450))
    form_n = min(1.0, ((goals or 0) + (assists or 0) * 0.6) / 22)
    apps_n = min(1.0, (apps or 0) / 35)
    pos_n = _POS_WEIGHT.get((position or "?").upper(), 0.8)
    return round(100 * (0.35 * elo_n + 0.45 * form_n + 0.12 * apps_n + 0.08 * pos_n), 1)


def _has_comp_scorers(conn, edition_id: int | None) -> bool:
    if not edition_id:
        return False
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM player_edition_stats WHERE edition_id = %s AND goals > 0 LIMIT 1",
            (edition_id,))
        return cur.fetchone() is not None


def _cap_players_per_team(players: list, cap: int = _STANDOUT_TEAM_CAP) -> list:
    """Avoid one nation/club filling the whole grid (e.g. four Spain players)."""
    counts: dict[str, int] = {}
    out = []
    for p in players:
        team = p.get("team") or "?"
        if counts.get(team, 0) >= cap:
            continue
        counts[team] = counts.get(team, 0) + 1
        out.append(p)
    return out


def _edition_id_for_comp(conn, comp: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id FROM competition_editions e "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = %s "
            "ORDER BY e.start_date DESC NULLS LAST LIMIT 1",
            (comp,))
        row = cur.fetchone()
    return row[0] if row else None


def compute_standings(rows):
    """rows: iterable of (home, away, home_goals, away_goals). Returns sorted table."""
    tbl = {}

    def slot(t):
        return tbl.setdefault(t, {"team": t, "P": 0, "W": 0, "D": 0,
                                  "L": 0, "GF": 0, "GA": 0, "Pts": 0})
    for home, away, hg, ag in rows:
        h, a = slot(home), slot(away)
        h["P"] += 1; a["P"] += 1
        h["GF"] += hg; h["GA"] += ag; a["GF"] += ag; a["GA"] += hg
        if hg > ag:
            h["W"] += 1; h["Pts"] += 3; a["L"] += 1
        elif hg < ag:
            a["W"] += 1; a["Pts"] += 3; h["L"] += 1
        else:
            h["D"] += 1; a["D"] += 1; h["Pts"] += 1; a["Pts"] += 1
    table = list(tbl.values())
    for t in table:
        t["GD"] = t["GF"] - t["GA"]
    table.sort(key=lambda t: (t["Pts"], t["GD"], t["GF"]), reverse=True)
    for i, t in enumerate(table, 1):
        t["rank"] = i
    return table


def get_standings(conn, comp_code: str = "PL", season: str | None = None) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT th.name, ta.name, m.home_goals, m.away_goals FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE c.code = %s AND m.home_goals IS NOT NULL "
            "  AND (%s::text IS NULL OR e.season = %s)", (comp_code, season, season))
        return compute_standings(cur.fetchall())


def get_fixtures(conn, comp: str = "WC", limit: int = 16) -> list:
    limit = min(limit, 64)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT th.name AS home, ta.name AS away, "
            "       m.match_date, m.stage, m.home_goals, m.away_goals "
            "FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE c.code = %s "
            "  AND m.match_date >= now() - interval '3 hours' "
            "ORDER BY m.match_date ASC LIMIT %s",
            (comp, limit))
        cols = [d[0] for d in cur.description]
        fixtures = []
        now = _dt.datetime.now(_dt.timezone.utc)
        for row in cur.fetchall():
            f = dict(zip(cols, row))
            if f.get("match_date") and f.get("home_goals") is None:
                kick_off = f["match_date"]
                if hasattr(kick_off, "tzinfo") and kick_off.tzinfo is None:
                    kick_off = kick_off.replace(tzinfo=_dt.timezone.utc)
                elapsed = (now - kick_off).total_seconds() / 60
                f["live"] = 0 < elapsed < 115
            else:
                f["live"] = False
            if f.get("match_date"):
                f["match_date"] = f["match_date"].isoformat()
            fixtures.append(f)
    return fixtures


def get_groups(conn, comp: str = "WC") -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT g, team, SUM(W) W, SUM(D) D, SUM(L) L, "
            "       SUM(GF) GF, SUM(GA) GA, SUM(Pts) Pts "
            "FROM ("
            "  SELECT m.group_name g, th.name team,"
            "    COUNT(*) FILTER (WHERE m.home_goals > m.away_goals) W,"
            "    COUNT(*) FILTER (WHERE m.home_goals = m.away_goals) D,"
            "    COUNT(*) FILTER (WHERE m.home_goals < m.away_goals) L,"
            "    COALESCE(SUM(m.home_goals),0) GF, COALESCE(SUM(m.away_goals),0) GA,"
            "    SUM(CASE WHEN m.home_goals > m.away_goals THEN 3"
            "             WHEN m.home_goals = m.away_goals THEN 1 ELSE 0 END) Pts"
            "  FROM matches m"
            "  JOIN competition_editions e ON e.id = m.edition_id"
            "  JOIN competitions c ON c.id = e.competition_id"
            "  JOIN teams th ON th.id = m.home_team_id"
            "  WHERE c.code = %s AND m.home_goals IS NOT NULL AND m.group_name IS NOT NULL"
            "  GROUP BY m.group_name, th.name"
            "  UNION ALL"
            "  SELECT m.group_name, ta.name,"
            "    COUNT(*) FILTER (WHERE m.away_goals > m.home_goals),"
            "    COUNT(*) FILTER (WHERE m.away_goals = m.home_goals),"
            "    COUNT(*) FILTER (WHERE m.away_goals < m.home_goals),"
            "    COALESCE(SUM(m.away_goals),0), COALESCE(SUM(m.home_goals),0),"
            "    SUM(CASE WHEN m.away_goals > m.home_goals THEN 3"
            "             WHEN m.away_goals = m.home_goals THEN 1 ELSE 0 END)"
            "  FROM matches m"
            "  JOIN competition_editions e ON e.id = m.edition_id"
            "  JOIN competitions c ON c.id = e.competition_id"
            "  JOIN teams ta ON ta.id = m.away_team_id"
            "  WHERE c.code = %s AND m.home_goals IS NOT NULL AND m.group_name IS NOT NULL"
            "  GROUP BY m.group_name, ta.name"
            ") s GROUP BY g, team ORDER BY g, Pts DESC, (SUM(GF)-SUM(GA)) DESC",
            (comp, comp))
        rows = cur.fetchall()

    groups = {}
    for g, team, W, D, L, GF, GA, Pts in rows:
        groups.setdefault(g, []).append({
            "team": team, "W": W, "D": D, "L": L,
            "GD": GF - GA, "GF": GF, "GA": GA, "Pts": Pts,
        })
    return groups


def get_rankings(conn, comp: str = "WC", limit: int = 48) -> list:
    limit = min(limit, 100)
    with conn.cursor() as cur:
        if comp:
            cur.execute(
                "SELECT DISTINCT t.name, tr.rating "
                "FROM team_ratings tr "
                "JOIN teams t ON t.id = tr.team_id "
                "WHERE t.type = 'national' "
                "  AND EXISTS ("
                "    SELECT 1 FROM matches m "
                "    JOIN competition_editions e ON e.id = m.edition_id "
                "    JOIN competitions c ON c.id = e.competition_id "
                "    WHERE c.code = %s "
                "      AND (m.home_team_id = t.id OR m.away_team_id = t.id)"
                "  ) "
                "ORDER BY tr.rating DESC LIMIT %s", (comp, limit))
        else:
            cur.execute(
                "SELECT t.name, tr.rating FROM team_ratings tr "
                "JOIN teams t ON t.id = tr.team_id "
                "WHERE t.type = 'national' "
                "ORDER BY tr.rating DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    if not rows:
        return []
    max_r, min_r = rows[0][1], rows[-1][1] if len(rows) > 1 else rows[0][1]
    span = max(max_r - min_r, 1)
    return [
        {"rank": i + 1, "team": name, "rating": round(rating),
         "strength": round((rating - min_r) / span, 3)}
        for i, (name, rating) in enumerate(rows)
    ]


def get_standouts(conn, comp: str = "WC", position: str | None = None, limit: int = 20) -> list:
    """Standout players ranked by comp goals when available, else composite rating.

    Composite rating (WC / pre-tournament): team Elo + best club-season G/A,
    filtered to national squads only. Caps players per team for variety.
    """
    limit = min(limit, 60)
    pos_filter = (position or "").upper() or None
    edition_id = _edition_id_for_comp(conn, comp)
    kind = _affil_kind_for_comp(conn, comp)

    if edition_id and _has_comp_scorers(conn, edition_id):
        with conn.cursor() as cur:
            sql = (
                "SELECT p.name, t.name, p.position, tr.rating, p.birth_date, "
                "       co.name, pes.goals, pes.assists, pes.appearances "
                "FROM player_edition_stats pes "
                "JOIN players p ON p.id = pes.player_id "
                "LEFT JOIN teams t ON t.id = pes.team_id "
                "LEFT JOIN team_ratings tr ON tr.team_id = t.id "
                "LEFT JOIN countries co ON co.id = p.nationality "
                "WHERE pes.edition_id = %s "
            )
            params: list = [edition_id]
            if pos_filter:
                sql += " AND p.position = %s "
                params.append(pos_filter)
            sql += " ORDER BY pes.goals DESC, pes.assists DESC, p.name LIMIT %s"
            params.append(limit * 2)
            cur.execute(sql, params)
            rows = cur.fetchall()

        standouts = []
        for name, team, pos, rating, dob, nat, goals, ast, apps in rows:
            sr = _compute_standout_rating(rating, goals, ast, apps, pos)
            standouts.append(_row_player(
                name, team, pos, rating, dob, nat, goals, ast, apps, sr))
        return _cap_players_per_team(standouts)[:limit]

    with conn.cursor() as cur:
        sql = (
            "SELECT p.id, p.name, t.name, p.position, tr.rating, p.birth_date, "
            "       co.name, COALESCE(cs.goals, 0), COALESCE(cs.assists, 0), "
            "       COALESCE(cs.appearances, 0), cs.club_team "
            "FROM player_affiliations pa "
            "JOIN players p ON p.id = pa.player_id "
            "JOIN teams t ON t.id = pa.team_id "
            "LEFT JOIN team_ratings tr ON tr.team_id = t.id "
            "LEFT JOIN countries co ON co.id = p.nationality "
            "LEFT JOIN LATERAL ("
            "  SELECT pes.goals, pes.assists, pes.appearances, t2.name AS club_team "
            "  FROM player_edition_stats pes "
            "  JOIN teams t2 ON t2.id = pes.team_id "
            "  WHERE pes.player_id = p.id "
            "  ORDER BY (pes.goals + pes.assists * 0.6) DESC, pes.appearances DESC "
            "  LIMIT 1"
            ") cs ON true "
            "WHERE pa.end_date IS NULL AND pa.kind = %s "
            "  AND EXISTS ("
            "    SELECT 1 FROM matches m "
            "    JOIN competition_editions e ON e.id = m.edition_id "
            "    JOIN competitions c ON c.id = e.competition_id "
            "    WHERE c.code = %s "
            "      AND (m.home_team_id = t.id OR m.away_team_id = t.id)"
            "  ) "
        )
        params: list = [kind, comp]
        if pos_filter:
            sql += " AND p.position = %s "
            params.append(pos_filter)
        sql += " ORDER BY p.id"
        cur.execute(sql, params)
        rows = cur.fetchall()

    standouts = []
    for _pid, name, team, pos, rating, dob, nat, goals, ast, apps, club in rows:
        sr = _compute_standout_rating(rating, goals, ast, apps, pos)
        standouts.append(_row_player(
            name, team, pos, rating, dob, nat, goals or None, ast or None,
            apps or None, sr, club))

    standouts.sort(key=lambda x: (-(x.get("standout_rating") or 0), x["name"]))
    return _cap_players_per_team(standouts)[:limit]


def search_players(conn, query: str, comp: str | None = None, limit: int = 15) -> list:
    limit = min(limit, 30)
    term = (query or "").strip()
    if len(term) < 2:
        return []
    with conn.cursor() as cur:
        sql = (
            "SELECT DISTINCT ON (p.id) "
            "  p.name, t.name AS team, p.position, "
            "  tr.rating AS team_rating, p.birth_date, co.name AS nationality "
            "FROM players p "
            "JOIN player_affiliations pa ON pa.player_id = p.id AND pa.end_date IS NULL "
            "JOIN teams t ON t.id = pa.team_id "
            "LEFT JOIN team_ratings tr ON tr.team_id = t.id "
            "LEFT JOIN countries co ON co.id = p.nationality "
            "WHERE p.name ILIKE %s "
        )
        params: list = [f"%{term}%"]
        if comp:
            kind = _affil_kind_for_comp(conn, comp)
            sql += " AND pa.kind = %s "
            params.append(kind)
            sql += (
                " AND EXISTS ("
                "   SELECT 1 FROM matches m "
                "   JOIN competition_editions e ON e.id = m.edition_id "
                "   JOIN competitions c ON c.id = e.competition_id "
                "   WHERE c.code = %s "
                "     AND (m.home_team_id = t.id OR m.away_team_id = t.id)"
                " ) "
            )
            params.append(comp)
        sql += " ORDER BY p.id, COALESCE(tr.rating, 0) DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
    results = [_row_player(*row) for row in rows]
    results.sort(key=lambda x: (-(x["team_rating"] or 0), x["name"]))
    return results


def get_teams_in_comp(conn, comp: str = "WC") -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT t.name FROM teams t "
            "JOIN matches m ON m.home_team_id = t.id OR m.away_team_id = t.id "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = %s "
            "ORDER BY t.name",
            (comp,))
        return [r[0] for r in cur.fetchall()]


def get_team_squad(conn, team_name: str, comp: str | None = None) -> dict:
    from footballmind_mcp_predict import _resolve_team

    with conn.cursor() as cur:
        team_id, team_type = _resolve_team(cur, team_name)
        cur.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
        resolved_name = cur.fetchone()[0]

        sql = (
            "SELECT p.name, p.position, pa.shirt_number, p.birth_date, co.name "
            "FROM player_affiliations pa "
            "JOIN players p ON p.id = pa.player_id "
            "LEFT JOIN countries co ON co.id = p.nationality "
            "WHERE pa.team_id = %s AND pa.end_date IS NULL "
        )
        params: list = [team_id]
        if comp:
            sql += (
                " AND EXISTS ("
                "   SELECT 1 FROM matches m "
                "   JOIN competition_editions e ON e.id = m.edition_id "
                "   JOIN competitions c ON c.id = e.competition_id "
                "   WHERE c.code = %s "
                "     AND (m.home_team_id = pa.team_id OR m.away_team_id = pa.team_id)"
                " ) "
            )
            params.append(comp)
        sql += " ORDER BY p.name"
        cur.execute(sql, params)
        rows = cur.fetchall()

        cur.execute(
            "SELECT rating FROM team_ratings WHERE team_id = %s", (team_id,))
        rating_row = cur.fetchone()
        team_rating = round(rating_row[0]) if rating_row else None

    squad = []
    for name, pos, shirt, dob, nationality in rows:
        squad.append({
            "name": name,
            "position": pos or "?",
            "shirt_number": shirt,
            "age": _player_age(dob),
            "nationality": nationality,
        })
    squad.sort(key=lambda p: (POS_ORDER.get(p["position"], 9), p["name"]))

    by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": [], "?": []}
    for p in squad:
        by_pos.setdefault(p["position"], []).append(p)

    return {
        "team": resolved_name,
        "team_type": team_type,
        "team_rating": team_rating,
        "comp": comp,
        "squad_size": len(squad),
        "squad": squad,
        "by_position": {k: v for k, v in by_pos.items() if v},
    }


def get_player_profile(conn, name: str, comp: str | None = None) -> dict | None:
    base = search_players(conn, name, comp, limit=5)
    if not base:
        return None
    exact = [h for h in base if h["name"].lower() == name.strip().lower()]
    profile = dict(exact[0] if exact else base[0])
    if comp:
        stats = get_player_comp_stats(conn, profile["name"], comp)
        if stats:
            profile.update(stats)
    return profile


def get_player_comp_stats(conn, name: str, comp: str) -> dict | None:
    edition_id = _edition_id_for_comp(conn, comp)
    if not edition_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pes.goals, pes.assists, pes.appearances, pes.penalties, t.name "
            "FROM player_edition_stats pes "
            "JOIN players p ON p.id = pes.player_id "
            "LEFT JOIN teams t ON t.id = pes.team_id "
            "WHERE pes.edition_id = %s AND p.name ILIKE %s "
            "ORDER BY pes.goals DESC LIMIT 1",
            (edition_id, name.strip()))
        row = cur.fetchone()
    if not row:
        return None
    goals, assists, apps, pens, team = row
    return {
        "goals": goals, "assists": assists, "appearances": apps,
        "penalties": pens, "stats_team": team, "comp": comp,
    }


def get_top_scorers(conn, comp: str = "PL", limit: int = 20) -> list:
    limit = min(limit, 50)
    edition_id = _edition_id_for_comp(conn, comp)
    if not edition_id:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.name, t.name, p.position, pes.goals, pes.assists, "
            "       pes.appearances, pes.penalties, p.birth_date, co.name "
            "FROM player_edition_stats pes "
            "JOIN players p ON p.id = pes.player_id "
            "LEFT JOIN teams t ON t.id = pes.team_id "
            "LEFT JOIN countries co ON co.id = p.nationality "
            "WHERE pes.edition_id = %s "
            "ORDER BY pes.goals DESC, pes.assists DESC, p.name "
            "LIMIT %s",
            (edition_id, limit))
        rows = cur.fetchall()

    scorers = []
    for i, (name, team, pos, goals, assists, apps, pens, dob, nat) in enumerate(rows, 1):
        scorers.append({
            "rank": i,
            "name": name,
            "team": team,
            "position": pos or "?",
            "goals": goals,
            "assists": assists,
            "appearances": apps,
            "penalties": pens,
            "age": _player_age(dob),
            "nationality": nat,
        })
    return scorers


def get_match_lineup(conn, home: str, away: str, comp: str | None = None) -> dict | None:
    from footballmind_mcp_predict import _resolve_team

    with conn.cursor() as cur:
        home_id, _ = _resolve_team(cur, home)
        away_id, _ = _resolve_team(cur, away)
        sql = (
            "SELECT m.id, m.match_date, m.home_goals, m.away_goals, "
            "       th.name, ta.name "
            "FROM matches m "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE m.home_team_id = %s AND m.away_team_id = %s "
            "  AND m.home_goals IS NOT NULL "
        )
        params: list = [home_id, away_id]
        if comp:
            sql += " AND c.code = %s "
            params.append(comp)
        sql += " ORDER BY m.match_date DESC LIMIT 1"
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        match_id, match_date, hg, ag, home_name, away_name = row

        cur.execute(
            "SELECT t.name, mtl.formation FROM match_team_lineups mtl "
            "JOIN teams t ON t.id = mtl.team_id "
            "WHERE mtl.match_id = %s",
            (match_id,))
        formations = {name: form for name, form in cur.fetchall()}

        cur.execute(
            "SELECT t.name, p.name, mlp.role, mlp.position, mlp.shirt_number "
            "FROM match_lineup_players mlp "
            "JOIN teams t ON t.id = mlp.team_id "
            "JOIN players p ON p.id = mlp.player_id "
            "WHERE mlp.match_id = %s "
            "ORDER BY t.name, "
            "  CASE mlp.role WHEN 'starter' THEN 0 WHEN 'sub_in' THEN 1 ELSE 2 END, "
            "  p.name",
            (match_id,))
        lineup_rows = cur.fetchall()

    teams_out = {}
    for team_name, pname, role, pos, shirt in lineup_rows:
        bucket = teams_out.setdefault(team_name, {"formation": formations.get(team_name),
                                                  "starters": [], "bench": []})
        entry = {"name": pname, "position": pos or "?", "shirt_number": shirt}
        if role == "starter":
            bucket["starters"].append(entry)
        else:
            bucket["bench"].append(entry)

    return {
        "home": home_name,
        "away": away_name,
        "score": f"{hg}-{ag}",
        "match_date": match_date.isoformat() if match_date else None,
        "formations": formations,
        "lineups": teams_out,
        "has_lineup_data": bool(lineup_rows),
    }


def get_team_formations(conn, team_name: str, comp: str | None = None, limit: int = 5) -> list:
    from footballmind_mcp_predict import _resolve_team

    with conn.cursor() as cur:
        team_id, _ = _resolve_team(cur, team_name)
        sql = (
            "SELECT m.match_date, th.name, ta.name, m.home_goals, m.away_goals, "
            "       mtl.formation, (m.home_team_id = %s) AS was_home "
            "FROM match_team_lineups mtl "
            "JOIN matches m ON m.id = mtl.match_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE mtl.team_id = %s AND mtl.formation IS NOT NULL "
        )
        params: list = [team_id, team_id]
        if comp:
            sql += " AND c.code = %s "
            params.append(comp)
        sql += " ORDER BY m.match_date DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()

    out = []
    for match_date, home, away, hg, ag, formation, was_home in rows:
        opponent = away if was_home else home
        out.append({
            "match_date": match_date.isoformat() if match_date else None,
            "opponent": opponent,
            "score": f"{hg}-{ag}",
            "formation": formation,
            "venue": "home" if was_home else "away",
        })
    return out


def get_bracket(conn, comp: str = "WC") -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.stage, th.name AS home, ta.name AS away, "
            "       m.match_date, m.home_goals, m.away_goals "
            "FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE c.code = %s "
            "  AND m.stage NOT IN ('regular_season', 'group', 'third_place') "
            "ORDER BY m.match_date ASC NULLS LAST",
            (comp,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    rounds = {s: [] for s in KNOCKOUT_ORDER}
    for row in rows:
        f = dict(zip(cols, row))
        if f.get("match_date"):
            f["match_date"] = f["match_date"].isoformat()
        stage = f["stage"]
        if stage in rounds:
            rounds[stage].append(f)
    return [{"round": s, "matches": rounds[s]} for s in KNOCKOUT_ORDER if rounds[s]]
