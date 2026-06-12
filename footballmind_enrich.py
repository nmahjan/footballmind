"""
FootballMind — free multi-source data enrichment.

Complements football-data.org (spine) with zero/low-cost feeds:
  - FPL bootstrap-static  → PL injury/doubt flags (official, no API key)
  - API-Football (free)   → injuries + per-match player ratings (optional key)
  - Understat             → match xG for top-5 leagues (no key)

Env:
  API_FOOTBALL_KEY   optional — api-sports.io key (100 req/day free tier)
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime, timezone

import requests

FPL_BASE = "https://fantasy.premierleague.com/api"
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
UNDERSTAT_BASE = "https://understat.com/main"

API_FOOTBALL_LEAGUES: dict[str, tuple[int, int]] = {
    # comp_code -> (league_id, season_start_year)
    "PL": (39, 2025),
    "PD": (140, 2025),
    "BL1": (78, 2025),
    "SA": (135, 2025),
    "FL1": (61, 2025),
    "CL": (2, 2025),
}

UNDERSTAT_LEAGUES: dict[str, tuple[str, int]] = {
    "PL": ("EPL", 2025),
    "PD": ("La_liga", 2025),
    "BL1": ("Bundesliga", 2025),
    "SA": ("Serie_A", 2025),
    "FL1": ("Ligue_1", 2025),
}

_FPL_STATUS = {
    "i": "injured",
    "d": "doubtful",
    "u": "injured",
    "n": "doubtful",
}

# FPL short names → football-data.org team names
_FPL_TEAM_NAMES = {
    "Man City": "Manchester City FC",
    "Man Utd": "Manchester United FC",
    "Nott'm Forest": "Nottingham Forest FC",
    "Spurs": "Tottenham Hotspur FC",
    "West Ham": "West Ham United FC",
    "Wolves": "Wolverhampton Wanderers FC",
    "Newcastle": "Newcastle United FC",
    "Brighton": "Brighton & Hove Albion FC",
    "Bournemouth": "AFC Bournemouth",
    "Sunderland": "Sunderland AFC",
    "Leeds": "Leeds United FC",
}


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("ø", "o"), ("Ø", "o"), ("æ", "ae"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _get_json(url: str, headers: dict | None = None, timeout: int = 25) -> dict | list:
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _store_provider_id(cur, entity_type: str, entity_id: int,
                       provider: str, external_id: str) -> None:
    cur.execute(
        "INSERT INTO provider_external_ids "
        "(entity_type, entity_id, provider, external_id) "
        "VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (entity_type, entity_id, provider) DO UPDATE SET "
        "  external_id = EXCLUDED.external_id",
        (entity_type, entity_id, provider, str(external_id)))


def _resolve_team_id(cur, name: str) -> int | None:
    from footballmind_mcp_predict import _resolve_team

    try:
        team_id, _ = _resolve_team(cur, name)
        return team_id
    except ValueError:
        return None


def _resolve_player_on_team(cur, team_id: int, *names: str) -> int | None:
    from footballmind_services import _resolve_player_on_team

    for name in names:
        if not name:
            continue
        found = _resolve_player_on_team(cur, name, team_id)
        if found:
            return found[0]
    # Last name only
    for name in names:
        if not name or " " not in name.strip():
            continue
        last = name.strip().split()[-1]
        found = _resolve_player_on_team(cur, last, team_id)
        if found:
            return found[0]
    return None


def _fpl_team_name(fpl_team: dict) -> str:
    raw = fpl_team.get("name") or ""
    return _FPL_TEAM_NAMES.get(raw, f"{raw} FC" if raw and not raw.endswith(" FC") else raw)


def sync_fpl_availability(conn) -> int:
    """Pull PL injury/doubt flags from the official FPL API (free, no key)."""
    data = _get_json(f"{FPL_BASE}/bootstrap-static/")
    teams = {t["id"]: t for t in data.get("teams") or []}
    n = 0
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM player_availability "
            "WHERE comp_code = 'PL' AND source = 'fpl'")
        for el in data.get("elements") or []:
            status_code = (el.get("status") or "a").lower()
            if status_code == "a":
                continue
            status = _FPL_STATUS.get(status_code)
            if not status:
                continue
            team = teams.get(el.get("team"))
            if not team:
                continue
            team_id = _resolve_team_id(cur, _fpl_team_name(team))
            if not team_id:
                continue
            web = el.get("web_name") or ""
            full = f"{el.get('first_name', '')} {el.get('second_name', '')}".strip()
            player_id = _resolve_player_on_team(cur, team_id, full, web)
            if not player_id:
                continue
            reason = (el.get("news") or "").strip() or status
            chance = el.get("chance_of_playing_next_round")
            if chance is not None and int(chance) < 100:
                reason = f"{reason} ({chance}% chance)".strip()
            cur.execute(
                "INSERT INTO player_availability "
                "(player_id, team_id, comp_code, status, reason, source, updated_at) "
                "VALUES (%s,%s,'PL',%s,%s,'fpl',now()) "
                "ON CONFLICT (player_id, team_id, comp_code) DO UPDATE SET "
                "  status = EXCLUDED.status, reason = EXCLUDED.reason, "
                "  source = EXCLUDED.source, updated_at = now() "
                "WHERE player_availability.source != 'manual'",
                (player_id, team_id, status, reason[:500]))
            _store_provider_id(cur, "player", player_id, "fpl", str(el["id"]))
            n += 1
    conn.commit()
    return n


class ApiFootballClient:
    def __init__(self, api_key: str):
        self.headers = {"x-apisports-key": api_key}

    def get(self, path: str, params: dict | None = None) -> dict:
        r = requests.get(
            f"{API_FOOTBALL_BASE}{path}",
            headers=self.headers,
            params=params or {},
            timeout=25,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(str(data["errors"]))
        return data

    def injuries(self, league_id: int, season: int) -> list:
        data = self.get("/injuries", {"league": league_id, "season": season})
        return data.get("response") or []

    def fixtures_last(self, league_id: int, season: int, last: int = 5) -> list:
        data = self.get("/fixtures", {
            "league": league_id, "season": season, "last": last,
        })
        return data.get("response") or []

    def fixture_players(self, fixture_id: int) -> list:
        data = self.get("/fixtures/players", {"fixture": fixture_id})
        return data.get("response") or []

    def fixture_lineups(self, fixture_id: int) -> list:
        data = self.get("/fixtures/lineups", {"fixture": fixture_id})
        return data.get("response") or []


def _match_team_names(cur, match_id: int) -> tuple[str, str, date | None]:
    cur.execute(
        "SELECT th.name, ta.name, m.match_date::date "
        "FROM matches m "
        "JOIN teams th ON th.id = m.home_team_id "
        "JOIN teams ta ON ta.id = m.away_team_id "
        "WHERE m.id = %s",
        (match_id,))
    row = cur.fetchone()
    return row if row else ("", "", None)


def _find_match_for_fixture(cur, comp_code: str, home_name: str, away_name: str,
                            fixture_date: str) -> int | None:
    cur.execute(
        "SELECT m.id, th.name, ta.name "
        "FROM matches m "
        "JOIN teams th ON th.id = m.home_team_id "
        "JOIN teams ta ON ta.id = m.away_team_id "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s AND m.match_date::date = %s::date "
        "  AND m.home_goals IS NOT NULL",
        (comp_code, fixture_date[:10]))
    nh, na = _norm(home_name), _norm(away_name)
    for mid, th, ta in cur.fetchall():
        if _norm(th) == nh and _norm(ta) == na:
            return mid
        if nh in _norm(th) and na in _norm(ta):
            return mid
    return None


def sync_api_football_injuries(conn, client: ApiFootballClient,
                               comp_code: str) -> int:
    cfg = API_FOOTBALL_LEAGUES.get(comp_code)
    if not cfg:
        return 0
    league_id, season = cfg
    n = 0
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM player_availability "
            "WHERE comp_code = %s AND source = 'api_football'",
            (comp_code,))
        for row in client.injuries(league_id, season):
            player = row.get("player") or {}
            team = row.get("team") or {}
            team_id = _resolve_team_id(cur, team.get("name") or "")
            if not team_id:
                continue
            pname = player.get("name") or ""
            player_id = _resolve_player_on_team(cur, team_id, pname)
            if not player_id:
                continue
            reason = (row.get("reason") or row.get("type") or "injured").strip()
            cur.execute(
                "INSERT INTO player_availability "
                "(player_id, team_id, comp_code, status, reason, source, updated_at) "
                "VALUES (%s,%s,%s,'injured',%s,'api_football',now()) "
                "ON CONFLICT (player_id, team_id, comp_code) DO UPDATE SET "
                "  status = EXCLUDED.status, reason = EXCLUDED.reason, "
                "  source = EXCLUDED.source, updated_at = now() "
                "WHERE player_availability.source != 'manual'",
                (player_id, team_id, comp_code, reason[:500]))
            if player.get("id"):
                _store_provider_id(cur, "player", player_id, "api_football",
                                   str(player["id"]))
            n += 1
    conn.commit()
    return n


def sync_api_football_ratings(conn, client: ApiFootballClient,
                              comp_code: str, last_n: int = 5) -> int:
    cfg = API_FOOTBALL_LEAGUES.get(comp_code)
    if not cfg:
        return 0
    league_id, season = cfg
    n = 0
    with conn.cursor() as cur:
        for fix in client.fixtures_last(league_id, season, last=last_n):
            fid = fix["fixture"]["id"]
            fdate = (fix["fixture"].get("date") or "")[:10]
            home = (fix.get("teams") or {}).get("home") or {}
            away = (fix.get("teams") or {}).get("away") or {}
            match_id = _find_match_for_fixture(
                cur, comp_code, home.get("name", ""), away.get("name", ""), fdate)
            if not match_id:
                continue
            _store_provider_id(cur, "match", match_id, "api_football", str(fid))
            try:
                teams_data = client.fixture_players(fid)
            except RuntimeError:
                continue
            for side in teams_data:
                team_name = (side.get("team") or {}).get("name") or ""
                team_id = _resolve_team_id(cur, team_name)
                if not team_id:
                    continue
                for row in side.get("players") or []:
                    pinfo = row.get("player") or {}
                    stats = row.get("statistics") or [{}]
                    stat = stats[0] if stats else {}
                    rating_raw = stat.get("games", {}).get("rating")
                    if not rating_raw:
                        continue
                    try:
                        rating = float(rating_raw)
                    except (TypeError, ValueError):
                        continue
                    minutes = stat.get("games", {}).get("minutes")
                    pname = pinfo.get("name") or ""
                    player_id = _resolve_player_on_team(cur, team_id, pname)
                    if not player_id:
                        continue
                    cur.execute(
                        "INSERT INTO match_player_ratings "
                        "(match_id, player_id, rating, minutes, source, synced_at) "
                        "VALUES (%s,%s,%s,%s,'api_football',now()) "
                        "ON CONFLICT (match_id, player_id, source) DO UPDATE SET "
                        "  rating = EXCLUDED.rating, minutes = EXCLUDED.minutes, "
                        "  synced_at = now()",
                        (match_id, player_id, rating, minutes))
                    if pinfo.get("id"):
                        _store_provider_id(cur, "player", player_id, "api_football",
                                           str(pinfo["id"]))
                    n += 1
    conn.commit()
    return n


def _parse_understat_matches(raw: dict) -> list[dict]:
    dates = raw.get("dates")
    if isinstance(dates, str):
        return json.loads(dates)
    if isinstance(dates, list):
        return dates
    return []


def sync_understat_xg(conn, comp_code: str) -> int:
    """Batch xG from Understat for finished matches (top-5 leagues, free)."""
    cfg = UNDERSTAT_LEAGUES.get(comp_code)
    if not cfg:
        return 0
    league_key, season = cfg
    raw = _get_json(f"{UNDERSTAT_BASE}/getMatches?league={league_key}&season={season}")
    matches = _parse_understat_matches(raw)
    n = 0
    with conn.cursor() as cur:
        for m in matches:
            if not m.get("isResult"):
                continue
            try:
                hxg = float(m.get("xG", {}).get("h") or 0)
                axg = float(m.get("xG", {}).get("a") or 0)
            except (TypeError, ValueError):
                continue
            home = (m.get("h") or {}).get("title") or ""
            away = (m.get("a") or {}).get("title") or ""
            dt = (m.get("datetime") or "")[:10]
            if not dt:
                continue
            match_id = _find_match_for_fixture(cur, comp_code, home, away, dt)
            if not match_id:
                continue
            cur.execute(
                "UPDATE matches SET home_xg = %s, away_xg = %s, xg_source = 'understat' "
                "WHERE id = %s AND (home_xg IS NULL OR xg_source = 'understat')",
                (hxg, axg, match_id))
            if m.get("id"):
                _store_provider_id(cur, "match", match_id, "understat", str(m["id"]))
            n += 1
    conn.commit()
    return n


def sync_enrichment(conn, comps: list[str] | None = None) -> dict[str, int]:
    """Run all free enrichment feeds. API-Football skipped if no key set."""
    comps = comps or ["PL", "PD", "BL1", "SA", "FL1"]
    out: dict[str, int] = {}

    out["fpl_availability"] = sync_fpl_availability(conn)

    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if api_key:
        client = ApiFootballClient(api_key)
        inj_total = rat_total = 0
        for code in comps:
            if code == "PL":
                continue  # FPL is richer for PL injuries
            try:
                inj_total += sync_api_football_injuries(conn, client, code)
            except Exception:
                pass
            try:
                rat_total += sync_api_football_ratings(conn, client, code, last_n=3)
            except Exception:
                pass
        # PL ratings only (no duplicate injury source)
        try:
            rat_total += sync_api_football_ratings(conn, client, "PL", last_n=5)
        except Exception:
            pass
        out["api_football_injuries"] = inj_total
        out["api_football_ratings"] = rat_total
    else:
        out["api_football_injuries"] = 0
        out["api_football_ratings"] = 0

    xg_total = 0
    for code in comps:
        if code not in UNDERSTAT_LEAGUES:
            continue
        try:
            xg_total += sync_understat_xg(conn, code)
        except Exception:
            pass
    out["understat_xg"] = xg_total
    return out


def get_match_ratings(conn, match_id: int) -> dict[int, float]:
    """player_id -> rating for a match (best source available)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT player_id, rating::float FROM match_player_ratings "
            "WHERE match_id = %s ORDER BY synced_at DESC",
            (match_id,))
        out: dict[int, float] = {}
        for pid, rating in cur.fetchall():
            if pid not in out and rating is not None:
                out[pid] = rating
        return out
