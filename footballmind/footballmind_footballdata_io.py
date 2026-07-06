"""
FootballMind — optional enrichment via Footballdata.io.

Populates players.line_role from squad endpoints when football-data.org
positions are coarse ("Offence") and SoFIFA has not synced yet.

Env:
    FOOTBALLDATA_IO_KEY   Bearer token from https://footballdata.io
"""

from __future__ import annotations

import os
import re
from typing import Any

import requests

from footballmind_roles import LINE_ROLES, map_sofifa_position

# Footballdata.io league ids (NOT the same as API-Football)
LEAGUE_BY_COMP: dict[str, int] = {
    "PL": 15,
    "CL": 45,
    "WC": 50,
    # Other comps: resolve via /search instead of league roster (IDs differ from API-Football).
}

# Footballdata.io display names → football-data.org names in our DB
TEAM_NAME_ALIASES: dict[str, str] = {
    "Arsenal": "Arsenal FC",
    "Manchester City": "Manchester City FC",
    "Manchester United": "Manchester United FC",
    "Tottenham": "Tottenham Hotspur FC",
    "Spurs": "Tottenham Hotspur FC",
    "Newcastle": "Newcastle United FC",
    "Brighton": "Brighton & Hove Albion FC",
    "West Ham": "West Ham United FC",
    "Wolves": "Wolverhampton Wanderers FC",
    "Nottingham Forest": "Nottingham Forest FC",
    "Bournemouth": "AFC Bournemouth",
    "Leeds": "Leeds United FC",
    "Spain": "Spain",
    "Argentina": "Argentina",
    "England": "England",
    "France": "France",
}

_BASE_URLS = (
    "https://footballdata.io/api/v1",
    "https://api.footballdata.io/api/v1",
    "https://api.footballdata.io/v1",
)


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _unwrap(payload: dict | list | None) -> list | dict | None:
    if payload is None:
        return None
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return payload
    if payload.get("success") is False:
        err = payload.get("error") or {}
        raise RuntimeError(err.get("message") or err.get("code") or "API error")
    data = payload.get("data", payload)
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return data


