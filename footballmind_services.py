"""Shared read/query helpers used by Flask routes and the MCP server."""

from __future__ import annotations

import datetime as _dt
from datetime import date

KNOCKOUT_ORDER = ["final", "semi_final", "quarter_final", "round_of_16", "round_of_32"]
POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "?": 9}

SUPPORTED_COMP_CODES = frozenset({"PL", "PD", "BL1", "SA", "FL1", "CL", "DED", "WC", "MLS"})
COMP_LABELS = {
    "PL": "Premier League", "PD": "La Liga", "BL1": "Bundesliga",
    "SA": "Serie A", "FL1": "Ligue 1", "CL": "Champions League",
    "DED": "Eredivisie", "WC": "World Cup", "MLS": "MLS",
}
# Longest phrases first so "champions league" beats "liga".
COMP_PHRASES = (
    ("champions league", "CL"), ("premier league", "PL"), ("la liga", "PD"),
    ("laliga", "PD"), ("primera division", "PD"), ("primera división", "PD"),
    ("bundesliga", "BL1"), ("serie a", "SA"), ("ligue 1", "FL1"),
    ("eredivisie", "DED"), ("world cup", "WC"), ("mls", "MLS"),
    ("major league soccer", "MLS"),
)
_POS_WEIGHT = {"FWD": 1.0, "MID": 0.9, "DEF": 0.75, "GK": 0.65, "?": 0.8}
_STANDOUT_TEAM_CAP = 2          # max players per team in one standouts list
_LIVE_WINDOW_MINUTES = 115


def _as_utc(dt: _dt.datetime | None) -> _dt.datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def is_finished_match(
    home_goals: int | None,
    away_goals: int | None,
    match_date: _dt.datetime | None,
    *,
    now: _dt.datetime | None = None,
) -> bool:
    """True when a fixture has a final score and is past the live window."""
    if home_goals is None or away_goals is None or match_date is None:
        return False
    kick_off = _as_utc(match_date)
    if kick_off is None:
        return False
    now = now or _dt.datetime.now(_dt.timezone.utc)
    elapsed = (now - kick_off).total_seconds() / 60
    return elapsed >= _LIVE_WINDOW_MINUTES


def normalize_position(raw: str | None) -> str | None:
    """Map football-data.org role strings to GK / DEF / MID / FWD."""
    if not raw:
        return None
    s = raw.lower().strip()
    if s in ("gk", "goalkeeper", "goal keeper", "goal-keeper"):
        return "GK"
    if "goalkeeper" in s or "goal keeper" in s or "goal-keeper" in s:
        return "GK"
    if s in ("def", "defence", "defense"):
        return "DEF"
    if s in ("mid", "midfield"):
        return "MID"
    if s in ("fwd", "forward", "offence", "offense"):
        return "FWD"
    if "mid" in s:
        return "MID"
    if "def" in s or "back" in s:
        return "DEF"
    if "off" in s or "forward" in s or "attack" in s or "wing" in s:
        return "FWD"
    return None


def _coerce_standout_position(
    pos: str | None,
    goals: int | None = None,
    assists: int | None = None,
    saves: int | None = None,
) -> str:
    """Normalize DB/lineup position; never default unknown outfielders to GK."""
    norm = normalize_position(pos)
    if norm:
        return norm
    g, a, sv = goals or 0, assists or 0, saves or 0
    if sv and not g and not a:
        return "GK"
    if g or a:
        return "FWD" if g >= max(a, 1) else "MID"
    return "?"


def classify_line_role(raw: str | None, goals: int = 0, assists: int = 0) -> str:
    """Finer role for lineup slots: ST/WING, CAM/CDM/CM, CB/LB/RB, GK."""
    coarse = normalize_position(raw) or "?"
    s = (raw or "").lower().replace("-", " ")
    if coarse == "GK":
        return "GK"
    if coarse == "DEF":
        if ("left" in s and "back" in s) or "lwb" in s or "left wing back" in s:
            return "LB"
        if ("right" in s and "back" in s) or "rwb" in s or "right wing back" in s:
            return "RB"
        if "wing back" in s:
            return "LB" if "left" in s else "RB" if "right" in s else "LB"
        if any(w in s for w in ("centre back", "center back", "centre-back", "center-back")):
            return "CB"
        return "CB"
    if coarse == "MID":
        if "wing" in s or "wide" in s:
            return "WING"
        if "defensive" in s or "holding" in s or "anchor" in s:
            return "CDM"
        if "attacking" in s or "offensive" in s:
            return "CAM"
        if "central" in s:
            return "CM"
        # Generic midfield — creative vs holding heuristic
        if (goals or 0) + (assists or 0) == 0:
            return "CM"
        if assists >= max(4, int(goals * 1.2) + 2):
            return "CAM"
        if goals <= 3 and assists <= 3:
            return "CDM"
        return "CM"
    if coarse == "FWD":
        if "wing" in s or "wide" in s or s.startswith("left ") or s.startswith("right "):
            return "WING"
        if any(w in s for w in ("centre forward", "center forward", "striker",
                                "centre-forward", "center-forward")):
            return "ST"
        # Generic "Offence" / FWD — use output profile (strikers score, wingers assist)
        if goals >= max(4, int(assists * 1.5) + 1):
            return "ST"
        if assists >= max(3, int(goals * 0.7)):
            return "WING"
        return "ST" if goals > assists else "WING"
    return coarse if coarse in ("MID", "DEF", "GK", "CM", "CDM", "CAM", "CB", "LB", "RB") else "?"


def _player_age(dob) -> int | None:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _row_player(name, team, pos, rating, dob, nationality=None,
                goals=None, assists=None, appearances=None,
                standout_rating=None, club_team=None,
                ga_per_game=None, clean_sheets=None, saves=None, team_gp=None):
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
    if ga_per_game is not None:
        row["ga_per_game"] = ga_per_game
    if clean_sheets is not None:
        row["clean_sheets"] = clean_sheets
    if saves is not None:
        row["saves"] = saves
    if team_gp is not None:
        row["team_gp"] = team_gp
    return row


