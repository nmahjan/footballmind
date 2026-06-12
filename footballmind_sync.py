"""
FootballMind -- ingestion / sync job.

Pulls fixtures, results, and squads from football-data.org, upserts them, and
applies finished matches to the Elo ratings -- in the correct order and exactly
once. Run on a schedule (e.g. every 6 hours).

The idempotent upserts need the partial unique indexes on matches(external_id)
and players(external_id) -- applied by migrations/003_external_unique_indexes.sql.
"""

import time
from datetime import date
from threading import Lock

import requests

from footballmind_elo import apply_match_result
from footballmind_services import normalize_position

# football-data.org stage strings -> our match_stage enum
STAGE_MAP = {
    "REGULAR_SEASON": "regular_season", "GROUP_STAGE": "group",
    "LAST_32": "round_of_32", "LAST_16": "round_of_16",
    "QUARTER_FINALS": "quarter_final", "SEMI_FINALS": "semi_final",
    "THIRD_PLACE": "third_place", "FINAL": "final",
}
# competition code -> Elo importance weight
IMPORTANCE_BY_COMP = {"PL": "league", "CL": "continental", "WC": "world_cup"}


# ----------------------------------------------------------------------
# Rate limiting: token bucket sized to the free tier (10 requests / minute)
# ----------------------------------------------------------------------
class TokenBucket:
    def __init__(self, rate_per_min: int):
        self.capacity = rate_per_min
        self.tokens = float(rate_per_min)
        self.refill_per_sec = rate_per_min / 60.0
        self.last = time.monotonic()
        self.lock = Lock()

    def take(self) -> None:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity,
                              self.tokens + (now - self.last) * self.refill_per_sec)
            self.last = now
            if self.tokens < 1:
                time.sleep((1 - self.tokens) / self.refill_per_sec)
                self.tokens = 0.0
            else:
                self.tokens -= 1


class FootballDataClient:
    BASE = "https://api.football-data.org/v4"

    def __init__(self, api_key: str, bucket: TokenBucket):
        self.session = requests.Session()
        self.session.headers["X-Auth-Token"] = api_key
        self.bucket = bucket

    def _throttle_from_headers(self, headers) -> None:
        """The server's view of the quota is authoritative: clamp the local
        bucket to X-Requests-Available-Minute, and if the minute is exhausted
        sleep until the counter resets instead of bouncing off a 429."""
        avail = headers.get("X-Requests-Available-Minute")
        if avail is None:
            return
        with self.bucket.lock:
            self.bucket.tokens = min(self.bucket.tokens, float(avail))
        if int(avail) == 0:
            time.sleep(float(headers.get("X-RequestCounter-Reset", 60)) + 1)

    def _get(self, path: str, params=None) -> dict:
        self.bucket.take()                     # blocks until a token is free
        for attempt in (1, 2):
            r = self.session.get(f"{self.BASE}{path}", params=params, timeout=20)
            if r.status_code == 429 and attempt == 1:
                wait = float(r.headers.get("X-RequestCounter-Reset",
                                           r.headers.get("Retry-After", 60)))
                time.sleep(wait + 1)
                continue
            r.raise_for_status()
            self._throttle_from_headers(r.headers)
            return r.json()

    def matches(self, comp, status=None, date_from=None, date_to=None):
        params = {}
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        elif date_from:
            params["dateTo"] = date.today().isoformat()
        return self._get(f"/competitions/{comp}/matches", params).get("matches", [])

    def teams(self, comp):
        return self._get(f"/competitions/{comp}/teams").get("teams", [])

    def scorers(self, comp, limit=100, season=None):
        params = {"limit": limit}
        if season is not None:
            params["season"] = season
        return self._get(f"/competitions/{comp}/scorers", params).get("scorers", [])

    def match(self, match_id):
        return self._get(f"/matches/{match_id}")


