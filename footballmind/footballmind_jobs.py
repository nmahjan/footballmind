"""
FootballMind -- scheduled jobs entrypoint.

Scheduled via GitHub Actions (see .github/workflows/):

    python footballmind_jobs.py sync              # every ~6h: pull results, update Elo
    python footballmind_jobs.py sync-matchday     # every ~30m on match days: fixtures only
    python footballmind_jobs.py sync-wikipedia    # quarterly: WC + PL squads from Wikipedia
    python footballmind_jobs.py sync-wikipedia --clubs-only --teams Arsenal,Bournemouth
    python footballmind_jobs.py regrade           # re-link + re-grade all finished predictions
    python footballmind_jobs.py sync-espn-wc      # ESPN WC lineups (batch / backfill)
    python footballmind_jobs.py sync-sofifa       # EA FC attrs via SoFIFA (optional, needs Chrome)
    python footballmind_jobs.py backfill-scorers  # past season top scorers (optional)

Running these from GitHub Actions (not in-process) means they fire on schedule
even while a free-tier web service is asleep.

Env vars:
    DATABASE_URL            postgres URL (Neon, include ?sslmode=require)
    FOOTBALL_DATA_API_KEY   football-data.org key (sync only)
    FOOTBALLDATA_IO_KEY     footballdata.io key (optional squad positions)
"""

import os
import sys
from datetime import date, timedelta

from footballmind_db import get_connection, release_transaction
from footballmind_sync import (TokenBucket, FootballDataClient,
                               sync_competition, sync_teams_and_squads,
                               sync_scorers, sync_match_details,
                               refresh_knockout_scores, apply_team_captains)
from footballmind_production import select_and_deploy, train_and_store
from footballmind_seed_elo import seed_national_elo
from footballmind_grading import grade_predictions, link_orphan_predictions
from footballmind_enrich import sync_enrichment
from footballmind_espn_wc import backfill_espn_wc_dates, sync_espn_wc_lineups
from footballmind_sofifa import sync_sofifa_attributes, SOFIFA_CLUB_LEAGUES

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
    ("MLS", "MLS",                   "domestic_league",   "club",     "2026"),
]

# football-data.org v4 no longer exposes captain on squad/person — maintain manually.
# Keys: (comp_code, team_name) -> player name on that team's current squad.
# Use names that exist in our synced roster (football-data.org); Morata/Gündoğan
# are not on Spain/Germany WC squads in FDO — use in-squad leaders instead.
TEAM_CAPTAINS: dict[tuple[str, str], str] = {
    ("PL", "Arsenal FC"): "Martin Ødegaard",
    ("WC", "Argentina"): "Lionel Messi",
    ("WC", "Spain"): "Dani Olmo",
    ("WC", "England"): "Harry Kane",
    ("WC", "France"): "Kylian Mbappé",
    ("WC", "Brazil"): "Casemiro",
    ("WC", "Germany"): "Joshua Kimmich",
    ("WC", "Portugal"): "Cristiano Ronaldo",
    ("WC", "Netherlands"): "Virgil van Dijk",
    ("WC", "Belgium"): "Kevin De Bruyne",
}


def _connect():
    return get_connection()


def _comps_with_activity(conn, hours_before=12, hours_ahead=72):
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
    since = (date.today() - timedelta(days=3)).isoformat()
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
                comp_since = None if code in ("WC", "CL") else since
                print(f"[sync-matchday] {code} matches...", flush=True)
                sync_competition(conn, client, code, name, ctype, season,
                                 team_type=team_type, since=comp_since)
            except Exception as e:        # one bad competition shouldn't kill the run
                conn.rollback()
                print(f"[sync-matchday] {code} FAILED: {e}", file=sys.stderr,
                      flush=True)
        print("[sync-matchday] match details...", flush=True)
        detail_n = sync_match_details(conn, client, limit=40)
        print(f"[sync-matchday] match details: {detail_n} checked", flush=True)
        if "WC" in active:
            try:
                n = refresh_knockout_scores(conn, client, "WC", limit=32)
                if n:
                    print(f"[sync-matchday] WC knockout scores refreshed: {n}",
                          flush=True)
            except Exception as e:
                print(f"[sync-matchday] WC score refresh FAILED: {e}",
                      file=sys.stderr, flush=True)
        linked = link_orphan_predictions(conn)
        graded = grade_predictions(conn)
        print(f"[sync-matchday] predictions: {linked} linked, {graded} graded")
        try:
            from footballmind_grading import ensure_result_predictions
            fill = ensure_result_predictions(conn, "WC", backfill_limit=20)
            if fill["backfilled"]:
                print(f"[sync-matchday] WC result predictions backfilled: {fill['backfilled']}",
                      flush=True)
        except Exception as e:
            print(f"[sync-matchday] result backfill FAILED: {e}", file=sys.stderr, flush=True)
        try:
            espn = sync_espn_wc_lineups(conn, limit=30)
            print(f"[sync-matchday] espn-wc: checked={espn['checked']} "
                  f"synced={espn['synced']} players={espn['players']}", flush=True)
        except Exception as e:
            print(f"[sync-matchday] espn-wc FAILED: {e}", file=sys.stderr, flush=True)
        try:
            from footballmind_sync_status import record_sync_run
            record_sync_run(
                conn, "matchday", status="ok",
                summary={"active": sorted(active), "linked": linked, "graded": graded},
            )
        except Exception:
            pass