def _defensive_form_score(ga_per_game: float | None) -> float:
    """0–1 where lower goals-against per game is better (typical range ~0.7–2.2)."""
    if ga_per_game is None:
        return 0.5
    return max(0.0, min(1.0, (2.3 - ga_per_game) / 1.6))


def _team_season_defense(conn, edition_id: int) -> dict[int, dict]:
    """Per-team defensive record for a competition edition."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT home_team_id, away_team_id, home_goals, away_goals "
            "FROM matches WHERE edition_id = %s AND home_goals IS NOT NULL",
            (edition_id,))
        rows = cur.fetchall()
    stats: dict[int, dict] = {}
    for hid, aid, hg, ag in rows:
        for tid, conceded in ((hid, ag), (aid, hg)):
            slot = stats.setdefault(tid, {"ga": 0, "gp": 0, "clean_sheets": 0})
            slot["ga"] += conceded
            slot["gp"] += 1
            if conceded == 0:
                slot["clean_sheets"] += 1
    for slot in stats.values():
        gp = slot["gp"]
        slot["ga_per_game"] = round(slot["ga"] / gp, 2) if gp else None
    return stats


def _compute_standout_rating(team_rating, goals, assists, apps, position,
                             ga_per_game=None, clean_sheets=None, saves=None,
                             team_gp=None) -> float:
    """0–100 blend: team strength + position-appropriate form."""
    pos = (position or "?").upper()
    elo_n = min(1.0, max(0.0, ((team_rating or 1500) - 1400) / 450))
    apps_n = min(1.0, (apps or 0) / 38)
    pos_n = _POS_WEIGHT.get(pos, 0.8)
    g, a = goals or 0, assists or 0
    gp = team_gp or 0
    def_n = _defensive_form_score(ga_per_game)
    cs_n = min(1.0, (clean_sheets or 0) / max(gp, 1) * 2.5) if gp else def_n * 0.85
    saves_n = min(1.0, (saves or 0) / 90) if saves else None

    if pos == "GK":
        # Saves + fewest goals conceded (team proxy when no individual GK stats).
        if saves_n is not None:
            blend = 0.28 * elo_n + 0.18 * apps_n + 0.32 * def_n + 0.17 * saves_n + 0.05 * pos_n
        else:
            blend = 0.30 * elo_n + 0.22 * apps_n + 0.40 * def_n + 0.03 * cs_n + 0.05 * pos_n
    elif pos == "DEF":
        # Clean sheets + low GA + regular minutes; goals/assists are a small bonus.
        contrib_n = min(1.0, apps_n * 0.75 + g * 0.04 + a * 0.06)
        blend = (0.26 * elo_n + 0.28 * def_n + 0.24 * cs_n
                 + 0.16 * contrib_n + 0.06 * pos_n)
    elif pos == "MID":
        form_n = min(1.0, (a * 1.0 + g * 0.35) / 16)
        blend = 0.32 * elo_n + 0.48 * form_n + 0.12 * apps_n + 0.08 * pos_n
    elif pos == "FWD":
        form_n = min(1.0, (g * 1.0 + a * 0.45) / 22)
        blend = 0.32 * elo_n + 0.48 * form_n + 0.12 * apps_n + 0.08 * pos_n
    else:
        form_n = min(1.0, (g + a * 0.6) / 22)
        blend = 0.35 * elo_n + 0.45 * form_n + 0.12 * apps_n + 0.08 * pos_n
    return round(100 * blend, 1)


def _affil_kind_for_comp(conn, comp: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT type FROM competitions WHERE code = %s", (comp,))
        row = cur.fetchone()
    return "national" if row and row[0] == "international" else "club"


def _standout_sql_order() -> str:
    """Rough pre-sort in SQL so the candidate pool includes non-forwards."""
    return (
        "CASE COALESCE(p.position, '?') "
        "  WHEN 'FWD' THEN pes.goals * 100 + pes.assists * 10 "
        "  WHEN 'MID' THEN pes.assists * 100 + pes.goals * 10 "
        "  WHEN 'DEF' THEN pes.appearances * 10 + pes.goals * 5 + pes.assists * 3 "
        "  WHEN 'GK'  THEN pes.appearances * 100 "
        "  ELSE pes.goals * 50 + pes.assists * 20 END"
    )


def _prefer_match_derived_stats(conn, comp: str, edition_id: int | None) -> bool:
    """Use goals/apps from finished matches in this edition (not career pes rows)."""
    if not edition_id:
        return False
    if _affil_kind_for_comp(conn, comp) == "national":
        return True
    return _has_match_derived_stats(conn, edition_id)


def _has_match_derived_stats(conn, edition_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM match_events me "
            "JOIN matches m ON m.id = me.match_id "
            "WHERE m.edition_id = %s AND me.event_type IN ('GOAL', 'PENALTY') "
            "LIMIT 1",
            (edition_id,))
        if cur.fetchone():
            return True
        cur.execute(
            "SELECT 1 FROM match_player_box_stats mpbs "
            "JOIN matches m ON m.id = mpbs.match_id "
            "WHERE m.edition_id = %s LIMIT 1",
            (edition_id,))
        if cur.fetchone():
            return True
        cur.execute(
            "SELECT 1 FROM match_lineup_players mlp "
            "JOIN matches m ON m.id = mlp.match_id "
            "WHERE m.edition_id = %s AND m.home_goals IS NOT NULL LIMIT 1",
            (edition_id,))
        return cur.fetchone() is not None


def _edition_player_stats_from_matches(conn, edition_id: int) -> dict[int, dict]:
    """Aggregate tournament/season stats from synced match detail."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT me.player_id, COUNT(*)::int "
            "FROM match_events me "
            "JOIN matches m ON m.id = me.match_id "
            "WHERE m.edition_id = %s AND me.player_id IS NOT NULL "
            "  AND me.event_type IN ('GOAL', 'PENALTY') "
            "GROUP BY me.player_id",
            (edition_id,))
        goals = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(
            "SELECT me.assist_player_id, COUNT(*)::int "
            "FROM match_events me "
            "JOIN matches m ON m.id = me.match_id "
            "WHERE m.edition_id = %s AND me.assist_player_id IS NOT NULL "
            "  AND me.event_type IN ('GOAL', 'PENALTY') "
            "GROUP BY me.assist_player_id",
            (edition_id,))
        assists = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(
            "SELECT mlp.player_id, COUNT(DISTINCT mlp.match_id)::int, "
            "       MIN(mlp.team_id) "
            "FROM match_lineup_players mlp "
            "JOIN matches m ON m.id = mlp.match_id "
            "WHERE m.edition_id = %s AND m.home_goals IS NOT NULL "
            "GROUP BY mlp.player_id",
            (edition_id,))
        apps = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

        cur.execute(
            "SELECT mpbs.player_id, SUM(COALESCE(mpbs.saves, 0))::int "
            "FROM match_player_box_stats mpbs "
            "JOIN matches m ON m.id = mpbs.match_id "
            "WHERE m.edition_id = %s "
            "GROUP BY mpbs.player_id "
            "HAVING SUM(COALESCE(mpbs.saves, 0)) > 0",
            (edition_id,))
        saves = {r[0]: r[1] for r in cur.fetchall()}

    out: dict[int, dict] = {}
    for pid in set(goals) | set(assists) | set(apps) | set(saves):
        app_n, team_id = apps.get(pid, (0, None))
        out[pid] = {
            "goals": goals.get(pid, 0),
            "assists": assists.get(pid, 0),
            "appearances": app_n,
            "team_id": team_id,
            "saves": saves.get(pid),
        }
    return out