# ----------------------------------------------------------------------
# Upserts (idempotent -- re-running the sync never double-writes)
# ----------------------------------------------------------------------
def upsert_team(cur, name, team_type, external_id, country_id=None):
    cur.execute(
        "INSERT INTO teams (name, type, external_id, country_id) "
        "VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (name, type) DO UPDATE SET external_id = EXCLUDED.external_id, "
        "  country_id = COALESCE(EXCLUDED.country_id, teams.country_id) "
        "RETURNING id", (name, team_type, str(external_id), country_id))
    return cur.fetchone()[0]


def upsert_country(cur, name, fifa_code=None):
    if not name:
        return None
    cur.execute(
        "INSERT INTO countries (name, fifa_code) VALUES (%s,%s) "
        "ON CONFLICT (name) DO UPDATE SET "
        "  fifa_code = COALESCE(EXCLUDED.fifa_code, countries.fifa_code) "
        "RETURNING id", (name, fifa_code))
    return cur.fetchone()[0]


def get_or_create_edition(cur, comp_code, comp_name, comp_type, season):
    cur.execute("INSERT INTO competitions (name, code, type) VALUES (%s,%s,%s) "
                "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                (comp_name, comp_code, comp_type))
    comp_id = cur.fetchone()[0]
    cur.execute("INSERT INTO competition_editions (competition_id, season) "
                "VALUES (%s,%s) ON CONFLICT (competition_id, season) "
                "DO UPDATE SET season = EXCLUDED.season RETURNING id", (comp_id, season))
    return cur.fetchone()[0]


def upsert_match(cur, edition_id, m, team_type):
    """Insert/update one match row. Does NOT touch ratings (that is staged
    separately so it happens in chronological order, exactly once).
    Knockout fixtures whose participants are not yet decided (TBD slots with
    null team names) are skipped; later syncs pick them up once known."""
    if not m["homeTeam"].get("name") or not m["awayTeam"].get("name"):
        return
    home_id = upsert_team(cur, m["homeTeam"]["name"], team_type, m["homeTeam"]["id"])
    away_id = upsert_team(cur, m["awayTeam"]["name"], team_type, m["awayTeam"]["id"])
    stage = STAGE_MAP.get(m.get("stage", "REGULAR_SEASON"), "regular_season")
    ft = (m.get("score") or {}).get("fullTime") or {}
    group_name = m.get("group")   # e.g. "GROUP_A" from football-data.org
    if group_name:
        # normalise "GROUP_A" -> "A"
        group_name = group_name.replace("GROUP_", "").replace("Group ", "").strip()
    cur.execute(
        "INSERT INTO matches (edition_id, stage, match_date, home_team_id, "
        " away_team_id, home_goals, away_goals, external_id, group_name) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO UPDATE SET "
        "  home_goals = EXCLUDED.home_goals, away_goals = EXCLUDED.away_goals, "
        "  stage = EXCLUDED.stage, group_name = EXCLUDED.group_name",
        (edition_id, stage, m["utcDate"], home_id, away_id,
         ft.get("home"), ft.get("away"), str(m["id"]), group_name))


# ----------------------------------------------------------------------
# The two correctness-critical steps
# ----------------------------------------------------------------------
def apply_pending_ratings(conn, comp_code):
    """Apply finished-but-not-yet-rated matches for one competition, oldest first."""
    importance = IMPORTANCE_BY_COMP.get(comp_code, "league")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = %s AND m.home_goals IS NOT NULL "
            "  AND NOT EXISTS (SELECT 1 FROM rating_history rh "
            "                  WHERE rh.match_id = m.id) "
            "ORDER BY m.match_date ASC",
            (comp_code,))
        pending = [row[0] for row in cur.fetchall()]
    for match_id in pending:
        apply_match_result(conn, match_id, importance)


def sync_competition(conn, client, comp_code, comp_name, comp_type, season,
                     team_type="club", since=None):
    """Full sync for one competition: matches (results AND upcoming fixtures,
    so predictions can link to real fixtures) -> upsert -> rate finished ones."""
    fetched = client.matches(comp_code, status=None, date_from=since)
    with conn.cursor() as cur:
        edition_id = get_or_create_edition(cur, comp_code, comp_name, comp_type, season)
        for m in fetched:
            upsert_match(cur, edition_id, m, team_type)
    conn.commit()
    apply_pending_ratings(conn, comp_code)               # chronological + once