def cmd_sync(full=False):
    """Rolling 10-day window normally; --full pulls the whole current season
    (first seed / recovery after downtime)."""
    bucket = TokenBucket(10)
    client = FootballDataClient(os.environ["FOOTBALL_DATA_API_KEY"], bucket)
    since = None if full else (date.today() - timedelta(days=10)).isoformat()
    with _connect() as conn:
        for code, name, ctype, team_type, season in COMPETITIONS:
            try:
                if code == "MLS":
                    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
                    if api_key:
                        from footballmind_enrich import (
                            ApiFootballClient,
                            sync_api_football_comp_metadata,
                            sync_api_football_competition,
                        )
                        af_client = ApiFootballClient(api_key)
                        nf = sync_api_football_competition(conn, af_client, code)
                        meta = sync_api_football_comp_metadata(conn, af_client, code)
                        print(
                            f"[sync] MLS via api-football: {nf} fixtures, "
                            f"{meta['conferences']} conference tags, "
                            f"{meta['players']} players",
                            flush=True,
                        )
                    else:
                        print("[sync] MLS skipped — needs API_FOOTBALL_KEY "
                              "(not on football-data.org free tier)", flush=True)
                    continue
                print(f"[sync] {code} matches...", flush=True)
                sync_competition(conn, client, code, name, ctype, season,
                                 team_type=team_type, since=since)
                print(f"[sync] {code} squads...", flush=True)
                n = sync_teams_and_squads(conn, client, code, team_type=team_type)
                print(f"[sync] {code} scorers...", flush=True)
                ns = sync_scorers(conn, client, code, season, team_type=team_type)
                print(f"[sync] {code} ok ({n} squads, {ns} scorers)", flush=True)
            except Exception as e:        # one bad competition shouldn't kill the run
                conn.rollback()
                print(f"[sync] {code} FAILED: {e}", file=sys.stderr, flush=True)
        print("[sync] match details...", flush=True)
        detail_n = sync_match_details(conn, client, limit=50 if full else 15)
        print(f"[sync] match details: {detail_n} checked", flush=True)
        nc = apply_team_captains(conn, TEAM_CAPTAINS)
        print(f"[sync] captains: {nc} flags set", flush=True)
        try:
            cmd_sync_enrich()
        except Exception as e:
            print(f"[sync] enrich FAILED: {e}", file=sys.stderr, flush=True)
        linked = link_orphan_predictions(conn)
        graded = grade_predictions(conn)
        print(f"[sync] predictions: {linked} linked, {graded} graded")
        try:
            from footballmind_sync_status import record_sync_run
            record_sync_run(
                conn, "sync", status="ok",
                summary={"linked": linked, "graded": graded, "full": full},
            )
        except Exception:
            pass