def _position_matches(pos: str | None, pos_filter: str | None) -> bool:
    if not pos_filter:
        return True
    coarse = normalize_position(pos) or (pos or "?").upper()
    want = pos_filter.upper()
    if want == "GK":
        return coarse == "GK"
    return coarse == want


def _has_standout_signal(pos: str | None, goals: int, assists: int,
                          apps: int, saves: int | None) -> bool:
    if (goals or 0) > 0 or (assists or 0) > 0 or (saves or 0) > 0:
        return True
    return False


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


def parse_comp_from_text(text: str) -> str | None:
    """Map a competition name or code in user text to a comp code."""
    import re

    raw = (text or "").strip()
    if not raw:
        return None
    m = re.search(r"\b(PL|PD|BL1|SA|FL1|CL|DED|WC|MLS)\b", raw, re.I)
    if m:
        code = m.group(1).upper()
        return code if code in SUPPORTED_COMP_CODES else None
    low = raw.lower()
    for phrase, code in COMP_PHRASES:
        if phrase in low:
            return code
    return None


def _edition_id_for_comp(conn, comp: str, season: str | None = None) -> int | None:
    with conn.cursor() as cur:
        if season:
            cur.execute(
                "SELECT e.id FROM competition_editions e "
                "JOIN competitions c ON c.id = e.competition_id "
                "WHERE c.code = %s AND e.season = %s",
                (comp, season))
        else:
            cur.execute(
                "SELECT e.id FROM competition_editions e "
                "JOIN competitions c ON c.id = e.competition_id "
                "WHERE c.code = %s "
                "ORDER BY e.start_date DESC NULLS LAST, e.season DESC LIMIT 1",
                (comp,))
        row = cur.fetchone()
    return row[0] if row else None


def _current_season_for_comp(conn, comp: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.season FROM competition_editions e "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = %s "
            "ORDER BY e.start_date DESC NULLS LAST, e.season DESC LIMIT 1",
            (comp,))
        row = cur.fetchone()
    return row[0] if row else None


def _player_stats_in_comp(conn, player_id: int, comp: str) -> dict | None:
    """Stats for a player in a competition: current synced season first, else best past."""
    current_edition = _edition_id_for_comp(conn, comp)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pes.goals, pes.assists, pes.appearances, pes.penalties, "
            "       t.name, e.season, e.id "
            "FROM player_edition_stats pes "
            "JOIN competition_editions e ON e.id = pes.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "LEFT JOIN teams t ON t.id = pes.team_id "
            "WHERE pes.player_id = %s AND c.code = %s "
            "ORDER BY "
            "  CASE WHEN e.id = %s THEN 0 ELSE 1 END, "
            "  e.start_date DESC NULLS LAST, e.season DESC, "
            "  (pes.goals + pes.assists) DESC "
            "LIMIT 1",
            (player_id, comp, current_edition))
        row = cur.fetchone()
    if not row:
        return None
    goals, assists, apps, pens, team, season, edition_id = row
    current_season = _current_season_for_comp(conn, comp)
    return {
        "goals": goals,
        "assists": assists,
        "appearances": apps,
        "penalties": pens,
        "stats_team": team,
        "comp": comp,
        "comp_season": season,
        "comp_stats_are_historical": bool(
            current_season and season != current_season),
    }


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
    from footballmind_standings_zones import annotate_standings, finalize_mls_standings

    with conn.cursor() as cur:
        cur.execute(
            "SELECT th.name, ta.name, m.home_goals, m.away_goals FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE c.code = %s AND m.home_goals IS NOT NULL "
            "  AND (%s::text IS NULL OR e.season = %s)", (comp_code, season, season))
        table = compute_standings(cur.fetchall())
    if comp_code == "MLS":
        return finalize_mls_standings(conn, table)
    return annotate_standings(table, comp_code)


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
            "  AND m.match_date >= (CURRENT_DATE - INTERVAL '1 day') "
            "ORDER BY m.match_date ASC "
            "LIMIT %s",
            (comp, limit * 3),
        )
        cols = [d[0] for d in cur.description]
        fixtures = []
        now = _dt.datetime.now(_dt.timezone.utc)
        for row in cur.fetchall():
            f = dict(zip(cols, row))
            kick_off = _as_utc(f.get("match_date"))
            if f.get("match_date") and f.get("home_goals") is None:
                elapsed = (now - kick_off).total_seconds() / 60 if kick_off else 0
                f["live"] = 0 < elapsed < _LIVE_WINDOW_MINUTES
            elif f.get("home_goals") is not None and kick_off:
                # Ignore premature scores on fixtures still in the future.
                if kick_off > now + _dt.timedelta(minutes=30):
                    f["home_goals"] = None
                    f["away_goals"] = None
                    f["live"] = False
                else:
                    f["live"] = False
            else:
                f["live"] = False
            if is_finished_match(f.get("home_goals"), f.get("away_goals"), f.get("match_date"), now=now):
                continue
            if f.get("match_date"):
                f["match_date"] = f["match_date"].isoformat()
            fixtures.append(f)
            if len(fixtures) >= limit:
                break
    return fixtures