def sync_teams_and_squads(conn, client, comp_code, team_type="club"):
    """One API call per competition: upsert every team (with its country) and
    its full squad (players + club/national affiliations)."""
    kind = "national" if team_type == "national" else "club"
    teams = client.teams(comp_code)
    with conn.cursor() as cur:
        for t in teams:
            area = t.get("area") or {}
            country_id = upsert_country(cur, area.get("name"),
                                        t.get("tla") if kind == "national" else None)
            team_id = upsert_team(cur, t["name"], team_type, t["id"], country_id)
            sync_squad(cur, t.get("squad") or [], team_id, kind)
    conn.commit()
    return len(teams)


# ----------------------------------------------------------------------
# Squads -> players + dual affiliations
# ----------------------------------------------------------------------
def sync_squad(cur, squad, team_id, kind):
    """Upsert players and set their CLUB or NATIONAL affiliation to team_id,
    closing a prior open stint of the same kind if they moved. The DB's
    exclusion constraint guarantees no overlapping same-kind stints."""
    today = date.today()
    for p in squad:
        nationality_id = upsert_country(cur, p.get("nationality"))
        pos = normalize_position(p.get("position"))
        cur.execute(
            "INSERT INTO players (name, external_id, birth_date, nationality, position) "
            "VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (external_id) WHERE external_id IS NOT NULL "
            "DO UPDATE SET name = EXCLUDED.name, "
            "  birth_date = COALESCE(EXCLUDED.birth_date, players.birth_date), "
            "  nationality = COALESCE(EXCLUDED.nationality, players.nationality), "
            "  position = COALESCE(EXCLUDED.position, players.position) "
            "RETURNING id",
            (p["name"], str(p["id"]), p.get("dateOfBirth"), nationality_id, pos))
        player_id = cur.fetchone()[0]

        cur.execute("SELECT id, team_id FROM player_affiliations "
                    "WHERE player_id = %s AND kind = %s AND end_date IS NULL",
                    (player_id, kind))
        open_row = cur.fetchone()
        if open_row and open_row[1] == team_id:
            continue                                     # already correct
        if open_row:                                     # moved -> close old stint
            cur.execute("UPDATE player_affiliations SET end_date = %s WHERE id = %s",
                        (today, open_row[0]))
        cur.execute("INSERT INTO player_affiliations "
                    "(player_id, team_id, kind, start_date) VALUES (%s,%s,%s,%s)",
                    (player_id, team_id, kind, today))


# ----------------------------------------------------------------------
# Scorers + match detail (lineups / events when API provides them)
# ----------------------------------------------------------------------
_EVENT_MAP = {
    "REGULAR": "GOAL", "OWN": "OWN_GOAL", "PENALTY": "PENALTY",
    "YELLOW": "YELLOW_CARD", "RED": "RED_CARD", "YELLOW_RED": "RED_CARD",
}


def _edition_id(cur, comp_code, season):
    cur.execute(
        "SELECT e.id FROM competition_editions e "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s AND e.season = %s",
        (comp_code, season))
    row = cur.fetchone()
    return row[0] if row else None


def upsert_player_row(cur, p, team_id, kind):
    """Upsert one API player object; ensure affiliation to team_id."""
    nationality_id = upsert_country(cur, p.get("nationality"))
    pos = normalize_position(p.get("position") or p.get("section"))
    ext = p.get("id")
    if ext is None:
        return None
    cur.execute(
        "INSERT INTO players (name, external_id, birth_date, nationality, position) "
        "VALUES (%s,%s,%s,%s,%s) "
        "ON CONFLICT (external_id) WHERE external_id IS NOT NULL "
        "DO UPDATE SET name = EXCLUDED.name, "
        "  birth_date = COALESCE(EXCLUDED.birth_date, players.birth_date), "
        "  nationality = COALESCE(EXCLUDED.nationality, players.nationality), "
        "  position = COALESCE(EXCLUDED.position, players.position) "
        "RETURNING id",
        (p["name"], str(ext), p.get("dateOfBirth"), nationality_id, pos))
    player_id = cur.fetchone()[0]
    today = date.today()
    cur.execute("SELECT id, team_id FROM player_affiliations "
                "WHERE player_id = %s AND kind = %s AND end_date IS NULL",
                (player_id, kind))
    open_row = cur.fetchone()
    if open_row and open_row[1] == team_id:
        return player_id
    if open_row:
        cur.execute("UPDATE player_affiliations SET end_date = %s WHERE id = %s",
                    (today, open_row[0]))
    cur.execute("INSERT INTO player_affiliations "
                "(player_id, team_id, kind, start_date) VALUES (%s,%s,%s,%s)",
                (player_id, team_id, kind, today))
    return player_id


