"""Shared read/query helpers used by Flask routes and the MCP server."""

from __future__ import annotations

import datetime as _dt
from datetime import date

KNOCKOUT_ORDER = ["final", "semi_final", "quarter_final", "round_of_16", "round_of_32"]


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
    limit = min(limit, 60)
    pos_filter = (position or "").upper() or None
    with conn.cursor() as cur:
        sql = (
            "SELECT DISTINCT ON (p.id) "
            "  p.name, t.name AS team, pa.position, "
            "  tr.rating AS team_rating, p.date_of_birth "
            "FROM player_affiliations pa "
            "JOIN players p ON p.id = pa.player_id "
            "JOIN teams t ON t.id = pa.team_id "
            "JOIN team_ratings tr ON tr.team_id = t.id "
            "WHERE pa.ended_on IS NULL "
            "  AND EXISTS ("
            "    SELECT 1 FROM matches m "
            "    JOIN competition_editions e ON e.id = m.edition_id "
            "    JOIN competitions c ON c.id = e.competition_id "
            "    WHERE c.code = %s "
            "      AND (m.home_team_id = t.id OR m.away_team_id = t.id)"
            "  ) "
        )
        params: list = [comp]
        if pos_filter:
            sql += " AND pa.position = %s "
            params.append(pos_filter)
        sql += " ORDER BY p.id, tr.rating DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()

    standouts = []
    today = date.today()
    for name, team, pos, rating, dob in rows:
        age = None
        if dob:
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        standouts.append({
            "name": name, "team": team, "position": pos or "?",
            "team_rating": round(rating), "age": age,
        })
    standouts.sort(key=lambda x: (-x["team_rating"], x["name"]))
    return standouts[:limit]


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