def cmd_sync_enrich():
    """Free enrichment feeds: FPL injuries, API-Football ratings/injuries, Understat xG."""
    with _connect() as conn:
        stats = sync_enrichment(conn)
        from footballmind_roles import apply_player_line_roles
        n = apply_player_line_roles(conn)
        if n:
            print(f"[sync-enrich] applied {n} line_role overrides", flush=True)
        parts = ", ".join(f"{k}={v}" for k, v in sorted(stats.items()))
        print(f"[sync-enrich] {parts}", flush=True)
        if (
            os.environ.get("API_FOOTBALL_KEY", "").strip()
            and stats.get("api_football_injuries", 0) == 0
            and stats.get("api_football_ratings", 0) == 0
        ):
            print(
                "[sync-enrich] API-Football key is set but returned no rows — "
                "the free plan only covers older seasons and blocks the "
                "'last N fixtures' shortcut; upgrade for 2025/26 ratings.",
                flush=True,
            )


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
        ([c[0] for c in COMPETITIONS if c[3] == "club"], "production_club",
         "league", 60, 180, 10),
        ([c[0] for c in COMPETITIONS if c[3] == "national"], "production_international",
         "world_cup", 12, 180, 5),
    ]
    with _connect() as conn:
        for (codes, name, importance, min_history,
             default_hl, default_cred) in domains:
            editions = _editions_for(conn, codes)
            release_transaction(conn)
            if not editions:
                print(f"[retrain] {name}: no editions yet, skipping")
                continue
            try:
                out = select_and_deploy(
                    conn, editions, test_start, importance=importance, name=name,
                    min_history=min_history, default_half_life=default_hl,
                    default_credibility=default_cred)
                best = out["best"]
            except ValueError as e:
                # Edition exists but no finished matches to fit on yet.
                print(f"[retrain] {name}: skipped ({e})")
                continue
            rps = best["mean_rps"]
            rps_s = f"{rps:.4f}" if rps is not None else "n/a (defaults)"
            note = " [backtest skipped]" if out.get("backtest_skipped") else ""
            print(f"[retrain] {name}: half_life={best['half_life_days']}d "
                  f"cred={best['full_credibility']} RPS={rps_s}{note}")


def cmd_sync_sofifa():
    """EA FC physical/meta attributes from SoFIFA (optional soccerdata + Chrome)."""
    teams = None
    leagues = None
    max_players = None
    version_id = None
    all_clubs = False
    headless = os.environ.get("SOFIFA_VISIBLE", "").lower() not in ("1", "true", "yes")
    cloudflare_wait_sec = 600
    import_cache = False
    cache_dir = None
    ttl_days = 90          # skip players synced within this window; --refresh-all disables
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--teams" and i + 1 < len(args):
            teams = [t.strip() for t in args[i + 1].split(",") if t.strip()]
            i += 2
        elif args[i] == "--leagues" and i + 1 < len(args):
            leagues = [t.strip() for t in args[i + 1].split(",") if t.strip()]
            i += 2
        elif args[i] == "--max" and i + 1 < len(args):
            max_players = int(args[i + 1])
            i += 2
        elif args[i] == "--version" and i + 1 < len(args):
            version_id = int(args[i + 1])
            i += 2
        elif args[i] == "--visible":
            headless = False
            i += 1
        elif args[i] == "--cloudflare-wait" and i + 1 < len(args):
            cloudflare_wait_sec = int(args[i + 1])
            i += 2
        elif args[i] == "--import-cache":
            import_cache = True
            i += 1
        elif args[i] == "--all-clubs":
            all_clubs = True
            i += 1
        elif args[i] == "--refresh-all":
            ttl_days = None
            i += 1
        elif args[i] == "--ttl-days" and i + 1 < len(args):
            ttl_days = int(args[i + 1])
            i += 2
        elif args[i] == "--cache-dir" and i + 1 < len(args):
            cache_dir = args[i + 1]
            import_cache = True
            i += 2
        else:
            i += 1
    if not import_cache:
        mode = "headless (no Chrome window)" if headless else "visible Chrome"
        print(f"[sync-sofifa] browser={mode}", flush=True)
        if not headless:
            print(
                f"[sync-sofifa] cloudflare_wait={cloudflare_wait_sec}s "
                "(page will not reload while you click the checkbox)",
                flush=True,
            )
        elif headless:
            print(
                "[sync-sofifa] tip: add --visible to open Chrome for Cloudflare",
                flush=True,
            )
    teams_for_sync = teams
    leagues_for_sync = leagues or list(SOFIFA_CLUB_LEAGUES)
    if all_clubs and not import_cache:
        with _connect() as conn:
            from footballmind_sofifa import db_club_team_names
            teams_for_sync = db_club_team_names(conn)
        print(
            f"[sync-sofifa] all-clubs: {len(teams_for_sync)} DB clubs, "
            f"leagues={', '.join(leagues_for_sync)} (SoFIFA top-5 only)",
            flush=True,
        )
    if import_cache:
        with _connect() as conn:
            from footballmind_sofifa import sync_sofifa_from_cache
            stats = sync_sofifa_from_cache(conn, cache_dir, max_files=max_players)
    else:
        stats = sync_sofifa_attributes(
            leagues=leagues_for_sync,
            teams=teams_for_sync,
            version_id=version_id,
            max_players=max_players,
            headless=headless,
            cloudflare_wait_sec=cloudflare_wait_sec,
            ttl_days=ttl_days,
        )
    with _connect() as conn:
        from footballmind_roles import apply_player_line_roles
        n = apply_player_line_roles(conn)
        if n:
            print(f"[sync-sofifa] applied {n} manual line_role overrides", flush=True)
    if stats.get("error"):
        print(f"[sync-sofifa] {stats['error']}", file=sys.stderr, flush=True)
    if stats.get("hint"):
        print(f"[sync-sofifa] hint: {stats['hint']}", flush=True)
    parts = ", ".join(f"{k}={v}" for k, v in sorted(stats.items()) if k != "hint")
    print(f"[sync-sofifa] {parts}", flush=True)


