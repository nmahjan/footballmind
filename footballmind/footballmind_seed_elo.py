"""
FootballMind -- one-time national-team Elo seed.

Problem: the football-data.org free tier exposes only the current World Cup
edition (no historical results), so every national side would start at 1500
and pre-tournament predictions would be uniform. Solution: seed initial
ratings from the public World Football Elo Ratings (eloratings.net), recentered
to our 1500-mean scale. Only the *gaps* matter for prediction, so recentering
preserves their information exactly.

Insert-only: a team that already has a team_ratings row is never touched, so
ratings learned from real results always win. Re-running is safe.

Usage: python footballmind_jobs.py seed-elo
"""

import requests

WORLD_TSV = "https://www.eloratings.net/World.tsv"
TEAMS_TSV = "https://www.eloratings.net/en.teams.tsv"

# football-data.org name -> eloratings.net name, where they disagree
ALIASES = {
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Cape Verde Islands": "Cape Verde",
    "USA": "United States",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "China PR": "China",
    "Congo DR": "DR Congo",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
}


def _fetch_text(url, timeout):
    r = requests.get(url, timeout=timeout)
    r.encoding = "utf-8"          # server omits charset; default latin-1 mangles names
    return r.text


def fetch_elo_by_name(timeout=20):
    """Return {country_name: elo_rating} from eloratings.net."""
    codes = {}
    for line in _fetch_text(TEAMS_TSV, timeout).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            codes[parts[0]] = parts[1]
    ratings = {}
    for line in _fetch_text(WORLD_TSV, timeout).splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[2] in codes:
            ratings[codes[parts[2]]] = float(parts[3])
    return ratings


def seed_national_elo(conn):
    """Seed team_ratings for national teams that have no rating yet.
    Returns (seeded, skipped_existing, unmatched_names)."""
    elo = fetch_elo_by_name()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.id, t.name FROM teams t "
            "WHERE t.type = 'national' "
            "  AND NOT EXISTS (SELECT 1 FROM team_ratings r WHERE r.team_id = t.id)")
        todo = cur.fetchall()

        matched, unmatched = [], []
        for team_id, name in todo:
            r = elo.get(name) or elo.get(ALIASES.get(name, ""))
            if r is None:
                unmatched.append(name)
            else:
                matched.append((team_id, name, r))

        if matched:
            # Recenter so the seeded pool means 1500 (our base); gaps unchanged.
            mean = sum(r for _, _, r in matched) / len(matched)
            for team_id, _, r in matched:
                cur.execute(
                    "INSERT INTO team_ratings (team_id, rating) VALUES (%s, %s) "
                    "ON CONFLICT (team_id) DO NOTHING",
                    (team_id, 1500.0 + (r - mean)))
    conn.commit()
    return len(matched), len(todo) - len(matched) - len(unmatched), unmatched