def sync_scorers(conn, client, comp_code, season, team_type="club",
                 comp_name=None, comp_type=None):
    """Pull competition top scorers -> player_edition_stats."""
    kind = "national" if team_type == "national" else "club"
    year = int(season.split("/")[0]) if "/" in season else int(season)
    rows = client.scorers(comp_code, season=year)
    with conn.cursor() as cur:
        if comp_name and comp_type:
            edition_id = get_or_create_edition(cur, comp_code, comp_name, comp_type, season)
        else:
            edition_id = _edition_id(cur, comp_code, season)
        if edition_id is None:
            return 0
        n = 0
        for row in rows:
            player = row.get("player") or {}
            team = row.get("team") or {}
            if not player.get("name") or not team.get("name"):
                continue
            team_id = upsert_team(cur, team["name"], team_type, team["id"])
            player_id = upsert_player_row(cur, player, team_id, kind)
            if not player_id:
                continue
            cur.execute(
                "INSERT INTO player_edition_stats "
                "(player_id, edition_id, team_id, goals, assists, appearances, penalties) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (player_id, edition_id) DO UPDATE SET "
                "  team_id = EXCLUDED.team_id, goals = EXCLUDED.goals, "
                "  assists = EXCLUDED.assists, appearances = EXCLUDED.appearances, "
                "  penalties = EXCLUDED.penalties, synced_at = now()",
                (player_id, edition_id, team_id,
                 row.get("goals") or 0, row.get("assists") or 0,
                 row.get("playedMatches") or 0, row.get("penalties") or 0))
            n += 1
    conn.commit()
    return n


def _resolve_player_id(cur, p, team_id, kind):
    if not p or not p.get("name"):
        return None
    if p.get("id"):
        return upsert_player_row(cur, p, team_id, kind)
    cur.execute("SELECT id FROM players WHERE lower(name) = lower(%s) LIMIT 1",
                (p["name"],))
    row = cur.fetchone()
    return row[0] if row else None


def _sync_side_lineup(cur, match_id, team_side, team_type, kind):
    team_api = team_side or {}
    team_id = upsert_team(cur, team_api["name"], team_type, team_api["id"])
    formation = team_api.get("formation")
    if formation:
        cur.execute(
            "INSERT INTO match_team_lineups (match_id, team_id, formation) "
            "VALUES (%s,%s,%s) "
            "ON CONFLICT (match_id, team_id) DO UPDATE SET formation = EXCLUDED.formation",
            (match_id, team_id, formation))
    for role, players in (("starter", team_api.get("lineup") or []),
                          ("bench", team_api.get("bench") or [])):
        for p in players:
            player_id = _resolve_player_id(cur, p, team_id, kind)
            if not player_id:
                continue
            pos = normalize_position(p.get("position"))
            cur.execute(
                "INSERT INTO match_lineup_players "
                "(match_id, team_id, player_id, role, shirt_number, position) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (match_id, team_id, player_id) DO UPDATE SET "
                "  role = EXCLUDED.role, shirt_number = EXCLUDED.shirt_number, "
                "  position = COALESCE(EXCLUDED.position, match_lineup_players.position)",
                (match_id, team_id, player_id, role,
                 p.get("shirtNumber"), pos))