def cmd_sync_wikipedia():
    """WC + club squad positions from Wikipedia (free, no Chrome)."""
    wc_only = "--wc-only" in sys.argv
    clubs_only = "--clubs-only" in sys.argv
    teams = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--teams" and i + 1 < len(args):
            teams = [t.strip() for t in args[i + 1].split(",") if t.strip()]
            i += 2
        else:
            i += 1
    try:
        with _connect() as conn:
            from footballmind_wikipedia import sync_wikipedia_all
            from footballmind_roles import apply_player_line_roles
            from footballmind_sync_status import record_sync_run

            stats = sync_wikipedia_all(
                conn,
                wc=not clubs_only,
                clubs=not wc_only,
                teams=teams,
            )
            n = apply_player_line_roles(conn)
            if n:
                print(f"[sync-wikipedia] applied {n} manual line_role overrides", flush=True)
            _print_wikipedia_stats(stats)
            status = "partial" if any(b.get("errors") for b in stats.values()) else "ok"
            summary = record_sync_run(conn, "wikipedia", status=status, summary=stats)
            if summary.get("repeat_skips"):
                print(
                    f"[sync-wikipedia] ALERT repeat skips: "
                    f"{', '.join(summary['repeat_skips'])}",
                    file=sys.stderr,
                    flush=True,
                )
                sys.exit(1)
    except Exception as exc:
        try:
            with _connect() as conn:
                from footballmind_sync_status import record_sync_run
                record_sync_run(conn, "wikipedia", status="failed",
                                summary={"error": str(exc)})
        except Exception:
            pass
        print(f"[sync-wikipedia] FAILED: {exc}", file=sys.stderr, flush=True)
        raise


def _print_wikipedia_stats(stats: dict) -> None:
    for label, block in stats.items():
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(block.items())
            if k not in ("skipped_teams", "skipped_clubs", "missing_names", "errors")
        )
        print(f"[sync-wikipedia:{label}] {parts}", flush=True)
        skipped = block.get("skipped_teams") or block.get("skipped_clubs") or []
        if skipped:
            print(
                f"[sync-wikipedia:{label}] skipped ({len(skipped)}): "
                f"{', '.join(skipped)}",
                flush=True,
            )
        errors = block.get("errors") or []
        if errors:
            print(f"[sync-wikipedia:{label}] errors ({len(errors)}):", flush=True)
            for err in errors:
                print(f"[sync-wikipedia:{label}] error: {err}", flush=True)




