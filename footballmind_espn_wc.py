"""
FootballMind — ESPN World Cup lineup ingest (fifa.world hidden JSON API).

Fills match_team_lineups / match_lineup_players when football-data.org free tier
omits lineups. Uses ESPN event IDs stored in provider_external_ids.

Not an official API — batch job only; do not call from /api/chat.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import requests

from footballmind_enrich import _resolve_player_on_team, _resolve_team_id, _store_provider_id
from footballmind_lineup import normalize_formation
from footballmind_services import normalize_position

PROVIDER = "espn"
WC_SLUG = "fifa.world"
SCOREBOARD_URL = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{WC_SLUG}/scoreboard"
SUMMARY_URL = f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/{WC_SLUG}/summary"

# ESPN display names that differ from football-data.org national team names.
_ESPN_TEAM_ALIASES = {
    "usa": "United States",
    "u.s.": "United States",
    "korea republic": "South Korea",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
}


def _get_json(url: str, params: dict | None = None, timeout: int = 25) -> dict:
    r = requests.get(url, params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _espn_team_name(raw: str | None) -> str:
    if not raw:
        return ""
    return _ESPN_TEAM_ALIASES.get(raw.strip().lower(), raw.strip())


def _parse_event_teams(event: dict) -> tuple[str, str, str | None] | None:
    """Return (home_name, away_name, espn_event_id) or None."""
    comps = event.get("competitions") or []
    if not comps:
        return None
    competitors = comps[0].get("competitors") or []
    home = away = None
    for c in competitors:
        name = _espn_team_name((c.get("team") or {}).get("displayName"))
        if not name:
            continue
        if c.get("homeAway") == "home":
            home = name
        elif c.get("homeAway") == "away":
            away = name
    eid = event.get("id")
    if not home or not away or not eid:
        return None
    return home, away, str(eid)


def _event_date(event: dict) -> date | None:
    raw = event.get("date") or (event.get("competitions") or [{}])[0].get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _event_finished(event: dict) -> bool:
    st = ((event.get("competitions") or [{}])[0].get("status") or {}).get("type") or {}
    return st.get("completed") is True or st.get("name") == "STATUS_FULL_TIME"


def fetch_scoreboard(day: date, limit: int = 50) -> list[dict]:
    data = _get_json(SCOREBOARD_URL, {"dates": day.strftime("%Y%m%d"), "limit": limit})
    return data.get("events") or []


def fetch_summary(espn_event_id: str) -> dict:
    return _get_json(SUMMARY_URL, {"event": espn_event_id})


def _find_match_by_provider(cur, espn_event_id: str) -> int | None:
    cur.execute(
        "SELECT entity_id FROM provider_external_ids "
        "WHERE provider = %s AND entity_type = 'match' AND external_id = %s",
        (PROVIDER, str(espn_event_id)))
    row = cur.fetchone()
    return row[0] if row else None


def _find_match_by_teams_date(cur, home_id: int, away_id: int, match_day: date,
                              slack_days: int = 1) -> int | None:
    for delta in (0,) + tuple(d for d in range(-slack_days, slack_days + 1) if d != 0):
        day = match_day + timedelta(days=delta)
        cur.execute(
            "SELECT m.id FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = 'WC' AND m.home_team_id = %s AND m.away_team_id = %s "
            "  AND m.match_date::date = %s "
            "LIMIT 1",
            (home_id, away_id, day))
        row = cur.fetchone()
        if row:
            return row[0]
    return None


def _resolve_or_create_player(cur, team_id: int, athlete: dict, espn_athlete_id: str | None) -> int | None:
    display = (athlete.get("displayName") or athlete.get("shortName") or "").strip()
    if not display:
        return None
    if espn_athlete_id:
        cur.execute(
            "SELECT entity_id FROM provider_external_ids "
            "WHERE provider = %s AND entity_type = 'player' AND external_id = %s",
            (PROVIDER, str(espn_athlete_id)))
        row = cur.fetchone()
        if row:
            return row[0]
    found = _resolve_player_on_team(cur, team_id, display)
    if found:
        pid = found
        if espn_athlete_id:
            _store_provider_id(cur, "player", pid, PROVIDER, str(espn_athlete_id))
        return pid
    cur.execute(
        "INSERT INTO players (name) VALUES (%s) RETURNING id",
        (display,))
    pid = cur.fetchone()[0]
    cur.execute(
        "SELECT id FROM player_affiliations "
        "WHERE player_id = %s AND kind = 'national' AND end_date IS NULL",
        (pid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO player_affiliations (player_id, team_id, kind, start_date) "
            "VALUES (%s, %s, 'national', CURRENT_DATE)",
            (pid, team_id))
    if espn_athlete_id:
        _store_provider_id(cur, "player", pid, PROVIDER, str(espn_athlete_id))
    return pid


def _stat_value(stats: list[dict], name: str) -> int | None:
    for row in stats or []:
        if row.get("name") == name:
            try:
                return int(float(row.get("value") or 0))
            except (TypeError, ValueError):
                return None
    return None


def _espn_scoring_events(summary: dict) -> list[dict]:
    """Scoring keyEvents from an ESPN summary, if any."""
    return [
        event for event in (summary.get("keyEvents") or [])
        if event.get("scoringPlay")
    ]


def _sync_espn_key_events(cur, match_id: int, summary: dict,
                          name_to_id: dict[str, int]) -> int:
    """Insert goals/assists from ESPN keyEvents into match_events."""
    scoring_events = _espn_scoring_events(summary)
    if not scoring_events:
        return 0
    cur.execute("DELETE FROM match_events WHERE match_id = %s", (match_id,))
    n = 0
    for event in scoring_events:
        etype_raw = ((event.get("type") or {}).get("type") or "").lower()
        if "own" in etype_raw and "goal" in etype_raw:
            etype = "OWN_GOAL"
        elif "penalty" in etype_raw:
            etype = "PENALTY"
        else:
            etype = "GOAL"
        team_name = _espn_team_name((event.get("team") or {}).get("displayName"))
        team_id = name_to_id.get(team_name)
        if not team_id and team_name:
            team_id = _resolve_team_id(cur, team_name)
        participants = event.get("participants") or []
        scorer_id = assist_id = None
        if participants:
            scorer_ath = (participants[0].get("athlete") or {})
            scorer_id = _resolve_or_create_player(
                cur, team_id, scorer_ath,
                str(scorer_ath["id"]) if scorer_ath.get("id") else None,
            ) if team_id else None
        if len(participants) > 1:
            assist_ath = (participants[1].get("athlete") or {})
            assist_id = _resolve_or_create_player(
                cur, team_id, assist_ath,
                str(assist_ath["id"]) if assist_ath.get("id") else None,
            ) if team_id else None
        minute = None
        clock = event.get("clock") or {}
        try:
            minute = int((clock.get("value") or 0) // 60) or None
        except (TypeError, ValueError):
            minute = None
        cur.execute(
            "INSERT INTO match_events "
            "(match_id, team_id, player_id, assist_player_id, event_type, minute) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (match_id, team_id, scorer_id, assist_id, etype, minute))
        n += 1
    return n


def _sync_espn_box_stats(cur, match_id: int, rosters: list[dict],
                         name_to_id: dict[str, int]) -> int:
    """Persist per-match saves / goals conceded from ESPN roster stats."""
    cur.execute(
        "DELETE FROM match_player_box_stats WHERE match_id = %s",
        (match_id,))
    n = 0
    for roster in rosters:
        team_name = _espn_team_name((roster.get("team") or {}).get("displayName"))
        team_id = name_to_id.get(team_name) or _resolve_team_id(cur, team_name)
        if not team_id:
            continue
        for entry in roster.get("roster") or []:
            athlete = entry.get("athlete") or {}
            espn_aid = athlete.get("id")
            pid = _resolve_or_create_player(
                cur, team_id, athlete, str(espn_aid) if espn_aid else None)
            if not pid:
                continue
            stats = entry.get("stats") or []
            saves = _stat_value(stats, "saves")
            gc = _stat_value(stats, "goalsConceded")
            apps = _stat_value(stats, "appearances")
            if not apps and not entry.get("starter"):
                continue
            if saves is None and gc is None:
                continue
            cur.execute(
                "INSERT INTO match_player_box_stats "
                "(match_id, player_id, saves, goals_conceded) "
                "VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (match_id, player_id) DO UPDATE SET "
                "  saves = EXCLUDED.saves, goals_conceded = EXCLUDED.goals_conceded, "
                "  synced_at = now()",
                (match_id, pid, saves, gc))
            n += 1
    return n


def _upsert_team_lineup(cur, match_id: int, team_id: int, formation: str | None,
                        roster_entries: list[dict]) -> int:
    """Replace lineup rows for one team; return count of players written."""
    if formation:
        form = normalize_formation(formation) or formation
        cur.execute(
            "INSERT INTO match_team_lineups (match_id, team_id, formation) "
            "VALUES (%s,%s,%s) "
            "ON CONFLICT (match_id, team_id) DO UPDATE SET formation = EXCLUDED.formation",
            (match_id, team_id, form))
    cur.execute(
        "DELETE FROM match_lineup_players WHERE match_id = %s AND team_id = %s",
        (match_id, team_id))
    n = 0
    for entry in roster_entries:
        athlete = entry.get("athlete") or {}
        espn_aid = athlete.get("id")
        pid = _resolve_or_create_player(cur, team_id, athlete, str(espn_aid) if espn_aid else None)
        if not pid:
            continue
        role = "starter" if entry.get("starter") else "bench"
        pos = (entry.get("position") or {}).get("name") or (entry.get("position") or {}).get("abbreviation")
        pos = normalize_position(pos) or pos
        jersey = entry.get("jersey")
        try:
            jersey = int(jersey) if jersey is not None else None
        except (TypeError, ValueError):
            jersey = None
        cur.execute(
            "INSERT INTO match_lineup_players "
            "(match_id, team_id, player_id, role, shirt_number, position) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (match_id, team_id, player_id) DO UPDATE SET "
            "  role = EXCLUDED.role, shirt_number = EXCLUDED.shirt_number, "
            "  position = COALESCE(EXCLUDED.position, match_lineup_players.position)",
            (match_id, team_id, pid, role, jersey, pos))
        n += 1
    return n


def ingest_summary(conn, espn_event_id: str, home_name: str, away_name: str,
                   match_day: date | None = None) -> dict:
    """Fetch ESPN summary and upsert lineups for a matched WC fixture."""
    summary = fetch_summary(espn_event_id)
    rosters = summary.get("rosters") or []
    if not rosters:
        return {"espn_event_id": espn_event_id, "skipped": "no_rosters"}

    stats = {"espn_event_id": espn_event_id, "teams": 0, "players": 0, "match_id": None}

    with conn.cursor() as cur:
        home_id = _resolve_team_id(cur, home_name)
        away_id = _resolve_team_id(cur, away_name)
        if not home_id or not away_id:
            return {**stats, "skipped": "team_not_found",
                    "home": home_name, "away": away_name}

        match_id = _find_match_by_provider(cur, espn_event_id)
        if not match_id and match_day:
            match_id = _find_match_by_teams_date(cur, home_id, away_id, match_day)
        if not match_id:
            return {**stats, "skipped": "match_not_in_db", "home": home_name, "away": away_name}

        stats["match_id"] = match_id
        _store_provider_id(cur, "match", match_id, PROVIDER, str(espn_event_id))

        name_to_id = {home_name: home_id, away_name: away_id}
        for roster in rosters:
            team_name = _espn_team_name((roster.get("team") or {}).get("displayName"))
            team_id = name_to_id.get(team_name) or _resolve_team_id(cur, team_name)
            if not team_id:
                continue
            name_to_id[team_name] = team_id
            players = roster.get("roster") or []
            if not players:
                continue
            n = _upsert_team_lineup(
                cur, match_id, team_id, roster.get("formation"), players)
            if n:
                stats["teams"] += 1
                stats["players"] += n

        stats["events"] = _sync_espn_key_events(cur, match_id, summary, name_to_id)
        stats["box_stats"] = _sync_espn_box_stats(cur, match_id, rosters, name_to_id)

    conn.commit()
    return stats


def _pending_db_matches(cur, limit: int) -> list[tuple[int, date, str, str]]:
    cur.execute(
        "SELECT m.id, m.match_date::date, th.name, ta.name "
        "FROM matches m "
        "JOIN teams th ON th.id = m.home_team_id "
        "JOIN teams ta ON ta.id = m.away_team_id "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = 'WC' AND m.home_goals IS NOT NULL "
        "  AND ("
        "    NOT EXISTS ("
        "      SELECT 1 FROM match_team_lineups mtl "
        "      WHERE mtl.match_id = m.id AND mtl.formation IS NOT NULL"
        "    ) "
        "    OR NOT EXISTS ("
        "      SELECT 1 FROM match_events me WHERE me.match_id = m.id"
        "    )"
        "  ) "
        "ORDER BY m.match_date DESC LIMIT %s",
        (limit,))
    return cur.fetchall()


def _find_espn_event_for_match(events: list[dict], home: str, away: str) -> dict | None:
    for ev in events:
        parsed = _parse_event_teams(ev)
        if not parsed:
            continue
        eh, ea, _ = parsed
        if eh == home and ea == away:
            return ev
    return None


def _find_espn_event_near_date(
    events_by_day: dict[date, list[dict]],
    match_day: date,
    home: str,
    away: str,
    slack_days: int = 1,
) -> tuple[dict | None, date | None]:
    """Match by teams; allow ±slack_days when FDO and ESPN kickoff dates differ."""
    for delta in (0,) + tuple(d for d in range(-slack_days, slack_days + 1) if d != 0):
        day = match_day + timedelta(days=delta)
        ev = _find_espn_event_for_match(events_by_day.get(day) or [], home, away)
        if ev:
            return ev, day
    return None, None


def sync_espn_wc_lineups(conn, limit: int = 25, since_days: int = 21,
                         pause_sec: float = 0.35) -> dict:
    """
    Sync WC lineups from ESPN for:
      1) Finished DB matches missing formation data (primary)
      2) Scoreboard scan for recent days (catches matches not yet in DB)
    """
    out = {"checked": 0, "synced": 0, "players": 0, "skipped": [], "errors": []}

    with conn.cursor() as cur:
        pending = _pending_db_matches(cur, limit)

    # Group pending by match date to minimize scoreboard calls.
    by_day: dict[date, list[tuple]] = {}
    for match_id, match_day, home, away in pending:
        by_day.setdefault(match_day, []).append((match_id, home, away))

    today = date.today()
    scan_days = {today - timedelta(days=d) for d in range(since_days + 1)}
    for match_day in by_day:
        scan_days.add(match_day)
        for delta in (-1, 1):
            scan_days.add(match_day + timedelta(days=delta))

    events_by_day: dict[date, list[dict]] = {}
    for day in sorted(scan_days):
        try:
            events_by_day[day] = fetch_scoreboard(day)
            time.sleep(pause_sec)
        except Exception as e:
            out["errors"].append(f"scoreboard {day}: {e!r}")

    for match_id, match_day, home, away in pending:
        out["checked"] += 1
        ev, espn_day = _find_espn_event_near_date(events_by_day, match_day, home, away)
        if not ev:
            out["skipped"].append({"match_id": match_id, "reason": "no_espn_event", "date": str(match_day)})
            continue
        parsed = _parse_event_teams(ev)
        if not parsed:
            continue
        eh, ea, eid = parsed
        try:
            stats = ingest_summary(conn, eid, eh, ea, espn_day or match_day)
            if stats.get("players"):
                out["synced"] += 1
                out["players"] += stats["players"]
            else:
                out["skipped"].append({"match_id": match_id, **stats})
        except Exception as e:
            out["errors"].append(f"match {match_id}: {e!r}")
        time.sleep(pause_sec)

    # Opportunistic: finished ESPN events on recent days not yet linked.
    seen_ids = set()
    for day, events in events_by_day.items():
        for ev in events:
            if not _event_finished(ev):
                continue
            parsed = _parse_event_teams(ev)
            if not parsed:
                continue
            home, away, eid = parsed
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            with conn.cursor() as cur:
                if _find_match_by_provider(cur, eid):
                    continue
            try:
                stats = ingest_summary(conn, eid, home, away, _event_date(ev))
                if stats.get("players"):
                    out["synced"] += 1
                    out["players"] += stats["players"]
            except Exception as e:
                out["errors"].append(f"event {eid}: {e!r}")

    return out


def backfill_espn_wc_dates(conn, start: date, end: date, pause_sec: float = 0.4) -> dict:
    """Pull all finished ESPN WC events between start and end (inclusive)."""
    out = {"days": 0, "events": 0, "synced": 0, "players": 0, "errors": []}
    day = start
    while day <= end:
        out["days"] += 1
        try:
            for ev in fetch_scoreboard(day):
                if not _event_finished(ev):
                    continue
                out["events"] += 1
                parsed = _parse_event_teams(ev)
                if not parsed:
                    continue
                home, away, eid = parsed
                stats = ingest_summary(conn, eid, home, away, day)
                if stats.get("players"):
                    out["synced"] += 1
                    out["players"] += stats["players"]
                time.sleep(pause_sec)
        except Exception as e:
            out["errors"].append(f"{day}: {e!r}")
        day += timedelta(days=1)
        time.sleep(pause_sec)
    return out
