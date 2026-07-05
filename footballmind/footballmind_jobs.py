"""
FootballMind -- scheduled jobs entrypoint.

Two commands, triggered by GitHub Actions cron (see
.github/workflows/footballmind-jobs.yml):

    python footballmind_jobs.py sync      # every ~6h: pull results, update Elo
    python footballmind_jobs.py retrain   # weekly: sweep + redeploy best models

Running these from GitHub Actions (not in-process) means they fire on schedule
even while a free-tier web service is asleep.

Env vars:
    DATABASE_URL            postgres URL (Neon, include ?sslmode=require)
    FOOTBALL_DATA_API_KEY   football-data.org key (sync only)
"""

import os
import sys
from datetime import date, timedelta

from footballmind_db import get_connection
from footballmind_sync import (TokenBucket, FootballDataClient,
                               sync_competition, sync_teams_and_squads,
                               sync_scorers, sync_match_details)
from footballmind_production import select_and_deploy
from footballmind_seed_elo import seed_national_elo
from footballmind_grading import grade_predictions, link_orphan_predictions

# (code, name, comp_type, team_type, season)
# football-data.org free-tier competitions available without a paid plan:
#   PL, CL, FL1, BL1, SA, PD, DED  (WC is free during tournament year)
COMPETITIONS = [
    ("PL",  "Premier League",        "domestic_league",   "club",     "2025/26"),
    ("CL",  "UEFA Champions League", "continental_club",  "club",     "2025/26"),
    ("PD",  "La Liga",               "domestic_league",   "club",     "2025/26"),
    ("BL1", "Bundesliga",            "domestic_league",   "club",     "2025/26"),
    ("SA",  "Serie A",               "domestic_league",   "club",     "2025/26"),
    ("FL1", "Ligue 1",               "domestic_league",   "club",     "2025/26"),
    ("DED", "Eredivisie",            "domestic_league",   "club",     "2025/26"),
    ("WC",  "FIFA World Cup",        "international",     "national", "2026"),
]


def _connect():
    return get_connection()


def cmd_sync(full=False):
    """Rolling 10-day window normally; --full pulls the whole current season
    (first seed / recovery after downtime)."""
    bucket = TokenBucket(10)
    client = FootballDataClient(os.environ["FOOTBALL_DATA_API_KEY"], bucket)
    since = None if full else (date.today() - timedelta(days=10)).isoformat()
    with _connect() as conn:
        for code, name, ctype, team_type, season in COMPETITIONS:
            try:
                sync_competition(conn, client, code, name, ctype, season,
                                 team_type=team_type, since=since)
                n = sync_teams_and_squads(conn, client, code, team_type=team_type)
                ns = sync_scorers(conn, client, code, season, team_type=team_type)
                print(f"[sync] {code} ok ({n} squads, {ns} scorers)")
            except Exception as e:        # one bad competition shouldn't kill the run
                print(f"[sync] {code} FAILED: {e}", file=sys.stderr)
        detail_n = sync_match_details(conn, client, limit=50 if full else 15)
        print(f"[sync] match details: {detail_n} checked")
        linked = link_orphan_predictions(conn)
        graded = grade_predictions(conn)
        print(f"[sync] predictions: {linked} linked, {graded} graded")


def cmd_seed_elo():
    with _connect() as conn:
        seeded, skipped, unmatched = seed_national_elo(conn)
        print(f"[seed-elo] seeded {seeded}, already rated {skipped}")
        if unmatched:
            print(f"[seed-elo] UNMATCHED (left at 1500 default): {unmatched}",
                  file=sys.stderr)


def _editions_for(conn, codes):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id FROM competition_editions e "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = ANY(%s)", (list(codes),))
        return [r[0] for r in cur.fetchall()]


def cmd_retrain():
    """Deploy two models -- clubs and nations are separate ladders, so they get
    separately-fit hybrids stored under different names."""
    test_start = date.today() - timedelta(days=120)
    domains = [
        ([c[0] for c in COMPETITIONS if c[3] == "club"],     "production_club",          "league"),
        ([c[0] for c in COMPETITIONS if c[3] == "national"], "production_international",  "world_cup"),
    ]
    with _connect() as conn:
        for codes, name, importance in domains:
            editions = _editions_for(conn, codes)
            if not editions:
                print(f"[retrain] {name}: no editions yet, skipping")
                continue
            try:
                best = select_and_deploy(conn, editions, test_start,
                                         importance=importance, name=name)["best"]
            except ValueError as e:
                # e.g. a tournament that hasn't started: edition exists but no
                # finished matches. predict_match falls back to pure Elo until
                # enough results land for a fit.
                print(f"[retrain] {name}: skipped ({e})")
                continue
            print(f"[retrain] {name}: half_life={best['half_life_days']}d "
                  f"cred={best['full_credibility']} RPS={best['mean_rps']:.4f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sync":
        cmd_sync(full="--full" in sys.argv)
    elif cmd == "retrain":
        cmd_retrain()
    elif cmd == "seed-elo":
        cmd_seed_elo()
    else:
        print("usage: footballmind_jobs.py [sync|retrain|seed-elo]")
        sys.exit(1)