def cmd_quick_refit(if_new_results=False):
    """Re-fit Dixon-Coles on latest data using the already-tuned hyperparameters.
    No parameter sweep -- fast enough to run after every matchday sync.

    --if-new-results: skip if no match results arrived since the model was last trained."""
    domains = [
        ([c[0] for c in COMPETITIONS if c[3] == "club"],     "production_club",          180, 10),
        ([c[0] for c in COMPETITIONS if c[3] == "national"], "production_international", 180,  5),
    ]
    with _connect() as conn:
        if if_new_results:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MIN(trained_at) FROM model_artifacts "
                    "WHERE name = ANY(%s)",
                    (["production_club", "production_international"],))
                oldest = cur.fetchone()[0]
            if oldest is not None:
                with conn.cursor() as cur:
                    # matches has no updated_at column; team_ratings.updated_at is set
                    # to now() every time a result is applied to Elo, so it is the
                    # reliable "a new result landed" signal. (The old matches.updated_at
                    # query threw column-does-not-exist on every matchday run.)
                    cur.execute(
                        "SELECT 1 FROM team_ratings WHERE updated_at > %s LIMIT 1",
                        (oldest,))
                    has_new = cur.fetchone() is not None
                if not has_new:
                    print("[quick-refit] no new results since last training — skipped", flush=True)
                    return
        for codes, name, default_hl, default_cred in domains:
            editions = _editions_for(conn, codes)
            if not editions:
                print(f"[quick-refit] {name}: no editions, skipping", flush=True)
                continue
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT half_life_days, full_credibility FROM model_artifacts WHERE name = %s",
                    (name,))
                row = cur.fetchone()
            hl   = row[0] if row else default_hl
            cred = row[1] if row else default_cred
            try:
                train_and_store(conn, editions, hl, cred, name=name)
                print(f"[quick-refit] {name}: done (half_life={hl}d cred={cred})", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[quick-refit] {name}: skipped ({e})", file=__import__('sys').stderr)
def cmd_regrade():
    """Re-link orphan predictions and re-grade all finished matches."""
    with _connect() as conn:
        linked = link_orphan_predictions(conn)
        graded = grade_predictions(conn, force=True)
        print(f"[regrade] linked={linked} graded={graded}", flush=True)


def cmd_sync_footballdata_io():
    """Pull squad positions from Footballdata.io into players.line_role."""
    teams = None
    max_teams = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--teams" and i + 1 < len(args):
            teams = [t.strip() for t in args[i + 1].split(",") if t.strip()]
            i += 2
        elif args[i] == "--max" and i + 1 < len(args):
            max_teams = int(args[i + 1])
            i += 2
        elif args[i] == "--probe":
            from footballmind_footballdata_io import probe_account
            print(probe_account(), flush=True)
            return
        else:
            i += 1
    with _connect() as conn:
        from footballmind_footballdata_io import sync_footballdata_io_line_roles
        from footballmind_roles import apply_player_line_roles

        stats = sync_footballdata_io_line_roles(
            conn, teams=teams, max_teams=max_teams,
        )
        n = apply_player_line_roles(conn)
        if n:
            stats["manual_overrides"] = n
    if stats.get("error"):
        print(f"[sync-footballdata-io] {stats['error']}", file=sys.stderr, flush=True)
    parts = ", ".join(
        f"{k}={v}" for k, v in sorted(stats.items()) if k != "details"
    )
    print(f"[sync-footballdata-io] {parts}", flush=True)
    for d in stats.get("details") or []:
        print(f"  {d}", flush=True)


def cmd_sync_espn_wc():
    """ESPN fifa.world lineups for WC matches missing formation data."""
    with _connect() as conn:
        if "--backfill" in sys.argv:
            extra = [a for a in sys.argv[2:] if a not in ("--backfill",) and not a.startswith("-")]
            if len(extra) >= 2:
                start = date.fromisoformat(extra[0])
                end = date.fromisoformat(extra[1])
            else:
                start = date(2022, 11, 20)
                end = date(2022, 12, 18)
            stats = backfill_espn_wc_dates(conn, start, end)
            print(f"[sync-espn-wc] backfill {start}..{end}: {stats}", flush=True)
        else:
            stats = sync_espn_wc_lineups(conn, limit=40)
            print(f"[sync-espn-wc] {stats}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sync":
        cmd_sync(full="--full" in sys.argv)
    elif cmd == "sync-matchday":
        cmd_sync_matchday(force="--force" in sys.argv)
    elif cmd == "retrain":
        cmd_retrain()
    elif cmd == "quick-refit":
        cmd_quick_refit(if_new_results="--if-new-results" in sys.argv)
    elif cmd == "seed-elo":
        cmd_seed_elo()
    elif cmd == "sync-enrich":
        cmd_sync_enrich()
    elif cmd == "backfill-scorers":
        extra = [a for a in sys.argv[2:] if not a.startswith("-")]
        cmd_backfill_scorers(extra or None)
    elif cmd == "sync-espn-wc":
        cmd_sync_espn_wc()
    elif cmd == "sync-sofifa":
        cmd_sync_sofifa()
    elif cmd == "sync-footballdata-io":
        cmd_sync_footballdata_io()
    elif cmd == "sync-wikipedia":
        cmd_sync_wikipedia()
    elif cmd == "regrade":
        cmd_regrade()
    else:
        print("usage: footballmind_jobs.py "
              "[sync|sync-matchday|sync-enrich|sync-espn-wc|sync-sofifa|"
              "sync-footballdata-io|sync-wikipedia|regrade|backfill-scorers|retrain|quick-refit|seed-elo]")
        sys.exit(1)