class FootballdataIoClient:
    def __init__(self, api_key: str, *, base_url: str | None = None):
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        self.base_url = base_url or _pick_base_url(self.api_key)

    def get(self, path: str, **params) -> dict | list:
        path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params or None, timeout=25)
        r.raise_for_status()
        return r.json()

    def account_usage(self) -> dict:
        return self.get("/account/usage")

    def search(self, q: str, *, limit: int = 10) -> list[dict]:
        raw = self.get("/search", q=q, limit=limit)
        data = _unwrap(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, dict):
                out: list[dict] = []
                for key in ("teams", "players", "matches", "leagues"):
                    for item in results.get(key) or []:
                        if isinstance(item, dict):
                            item = {**item, "type": item.get("type") or key.rstrip("s")}
                            out.append(item)
                return out
            for key in ("teams", "players", "results", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def league_teams(self, league_id: int, *, season: int | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if season:
            params["season"] = season
        raw = self.get(f"/leagues/{league_id}/teams", **params)
        data = _unwrap(raw)
        return data if isinstance(data, list) else []

    def team_players(self, team_id: int | str, *, limit: int = 100) -> list[dict]:
        raw = self.get(f"/teams/{team_id}/players", limit=limit)
        data = _unwrap(raw)
        return data if isinstance(data, list) else []

    def player(self, player_id: int | str) -> dict | None:
        raw = self.get(f"/players/{player_id}")
        data = _unwrap(raw)
        return data if isinstance(data, dict) else None


def _pick_base_url(api_key: str) -> str:
    """Use first base URL that responds (docs list two hostnames)."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key.strip()}"
    for base in _BASE_URLS:
        try:
            r = session.get(f"{base}/meta/status", timeout=12)
            if r.status_code < 500:
                return base
        except requests.RequestException:
            continue
    return _BASE_URLS[0]


def extract_position_raw(player: dict) -> str | None:
    """Best-effort position string from a Footballdata.io player object."""
    for key in (
        "position", "primary_position", "position_code", "position_name",
        "role", "detailed_position", "main_position",
    ):
        val = player.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for sub in ("code", "name", "short", "abbreviation"):
                if isinstance(val.get(sub), str) and val[sub].strip():
                    return val[sub].strip()
    return None


def map_footballdata_position(raw: str | None) -> str | None:
    """Map API position text/code to lineup slot (ST, WING, LB, …)."""
    if not raw:
        return None
    code = map_sofifa_position(re.sub(r"[^A-Za-z]", "", raw))
    if code:
        return code
    s = raw.lower().replace("-", " ")
    if "striker" in s or "centre forward" in s or "center forward" in s:
        return "ST"
    if "winger" in s or ("wing" in s and "back" not in s):
        return "WING"
    from footballmind_services import classify_line_role

    role = classify_line_role(raw)
    return role if role in LINE_ROLES else None


def _resolve_fdio_team_id(client: FootballdataIoClient, team_name: str,
                          league_id: int | None) -> int | str | None:
    """Find Footballdata.io team id by name search or league roster."""
    query = team_name
    for hit in client.search(query, limit=15):
        if hit.get("type") not in (None, "team", "teams"):
            continue
        name = (hit.get("team_name") or hit.get("name") or hit.get("team")
                or hit.get("title") or hit.get("full_name") or "")
        tid = hit.get("team_id") or hit.get("id")
        if tid and (_norm(name) == _norm(team_name)
                    or _norm(team_name) in _norm(name)
                    or _norm(name) in _norm(team_name)):
            return tid

    if league_id is None:
        return None
    target = _norm(team_name)
    for t in client.league_teams(league_id):
        name = t.get("team_name") or t.get("name") or t.get("team") or ""
        if isinstance(t.get("team"), dict):
            name = t["team"].get("team_name") or t["team"].get("name") or name
        tid = t.get("team_id") or t.get("id")
        if isinstance(t.get("team"), dict):
            tid = t["team"].get("team_id") or tid
        if not tid:
            continue
        nn = _norm(name)
        if nn == target or target in nn or nn in target:
            return tid
    return None


def _resolve_db_team_name(cur, team_name: str) -> str | None:
    from footballmind_mcp_predict import _resolve_team

    try:
        _, _ = _resolve_team(cur, team_name)
        cur.execute("SELECT name FROM teams WHERE name ILIKE %s LIMIT 1", (team_name,))
        row = cur.fetchone()
        if row:
            return row[0]
    except ValueError:
        pass
    alias = TEAM_NAME_ALIASES.get(team_name, team_name)
    try:
        _resolve_team(cur, alias)
        return alias
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
    return None


def _store_provider_id(cur, entity_type: str, entity_id: int,
                       provider: str, external_id: str) -> None:
    cur.execute(
        "SELECT entity_id FROM provider_external_ids "
        "WHERE provider = %s AND external_id = %s",
        (provider, str(external_id)),
    )
    row = cur.fetchone()
    if row and row[0] != entity_id:
        return
    cur.execute(
        "INSERT INTO provider_external_ids "
        "(entity_type, entity_id, provider, external_id) "
        "VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (entity_type, entity_id, provider) DO UPDATE SET "
        "  external_id = EXCLUDED.external_id",
        (entity_type, entity_id, provider, str(external_id)),
    )


def sync_team_line_roles(
    conn,
    client: FootballdataIoClient,
    team_name: str,
    *,
    league_id: int | None = None,
) -> dict[str, int]:
    """Pull squad from Footballdata.io and write players.line_role where known."""
    stats = {"team": team_name, "api_players": 0, "matched": 0, "updated": 0, "skipped": 0}
    with conn.cursor() as cur:
        db_team = _resolve_db_team_name(cur, team_name)
        if not db_team:
            stats["error"] = "team_not_in_db"
            return stats
        from footballmind_mcp_predict import _resolve_team

        team_id, _ = _resolve_team(cur, db_team)
        fdio_tid = _resolve_fdio_team_id(client, team_name, league_id)
        if fdio_tid is None:
            fdio_tid = _resolve_fdio_team_id(client, db_team, league_id)
        if fdio_tid is None:
            stats["error"] = "team_not_on_footballdata_io"
            return stats

        _store_provider_id(cur, "team", team_id, "footballdata_io", str(fdio_tid))
        roster = client.team_players(fdio_tid)
        stats["api_players"] = len(roster)
        if not roster:
            stats["error"] = "empty_squad_on_plan"
            return stats

        for p in roster:
            raw_pos = extract_position_raw(p)
            line_role = map_footballdata_position(raw_pos)
            if not line_role:
                stats["skipped"] += 1
                continue
            names = [
                p.get("player_name"),
                p.get("name"),
                p.get("known_name"),
                p.get("full_name"),
                p.get("display_name"),
                " ".join(filter(None, [p.get("first_name"), p.get("last_name")])),
            ]
            pid = _resolve_player_on_team(cur, team_id, *names)
            if not pid:
                stats["skipped"] += 1
                continue
            stats["matched"] += 1
            fdio_pid = p.get("id") or p.get("player_id")
            if fdio_pid:
                _store_provider_id(cur, "player", pid, "footballdata_io", str(fdio_pid))
            cur.execute(
                "UPDATE players SET line_role = %s "
                "WHERE id = %s AND (line_role IS NULL OR line_role <> %s)",
                (line_role, pid, line_role),
            )
            if cur.rowcount:
                stats["updated"] += 1
    conn.commit()
    return stats


def sync_footballdata_io_line_roles(
    conn,
    *,
    teams: list[str] | None = None,
    comps: list[str] | None = None,
    max_teams: int | None = 10,
) -> dict[str, int | list]:
    """Sync line_role for configured club/national teams."""
    api_key = os.environ.get("FOOTBALLDATA_IO_KEY", "").strip()
    if not api_key:
        return {"error": "missing_key", "updated": 0}

    client = FootballdataIoClient(api_key)
    comps = comps or ["PL", "PD", "BL1", "SA", "FL1"]
    team_league: dict[str, int | None] = {}
    if teams:
        for t in teams:
            team_league[t] = None
    else:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT t.name, c.code FROM teams t "
                "JOIN player_affiliations pa ON pa.team_id = t.id AND pa.end_date IS NULL "
                "JOIN matches m ON m.home_team_id = t.id OR m.away_team_id = t.id "
                "JOIN competition_editions e ON e.id = m.edition_id "
                "JOIN competitions c ON c.id = e.competition_id "
                "WHERE c.code = ANY(%s) AND t.team_type = 'club' "
                "ORDER BY t.name",
                (comps,),
            )
            for name, code in cur.fetchall():
                team_league[name] = LEAGUE_BY_COMP.get(code)

    totals = {"teams": 0, "api_players": 0, "matched": 0, "updated": 0, "skipped": 0}
    details: list[dict] = []
    items = list(team_league.items())
    if max_teams is not None:
        items = items[:max_teams]
    for team_name, league_id in items:
        try:
            st = sync_team_line_roles(conn, client, team_name, league_id=league_id)
        except Exception as exc:
            st = {"team": team_name, "error": str(exc)}
        details.append(st)
        if "error" not in st:
            totals["teams"] += 1
        for k in ("api_players", "matched", "updated", "skipped"):
            totals[k] += int(st.get(k, 0) or 0)
    totals["details"] = details
    return totals


def probe_account() -> dict:
    """Quick connectivity check (for CLI)."""
    api_key = os.environ.get("FOOTBALLDATA_IO_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "FOOTBALLDATA_IO_KEY not set"}
    client = FootballdataIoClient(api_key)
    usage = _unwrap(client.account_usage())
    return {"ok": True, "base_url": client.base_url, "usage": usage}