def get_recent_match_results(conn, comp: str = "WC", limit: int = 40) -> list[dict]:
    """Recent finished matches for a competition, with optional prediction grading."""
    from footballmind_grading import ensure_result_predictions, grade_predictions

    ensure_result_predictions(conn, comp, backfill_limit=40)
    grade_predictions(conn)
    limit = min(limit, 100)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, m.home_team_id, m.away_team_id, th.name AS home, ta.name AS away, "
            "       m.home_goals, m.away_goals, m.match_date, m.stage, "
            "       p.id AS prediction_id, "
            "       p.home_win_prob, p.draw_prob, p.away_win_prob, p.was_correct "
            "FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "LEFT JOIN LATERAL ("
            "  SELECT p2.id, p2.home_win_prob, p2.draw_prob, p2.away_win_prob, p2.was_correct "
            "  FROM predictions p2 "
            "  WHERE p2.match_id = m.id "
            "     OR (p2.match_id IS NULL "
            "         AND p2.home_team_id = m.home_team_id "
            "         AND p2.away_team_id = m.away_team_id) "
            "  ORDER BY "
            "    CASE WHEN p2.match_id = m.id THEN 0 ELSE 1 END, "
            "    p2.created_at DESC "
            "  LIMIT 1"
            ") p ON TRUE "
            "WHERE c.code = %s "
            "  AND m.home_goals IS NOT NULL "
            "  AND m.away_goals IS NOT NULL "
            "  AND m.match_date >= (CURRENT_DATE - INTERVAL '14 days') "
            "ORDER BY m.match_date DESC "
            "LIMIT %s",
            (comp, limit),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    out = []
    for r in rows:
        home, away = r["home"], r["away"]
        hg, ag = r["home_goals"], r["away_goals"]
        md = r["match_date"]
        item = {
            "match_id": r["id"],
            "home": home,
            "away": away,
            "score": f"{hg}–{ag}",
            "home_goals": hg,
            "away_goals": ag,
            "stage": r.get("stage"),
            "match_date": md.isoformat() if md else None,
        }
        if r.get("prediction_id"):
            probs = [r["home_win_prob"] or 0, r["draw_prob"] or 0, r["away_win_prob"] or 0]
            predicted = _outcome_label(home, away, r["home_win_prob"],
                                       r["draw_prob"], r["away_win_prob"])
            if hg > ag:
                actual = home
            elif hg == ag:
                actual = "Draw"
            else:
                actual = away
            pred_idx = probs.index(max(probs))
            act_idx = 0 if hg > ag else (1 if hg == ag else 2)
            item.update({
                "id": r["prediction_id"],
                "predicted": predicted,
                "predicted_confidence": round(max(probs), 3),
                "actual": actual,
                "was_correct": pred_idx == act_idx,
            })
        out.append(item)
    return out


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
        w, d, lp = int(W), int(D), int(L)
        groups.setdefault(g, []).append({
            "team": team, "P": w + d + lp, "W": w, "D": d, "L": lp,
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


def _standout_from_row(name, team, pos, rating, dob, nat, goals, ast, apps,
                       team_id, team_defense, club=None, saves=None):
    pos = _coerce_standout_position(pos, goals, ast, saves)
    td = team_defense.get(team_id, {}) if team_id else {}
    ga_pg = td.get("ga_per_game")
    cs = td.get("clean_sheets")
    gp = td.get("gp")
    sr = _compute_standout_rating(
        rating, goals, ast, apps, pos,
        ga_per_game=ga_pg, clean_sheets=cs, team_gp=gp, saves=saves)
    return _row_player(
        name, team, pos, rating, dob, nat, goals, ast, apps, sr, club,
        ga_per_game=ga_pg, clean_sheets=cs, team_gp=gp, saves=saves)


def _get_standouts_from_match_stats(
    conn, comp: str, edition_id: int, pos_filter: str | None,
    team_defense: dict, limit: int,
) -> list:
    stats_by_player = _edition_player_stats_from_matches(conn, edition_id)
    if not stats_by_player:
        return []
    kind = _affil_kind_for_comp(conn, comp)
    pids = list(stats_by_player.keys())
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.name, t.name, "
            "       COALESCE(NULLIF(TRIM(p.position), ''), lp.pos) AS position, "
            "       tr.rating, p.birth_date, "
            "       co.name, pa.team_id "
            "FROM players p "
            "JOIN player_affiliations pa ON pa.player_id = p.id AND pa.end_date IS NULL "
            "  AND pa.kind = %s "
            "JOIN teams t ON t.id = pa.team_id "
            "LEFT JOIN team_ratings tr ON tr.team_id = t.id "
            "LEFT JOIN countries co ON co.id = p.nationality "
            "LEFT JOIN LATERAL ("
            "  SELECT mlp.position AS pos "
            "  FROM match_lineup_players mlp "
            "  JOIN matches m ON m.id = mlp.match_id "
            "  WHERE mlp.player_id = p.id AND m.edition_id = %s "
            "  ORDER BY m.match_date DESC "
            "  LIMIT 1"
            ") lp ON true "
            "WHERE p.id = ANY(%s) "
            "  AND EXISTS ("
            "    SELECT 1 FROM matches m "
            "    WHERE m.edition_id = %s "
            "      AND (m.home_team_id = t.id OR m.away_team_id = t.id)"
            "  )",
            (kind, edition_id, pids, edition_id))
        rows = cur.fetchall()

    standouts = []
    for pid, name, team, pos, rating, dob, nat, aff_team_id in rows:
        st = stats_by_player.get(pid, {})
        goals = st.get("goals", 0)
        ast = st.get("assists", 0)
        apps = st.get("appearances", 0)
        saves = st.get("saves")
        team_id = st.get("team_id") or aff_team_id
        pos_ok = _position_matches(pos, pos_filter)
        if pos_filter == "GK" and not pos_ok and not saves:
            continue
        if pos_filter and pos_filter != "GK" and not pos_ok:
            continue
        if not pos_filter and _position_matches(pos, "GK"):
            continue
        if pos_filter == "GK":
            if not (saves or _position_matches(pos, "GK")):
                continue
        elif pos_filter == "DEF":
            if not _position_matches(pos, "DEF"):
                continue
        elif not _has_standout_signal(pos, goals, ast, apps, saves):
            continue
        if not pos_filter and not _has_standout_signal(pos, goals, ast, apps, saves):
            continue
        standouts.append(_standout_from_row(
            name, team, pos, rating, dob, nat,
            goals or None, ast or None, apps or None, team_id, team_defense,
            saves=saves))
    if pos_filter == "GK":
        standouts.sort(key=lambda x: (-(x.get("saves") or 0), -(x.get("standout_rating") or 0), x["name"]))
    else:
        standouts.sort(key=lambda x: (-(x.get("standout_rating") or 0), x["name"]))
    return _cap_players_per_team(standouts)[:limit]


def get_standouts(conn, comp: str = "WC", position: str | None = None, limit: int = 20) -> list:
    """Standout players ranked by position-aware form + team strength.

    Forwards lean on goals; midfielders on assists; defenders on clean sheets
    and low goals against; GKs on saves (when synced) and team GA rate.
    """
    limit = min(limit, 60)
    pos_filter = (position or "").upper() or None
    edition_id = _edition_id_for_comp(conn, comp)
    kind = _affil_kind_for_comp(conn, comp)
    team_defense = _team_season_defense(conn, edition_id) if edition_id else {}

    if edition_id and _prefer_match_derived_stats(conn, comp, edition_id):
        match_standouts = _get_standouts_from_match_stats(
            conn, comp, edition_id, pos_filter, team_defense, limit)
        if match_standouts:
            return match_standouts

    if edition_id and _has_comp_scorers(conn, edition_id):
        with conn.cursor() as cur:
            sql = (
                "SELECT p.name, t.name, p.position, tr.rating, p.birth_date, "
                "       co.name, pes.goals, pes.assists, pes.appearances, "
                "       COALESCE(pes.team_id, t.id) "
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
            sql += f" ORDER BY {_standout_sql_order()} DESC, p.name LIMIT %s"
            params.append(limit * 4)
            cur.execute(sql, params)
            rows = cur.fetchall()

        standouts = []
        for name, team, pos, rating, dob, nat, goals, ast, apps, team_id in rows:
            standouts.append(_standout_from_row(
                name, team, pos, rating, dob, nat, goals, ast, apps,
                team_id, team_defense))
        standouts.sort(key=lambda x: (-(x.get("standout_rating") or 0), x["name"]))
        return _cap_players_per_team(standouts)[:limit]

    with conn.cursor() as cur:
        sql = (
            "SELECT p.id, p.name, t.name, p.position, tr.rating, p.birth_date, "
            "       co.name, COALESCE(cs.goals, 0), COALESCE(cs.assists, 0), "
            "       COALESCE(cs.appearances, 0), cs.club_team, t.id "
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
            + ("  AND pes.edition_id = %s " if edition_id else "")
            + "  ORDER BY (pes.goals + pes.assists * 0.6) DESC, pes.appearances DESC "
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
        params: list = []
        if edition_id:
            params.append(edition_id)
        params.extend([kind, comp])
        if pos_filter:
            sql += " AND p.position = %s "
            params.append(pos_filter)
        sql += " ORDER BY p.id"
        cur.execute(sql, params)
        rows = cur.fetchall()

    standouts = []
    for _pid, name, team, pos, rating, dob, nat, goals, ast, apps, club, team_id in rows:
        standouts.append(_standout_from_row(
            name, team, pos, rating, dob, nat, goals or None, ast or None,
            apps or None, team_id, team_defense, club))

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
            "SELECT p.id, p.name, p.position, p.line_role, pa.shirt_number, "
            "       p.birth_date, co.name "
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

    from footballmind_roles import resolve_player_line_role
    from footballmind_sofifa import get_eafc_attributes_bulk
    pids = [r[0] for r in rows]
    eafc_map = get_eafc_attributes_bulk(conn, pids)

    squad = []
    for pid, name, pos, line_role, shirt, dob, nationality in rows:
        tactical = resolve_player_line_role(
            name=name,
            db_line_role=line_role,
            db_position=pos,
        )
        entry = {
            "name": name,
            "position": pos or "?",
            "line_role": tactical,
            "shirt_number": shirt,
            "age": _player_age(dob),
            "nationality": nationality,
        }
        eafc = eafc_map.get(pid)
        if eafc:
            entry["eafc"] = eafc
        squad.append(entry)
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
    base = _find_player_record(conn, name)
    if not base:
        return None
    profile = dict(base)
    if comp:
        stats = get_player_comp_stats(conn, profile["name"], comp)
        if stats:
            profile.update(stats)
    from footballmind_sofifa import get_eafc_attributes
    eafc = get_eafc_attributes(conn, base["id"])
    if eafc:
        profile["eafc"] = eafc
    return profile


def _find_player_record(conn, name: str) -> dict | None:
    """Best-match player row for comparisons (exact name preferred)."""
    term = (name or "").strip()
    if len(term) < 2:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.name, p.position, p.birth_date, co.name "
            "FROM players p "
            "LEFT JOIN countries co ON co.id = p.nationality "
            "WHERE p.name ILIKE %s "
            "ORDER BY "
            "  CASE WHEN LOWER(p.name) = LOWER(%s) THEN 0 "
            "       WHEN p.name ILIKE %s THEN 1 ELSE 2 END, "
            "  p.name "
            "LIMIT 1",
            (f"%{term}%", term, f"{term}%"))
        row = cur.fetchone()
    if not row:
        return None
    pid, pname, pos, dob, nat = row
    return {
        "id": pid,
        "name": pname,
        "position": pos or "?",
        "age": _player_age(dob),
        "nationality": nat,
    }


def _player_affiliation(conn, player_id: int, kind: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.name, t.type, tr.rating "
            "FROM player_affiliations pa "
            "JOIN teams t ON t.id = pa.team_id "
            "LEFT JOIN team_ratings tr ON tr.team_id = t.id "
            "WHERE pa.player_id = %s AND pa.kind = %s AND pa.end_date IS NULL "
            "LIMIT 1",
            (player_id, kind))
        row = cur.fetchone()
    if not row:
        return None
    team, team_type, rating = row
    return {
        "team": team,
        "team_type": team_type,
        "rating": round(rating) if rating is not None else None,
    }


def _best_club_season(conn, player_id: int) -> dict | None:
    """Strongest club-competition season on goals + assists."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pes.goals, pes.assists, pes.appearances, pes.penalties, "
            "       t.name, c.code, e.season "
            "FROM player_edition_stats pes "
            "JOIN teams t ON t.id = pes.team_id "
            "JOIN competition_editions e ON e.id = pes.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE pes.player_id = %s AND t.type = 'club' "
            "ORDER BY (pes.goals + pes.assists * 0.6) DESC, pes.appearances DESC "
            "LIMIT 1",
            (player_id,))
        row = cur.fetchone()
    if not row:
        return None
    goals, assists, apps, pens, club, comp_code, season = row
    return {
        "club": club,
        "comp_code": comp_code,
        "season": season,
        "goals": goals,
        "assists": assists,
        "appearances": apps,
        "penalties": pens,
    }


def _build_compare_profile(conn, name: str, comp: str | None) -> dict | None:
    base = _find_player_record(conn, name)
    if not base:
        return None
    pid = base["id"]
    profile = dict(base)

    nat = _player_affiliation(conn, pid, "national")
    club = _player_affiliation(conn, pid, "club")
    club_season = _best_club_season(conn, pid)

    if nat:
        profile["national_team"] = nat["team"]
        profile["national_rating"] = nat["rating"]
    if club:
        profile["club"] = club["team"]
        profile["club_rating"] = club["rating"]
    if club_season:
        profile["club_season"] = club_season

    if comp:
        stats = _player_stats_in_comp(conn, pid, comp)
        if stats:
            profile.update(stats)

    from footballmind_sofifa import get_eafc_attributes
    eafc = get_eafc_attributes(conn, pid)
    if eafc:
        profile["eafc"] = eafc

    # Legacy fields used by MCP / older formatters
    kind = _affil_kind_for_comp(conn, comp) if comp else None
    if kind == "club" and club:
        profile["team"] = club["team"]
        profile["team_rating"] = club["rating"]
    elif nat:
        profile["team"] = nat["team"]
        profile["team_rating"] = nat["rating"]
    elif club:
        profile["team"] = club["team"]
        profile["team_rating"] = club["rating"]

    return profile


def _comparison_context(comp: str | None, conn) -> tuple[str, str]:
    """Return (mode, human-readable note) for compare_players output."""
    if not comp:
        return "general", (
            "Side-by-side profile with national team and club season context."
        )
    kind = _affil_kind_for_comp(conn, comp)
    if kind == "national":
        return "national_squads", (
            f"Comparing as national squad members ({comp} context). "
            "Club season form is included where synced."
        )
    label = COMP_LABELS.get(comp, comp)
    return "club_competition", (
        f"Comparing players in {label} ({comp}) stats "
        "(current synced season when available, otherwise best past season on file)."
    )


def _form_score(p: dict) -> float:
    cs = p.get("club_season") or {}
    if cs.get("goals") is not None or cs.get("assists"):
        return (cs.get("goals") or 0) + (cs.get("assists") or 0) * 0.6
    if p.get("goals") is not None:
        return (p.get("goals") or 0) + (p.get("assists") or 0) * 0.6
    return 0.0


def get_player_comp_stats(conn, name: str, comp: str) -> dict | None:
    base = _find_player_record(conn, name)
    if not base:
        return None
    return _player_stats_in_comp(conn, base["id"], comp)


def get_top_scorers(conn, comp: str = "PL", limit: int = 20) -> list:
    limit = min(limit, 50)
    edition_id = _edition_id_for_comp(conn, comp)
    if not edition_id:
        return []

    if _prefer_match_derived_stats(conn, comp, edition_id):
        stats_by_player = _edition_player_stats_from_matches(conn, edition_id)
        if stats_by_player:
            kind = _affil_kind_for_comp(conn, comp)
            pids = list(stats_by_player.keys())
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.id, p.name, t.name, p.position, p.birth_date, co.name, "
                    "       pa.team_id "
                    "FROM players p "
                    "JOIN player_affiliations pa ON pa.player_id = p.id "
                    "  AND pa.end_date IS NULL AND pa.kind = %s "
                    "JOIN teams t ON t.id = pa.team_id "
                    "LEFT JOIN countries co ON co.id = p.nationality "
                    "WHERE p.id = ANY(%s)",
                    (kind, pids))
                rows = cur.fetchall()
            ranked = []
            for pid, name, team, pos, dob, nat, _tid in rows:
                st = stats_by_player.get(pid, {})
                goals = st.get("goals", 0)
                if goals <= 0:
                    continue
                ranked.append((goals, st.get("assists", 0), name, team, pos, dob, nat, st))
            ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
            scorers = []
            for i, (goals, assists, name, team, pos, dob, nat, st) in enumerate(ranked[:limit], 1):
                scorers.append({
                    "rank": i,
                    "name": name,
                    "team": team,
                    "position": pos or "?",
                    "goals": goals,
                    "assists": assists,
                    "appearances": st.get("appearances", 0),
                    "penalties": None,
                    "age": _player_age(dob),
                    "nationality": nat,
                })
            return scorers

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


def _outcome_label(home: str, away: str, hw, dw, aw) -> str:
    probs = [hw or 0.0, dw or 0.0, aw or 0.0]
    idx = probs.index(max(probs))
    if idx == 0:
        return home
    if idx == 1:
        return "Draw"
    return away


def get_prediction_results(conn, limit: int = 30) -> list[dict]:
    """Finished matches we predicted: score, pick, and whether it was right.

    One row per match (most recent prediction wins). Runs grading first so
    newly synced results appear without waiting for the batch job.
    """
    from footballmind_grading import grade_predictions

    grade_predictions(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (COALESCE(p.match_id, p.id)) "
            "       p.id, "
            "       COALESCE(thm.name, thp.name) AS home, "
            "       COALESCE(tam.name, tap.name) AS away, "
            "       p.home_win_prob, p.draw_prob, p.away_win_prob, "
            "       p.confidence, "
            "       m.home_goals AS hg, "
            "       m.away_goals AS ag, "
            "       p.was_correct, m.match_date, p.match_id "
            "FROM predictions p "
            "LEFT JOIN matches m ON m.id = p.match_id "
            "LEFT JOIN teams thp ON thp.id = p.home_team_id "
            "LEFT JOIN teams tap ON tap.id = p.away_team_id "
            "LEFT JOIN teams thm ON thm.id = m.home_team_id "
            "LEFT JOIN teams tam ON tam.id = m.away_team_id "
            "WHERE m.home_goals IS NOT NULL "
            "  AND COALESCE(thm.name, thp.name) IS NOT NULL "
            "ORDER BY COALESCE(p.match_id, p.id), p.created_at DESC")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    out = []
    for r in rows[:limit]:
        home, away = r["home"], r["away"]
        hg, ag = r["hg"], r["ag"]
        predicted = _outcome_label(home, away, r["home_win_prob"],
                                   r["draw_prob"], r["away_win_prob"])
        if hg > ag:
            actual = home
        elif hg == ag:
            actual = "Draw"
        else:
            actual = away
        probs = [r["home_win_prob"] or 0, r["draw_prob"] or 0, r["away_win_prob"] or 0]
        pred_idx = probs.index(max(probs))
        act_idx = 0 if hg > ag else (1 if hg == ag else 2)
        was = pred_idx == act_idx
        md = r["match_date"]
        out.append({
            "id": r["id"],
            "home": home,
            "away": away,
            "score": f"{hg}–{ag}",
            "home_goals": hg,
            "away_goals": ag,
            "predicted": predicted,
            "predicted_confidence": round(max(probs), 3),
            "actual": actual,
            "was_correct": was,
            "match_date": md.isoformat() if md else None,
        })
    out.sort(key=lambda x: x.get("match_date") or "", reverse=True)
    return out


def get_prediction_summary(conn) -> dict:
    """Hit rate counting one result per match (not every duplicate chat prediction)."""
    with conn.cursor() as cur:
        cur.execute(
            "WITH per_match AS ("
            "  SELECT DISTINCT ON (p.match_id) p.was_correct "
            "  FROM predictions p "
            "  WHERE p.was_correct IS NOT NULL AND p.match_id IS NOT NULL "
            "  ORDER BY p.match_id, p.created_at DESC"
            ") "
            "SELECT count(*), count(*) FILTER (WHERE was_correct) FROM per_match")
        graded, correct = cur.fetchone()
    return {
        "graded": graded or 0,
        "correct": correct or 0,
        "hit_rate": (correct / graded) if graded else None,
    }


_CALIBRATION_BINS = [
    (0.33, 0.45, "33–45%"),
    (0.45, 0.55, "45–55%"),
    (0.55, 0.65, "55–65%"),
    (0.65, 0.75, "65–75%"),
    (0.75, 0.85, "75–85%"),
    (0.85, 1.001, "85%+"),
]


def get_prediction_calibration(conn) -> dict:
    """Confidence calibration: when we say ~70%, do ~70% of those picks win?

    Uses one graded prediction per match (most recent). Bins by predicted
    confidence (max of W/D/L probabilities).
    """
    from footballmind_grading import grade_predictions

    grade_predictions(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (p.match_id) "
            "       GREATEST(COALESCE(p.home_win_prob, 0), "
            "                COALESCE(p.draw_prob, 0), "
            "                COALESCE(p.away_win_prob, 0)) AS conf, "
            "       p.was_correct "
            "FROM predictions p "
            "WHERE p.was_correct IS NOT NULL AND p.match_id IS NOT NULL "
            "ORDER BY p.match_id, p.created_at DESC")
        rows = cur.fetchall()

    buckets = [
        {"label": label, "min": lo, "max": hi, "count": 0, "correct": 0,
         "conf_sum": 0.0}
        for lo, hi, label in _CALIBRATION_BINS
    ]
    confs, outcomes = [], []
    for conf, was_correct in rows:
        if conf is None:
            continue
        conf = float(conf)
        confs.append(conf)
        outcomes.append(1.0 if was_correct else 0.0)
        for b in buckets:
            if b["min"] <= conf < b["max"]:
                b["count"] += 1
                b["conf_sum"] += conf
                if was_correct:
                    b["correct"] += 1
                break

    bins_out = []
    abs_errors = []
    for b in buckets:
        if b["count"]:
            expected = b["conf_sum"] / b["count"]
            actual = b["correct"] / b["count"]
            abs_errors.append(abs(actual - expected))
            bins_out.append({
                "label": b["label"],
                "min": b["min"],
                "max": b["max"],
                "count": b["count"],
                "correct": b["correct"],
                "expected_rate": round(expected, 3),
                "actual_rate": round(actual, 3),
                "gap": round(actual - expected, 3),
            })
        else:
            bins_out.append({
                "label": b["label"],
                "min": b["min"],
                "max": b["max"],
                "count": 0,
                "correct": 0,
                "expected_rate": None,
                "actual_rate": None,
                "gap": None,
            })

    graded = len(confs)
    correct = int(sum(outcomes))
    mean_conf = (sum(confs) / graded) if graded else None
    hit_rate = (correct / graded) if graded else None
    mace = (sum(abs_errors) / len(abs_errors)) if abs_errors else None

    return {
        "graded": graded,
        "correct": correct,
        "hit_rate": hit_rate,
        "mean_confidence": round(mean_conf, 3) if mean_conf is not None else None,
        "mean_abs_calibration_error": round(mace, 3) if mace is not None else None,
        "bins": bins_out,
        "note": ("Well calibrated when actual win rate ≈ predicted confidence "
                 "in each bin. Needs several graded matches per bin to be meaningful."),
    }


def compare_players(conn, player_a: str, player_b: str,
                    comp: str | None = None) -> dict:
    """Side-by-side profile: national team, club, and season/comp stats."""
    a = _build_compare_profile(conn, player_a, comp)
    b = _build_compare_profile(conn, player_b, comp)
    if not a:
        return {"error": f"No player found matching {player_a!r}"}
    if not b:
        return {"error": f"No player found matching {player_b!r}"}
    mode, note = _comparison_context(comp, conn)
    return {
        "comp": comp,
        "comparison_mode": mode,
        "comparison_note": note,
        "player_a": a,
        "player_b": b,
    }


AVAIL_STATUSES = frozenset({"injured", "doubtful", "suspended"})


def _resolve_player_on_team(cur, player_name: str, team_id: int) -> tuple[int, str] | None:
    cur.execute(
        "SELECT p.id, p.name FROM players p "
        "JOIN player_affiliations pa ON pa.player_id = p.id "
        "WHERE pa.team_id = %s AND pa.end_date IS NULL "
        "  AND p.name ILIKE %s "
        "ORDER BY CASE WHEN LOWER(p.name) = LOWER(%s) THEN 0 ELSE 1 END, p.name "
        "LIMIT 1",
        (team_id, f"%{player_name.strip()}%", player_name.strip()))
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def list_availability_flags(conn, team_name: str, comp: str = "WC") -> list[dict]:
    from footballmind_mcp_predict import _resolve_team

    with conn.cursor() as cur:
        team_id, _ = _resolve_team(cur, team_name)
        cur.execute(
            "SELECT p.name, pa.status, pa.reason, pa.updated_at, pa.source "
            "FROM player_availability pa "
            "JOIN players p ON p.id = pa.player_id "
            "WHERE pa.team_id = %s AND pa.comp_code = %s "
            "ORDER BY pa.status, p.name",
            (team_id, comp))
        rows = cur.fetchall()
    return [
        {
            "player": name,
            "status": status,
            "reason": reason,
            "updated_at": updated.isoformat() if updated else None,
            "source": source or "manual",
            "manual": (source or "manual") == "manual",
        }
        for name, status, reason, updated, source in rows
    ]


def set_availability_flag(conn, player_name: str, team_name: str, comp: str,
                          status: str, reason: str | None = None) -> dict:
    from footballmind_mcp_predict import _resolve_team

    status = (status or "").strip().lower()
    if status not in AVAIL_STATUSES:
        return {"error": f"status must be one of: {', '.join(sorted(AVAIL_STATUSES))}"}
    with conn.cursor() as cur:
        team_id, _ = _resolve_team(cur, team_name)
        found = _resolve_player_on_team(cur, player_name, team_id)
        if not found:
            return {"error": f"No player on {team_name!r} matching {player_name!r}"}
        player_id, resolved_name = found
        cur.execute(
            "INSERT INTO player_availability "
            "(player_id, team_id, comp_code, status, reason, source, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, 'manual', now()) "
            "ON CONFLICT (player_id, team_id, comp_code) DO UPDATE SET "
            "  status = EXCLUDED.status, reason = EXCLUDED.reason, "
            "  source = 'manual', updated_at = now()",
            (player_id, team_id, comp, status, (reason or "").strip() or None))
    conn.commit()
    return {
        "ok": True,
        "player": resolved_name,
        "team": team_name,
        "comp": comp,
        "status": status,
        "reason": reason,
    }


def clear_availability_flag(conn, player_name: str, team_name: str,
                            comp: str) -> dict:
    from footballmind_mcp_predict import _resolve_team

    with conn.cursor() as cur:
        team_id, _ = _resolve_team(cur, team_name)
        found = _resolve_player_on_team(cur, player_name, team_id)
        if not found:
            return {"error": f"No player on {team_name!r} matching {player_name!r}"}
        player_id, resolved_name = found
        cur.execute(
            "DELETE FROM player_availability "
            "WHERE player_id = %s AND team_id = %s AND comp_code = %s",
            (player_id, team_id, comp))
        deleted = cur.rowcount
    conn.commit()
    if not deleted:
        return {"error": f"No manual flag found for {resolved_name} ({comp})"}
    return {"ok": True, "player": resolved_name, "team": team_name, "comp": comp}