def _sync_match_events(cur, match_id, m, team_type, kind):
    cur.execute("DELETE FROM match_events WHERE match_id = %s", (match_id,))
    cur.execute("DELETE FROM match_lineup_players WHERE match_id = %s", (match_id,))
    cur.execute("DELETE FROM match_team_lineups WHERE match_id = %s", (match_id,))

    for side in ("homeTeam", "awayTeam"):
        team_api = m.get(side) or {}
        team_id = upsert_team(cur, team_api["name"], team_type, team_api["id"])
        _sync_side_lineup(cur, match_id, team_api, team_type, kind)

    for goal in m.get("goals") or []:
        team_api = goal.get("team") or {}
        team_id = upsert_team(cur, team_api["name"], team_type, team_api["id"]) \
            if team_api.get("name") else None
        scorer_id = _resolve_player_id(cur, goal.get("scorer"), team_id, kind) \
            if team_id else None
        assist_id = _resolve_player_id(cur, goal.get("assist"), team_id, kind) \
            if team_id else None
        etype = _EVENT_MAP.get(goal.get("type", "REGULAR"), "GOAL")
        cur.execute(
            "INSERT INTO match_events "
            "(match_id, team_id, player_id, assist_player_id, event_type, minute) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (match_id, team_id, scorer_id, assist_id, etype, goal.get("minute")))

    for booking in m.get("bookings") or []:
        team_api = booking.get("team") or {}
        team_id = upsert_team(cur, team_api["name"], team_type, team_api["id"]) \
            if team_api.get("name") else None
        player_id = _resolve_player_id(cur, booking.get("player"), team_id, kind) \
            if team_id else None
        etype = _EVENT_MAP.get(booking.get("card", "YELLOW"), "YELLOW_CARD")
        cur.execute(
            "INSERT INTO match_events "
            "(match_id, team_id, player_id, event_type, minute) "
            "VALUES (%s,%s,%s,%s,%s)",
            (match_id, team_id, player_id, etype, booking.get("minute")))

    for sub in m.get("substitutions") or []:
        team_api = sub.get("team") or {}
        team_id = upsert_team(cur, team_api["name"], team_type, team_api["id"]) \
            if team_api.get("name") else None
        out_id = _resolve_player_id(cur, sub.get("playerOut"), team_id, kind) \
            if team_id else None
        cur.execute(
            "INSERT INTO match_events "
            "(match_id, team_id, player_id, event_type, minute, detail) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (match_id, team_id, out_id, "SUBSTITUTION", sub.get("minute"),
             (sub.get("playerIn") or {}).get("name")))


def sync_match_details(conn, client, limit=20):
    """Fetch /matches/{id} for finished games missing detail sync.

    Free tier often omits lineups/goals; those rows are marked synced anyway
    so we do not burn quota re-fetching them every run.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, m.external_id, c.code, t.type "
            "FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams t ON t.id = m.home_team_id "
            "WHERE m.home_goals IS NOT NULL AND m.details_synced = FALSE "
            "  AND m.external_id IS NOT NULL "
            "ORDER BY m.match_date DESC LIMIT %s",
            (limit,))
        pending = cur.fetchall()

    synced = 0
    for match_id, external_id, _comp, team_type in pending:
        kind = "national" if team_type == "national" else "club"
        try:
            m = client.match(external_id)
        except Exception:
            continue
        has_detail = bool(m.get("goals") or (m.get("homeTeam") or {}).get("lineup"))
        with conn.cursor() as cur:
            if has_detail:
                _sync_match_events(cur, match_id, m, team_type, kind)
            cur.execute("UPDATE matches SET details_synced = TRUE WHERE id = %s",
                        (match_id,))
        conn.commit()
        synced += 1
    return synced


if __name__ == "__main__":
    # Sketch of a scheduled run (provide your own psycopg connection + key):
    #   bucket = TokenBucket(10)
    #   client = FootballDataClient(API_KEY, bucket)
    #   sync_competition(conn, client, "PL", "Premier League",
    #                    "domestic_league", "2025/26", team_type="club")
    #   sync_competition(conn, client, "WC", "FIFA World Cup",
    #                    "international", "2026", team_type="national")
    pass
