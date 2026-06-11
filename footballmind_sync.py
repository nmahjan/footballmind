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

    def matches(self, comp, status="FINISHED", date_from=None, date_to=None):
        params = {"status": status}
        if date_from: params["dateFrom"] = date_from
        if date_to:   params["dateTo"] = date_to
        return self._get(f"/competitions/{comp}/matches", params).get("matches", [])

    def teams(self, comp):
        return self._get(f"/competitions/{comp}/teams").get("teams", [])


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
    cur.execute(
        "INSERT INTO matches (edition_id, stage, match_date, home_team_id, "
        " away_team_id, home_goals, away_goals, external_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO UPDATE SET "
        "  home_goals = EXCLUDED.home_goals, away_goals = EXCLUDED.away_goals, "
        "  stage = EXCLUDED.stage",
        (edition_id, stage, m["utcDate"], home_id, away_id,
         ft.get("home"), ft.get("away"), str(m["id"])))


# ----------------------------------------------------------------------
# The two correctness-critical steps
# ----------------------------------------------------------------------
def apply_pending_ratings(conn, comp_code):
    """Apply every finished-but-not-yet-rated match to Elo, oldest first.

    Elo is sequential (each update depends on prior ratings) AND not
    idempotent (applying a match twice corrupts ratings). This query handles
    both: it selects only matches with NO rating_history yet, ordered by date,
    so each match is rated exactly once, in chronological order."""
    importance = IMPORTANCE_BY_COMP.get(comp_code, "league")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id FROM matches m "
            "WHERE m.home_goals IS NOT NULL "
            "  AND NOT EXISTS (SELECT 1 FROM rating_history rh "
            "                  WHERE rh.match_id = m.id) "
            "ORDER BY m.match_date ASC", )
        pending = [row[0] for row in cur.fetchall()]
    for match_id in pending:
        apply_match_result(conn, match_id, importance)   # commits per match


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
        cur.execute(
            "INSERT INTO players (name, external_id, birth_date, nationality) "
            "VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (external_id) WHERE external_id IS NOT NULL "
            "DO UPDATE SET name = EXCLUDED.name, "
            "  birth_date = COALESCE(EXCLUDED.birth_date, players.birth_date), "
            "  nationality = COALESCE(EXCLUDED.nationality, players.nationality) "
            "RETURNING id",
            (p["name"], str(p["id"]), p.get("dateOfBirth"), nationality_id))
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


if __name__ == "__main__":
    # Sketch of a scheduled run (provide your own psycopg connection + key):
    #   bucket = TokenBucket(10)
    #   client = FootballDataClient(API_KEY, bucket)
    #   sync_competition(conn, client, "PL", "Premier League",
    #                    "domestic_league", "2025/26", team_type="club")
    #   sync_competition(conn, client, "WC", "FIFA World Cup",
    #                    "international", "2026", team_type="national")
    pass
