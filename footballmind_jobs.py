"""
FootballMind -- scheduled jobs entrypoint.

Two commands, triggered by GitHub Actions cron (see
.github/workflows/footballmind-jobs.yml):

    python footballmind_jobs.py sync           # every ~6h: pull results, update Elo
    python footballmind_jobs.py sync-matchday  # every ~30m on match days: fixtures only
    python footballmind_jobs.py backfill-scorers  # past season top scorers (optional)

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


def _comps_with_activity(conn, hours_before=3, hours_ahead=24):
    """Competition codes with a fixture in the live window (recent kickoffs + today)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT c.code "
            "FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE m.match_date >= now() - make_interval(hours => %s) "
            "  AND m.match_date <  now() + make_interval(hours => %s)",
            (hours_before, hours_ahead))
        return {row[0] for row in cur.fetchall()}


def cmd_sync_matchday(force=False):
    """Light sync for match days: fixtures + details + grading only (no squads/scorers).

    Skips when nothing is scheduled in the next 24h unless --force (manual run).
    """
    bucket = TokenBucket(10)
    client = FootballDataClient(os.environ["FOOTBALL_DATA_API_KEY"], bucket)
    since = (date.today() - timedelta(days=1)).isoformat()
    with _connect() as conn:
        active = _comps_with_activity(conn)
        if not active and not force:
            print("[sync-matchday] no fixtures in window — skipping", flush=True)
            return
        if not active and force:
            active = {c[0] for c in COMPETITIONS}
            print("[sync-matchday] --force: syncing all competitions", flush=True)
        else:
            print(f"[sync-matchday] active comps: {', '.join(sorted(active))}",
                  flush=True)
        for code, name, ctype, team_type, season in COMPETITIONS:
            if code not in active:
                continue
            try:
                print(f"[sync-matchday] {code} matches...", flush=True)
                sync_competition(conn, client, code, name, ctype, season,
                                 team_type=team_type, since=since)
            except Exception as e:
                print(f"[sync-matchday] {code} FAILED: {e}", file=sys.stderr,
                      flush=True)
        print("[sync-matchday] match details...", flush=True)
        detail_n = sync_match_details(conn, client, limit=40)
        print(f"[sync-matchday] match details: {detail_n} checked", flush=True)
        linked = link_orphan_predictions(conn)
        graded = grade_predictions(conn)
        print(f"[sync-matchday] predictions: {linked} linked, {graded} graded")


def cmd_sync(full=False):
    """Rolling 10-day window normally; --full pulls the whole current season
    (first seed / recovery after downtime)."""
    bucket = TokenBucket(10)
    client = FootballDataClient(os.environ["FOOTBALL_DATA_API_KEY"], bucket)
    since = None if full else (date.today() - timedelta(days=10)).isoformat()
    with _connect() as conn:
        for code, name, ctype, team_type, season in COMPETITIONS:
            try:
                print(f"[sync] {code} matches...", flush=True)
                sync_competition(conn, client, code, name, ctype, season,
                                 team_type=team_type, since=since)
                print(f"[sync] {code} squads...", flush=True)
                n = sync_teams_and_squads(conn, client, code, team_type=team_type)
                print(f"[sync] {code} scorers...", flush=True)
                ns = sync_scorers(conn, client, code, season, team_type=team_type)
                print(f"[sync] {code} ok ({n} squads, {ns} scorers)", flush=True)
            except Exception as e:        # one bad competition shouldn't kill the run
                print(f"[sync] {code} FAILED: {e}", file=sys.stderr, flush=True)
        print("[sync] match details...", flush=True)
        detail_n = sync_match_details(conn, client, limit=50 if full else 15)
        print(f"[sync] match details: {detail_n} checked", flush=True)
        linked = link_orphan_predictions(conn)
        graded = grade_predictions(conn)
        print(f"[sync] predictions: {linked} linked, {graded} graded")


def _season_labels_before(current: str, count: int) -> list[str]:
    """Season labels strictly before current, e.g. 2025/26 -> 2018/19 .. 2024/25."""
    start = int(current.split("/")[0]) if "/" in current else int(current)
    out = []
    for i in range(count, 0, -1):
        y = start - i
        out.append(f"{y}/{(y + 1) % 100:02d}" if "/" in current else str(y))
    return out


def cmd_backfill_scorers(seasons: list[str] | None = None):
    """Pull top scorers for past seasons into player_edition_stats (additive — never wipes).

    Default: eight seasons before each comp's configured current season (club comps only).
    """
    bucket = TokenBucket(10)
    client = FootballDataClient(os.environ["FOOTBALL_DATA_API_KEY"], bucket)
    with _connect() as conn:
        for code, name, ctype, team_type, current in COMPETITIONS:
            if team_type != "club":
                continue
            labels = seasons or _season_labels_before(current, 8)
            for season in labels:
                try:
                    n = sync_scorers(conn, client, code, season, team_type=team_type,
                                     comp_name=name, comp_type=ctype)
                    print(f"[backfill-scorers] {code} {season}: {n} scorers", flush=True)
                except Exception as e:
                    print(f"[backfill-scorers] {code} {season} FAILED: {e}",
                          file=sys.stderr, flush=True)


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
    elif cmd == "sync-matchday":
        cmd_sync_matchday(force="--force" in sys.argv)
    elif cmd == "retrain":
        cmd_retrain()
    elif cmd == "seed-elo":
        cmd_seed_elo()
    elif cmd == "backfill-scorers":
        extra = [a for a in sys.argv[2:] if not a.startswith("-")]
        cmd_backfill_scorers(extra or None)
    else:
        print("usage: footballmind_jobs.py "
              "[sync|sync-matchday|backfill-scorers|retrain|seed-elo]")
        sys.exit(1)
