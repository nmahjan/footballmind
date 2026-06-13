#!/usr/bin/env python3
"""
Probe soccerdata sources for league coverage and lineup availability.

Usage:
  python scripts/probe_soccerdata.py
  python scripts/probe_soccerdata.py --source espn --league "INT-World Cup" --season 2022
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run from footballmind/ or repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _wc_like(leagues: list[str]) -> list[str]:
    keys = ("world", "fifa", "wc", "international", "int-", "uefa", "copa", "euro")
    return sorted({L for L in leagues if any(k in L.lower() for k in keys)})


def _preview_df(df, n: int = 3) -> str:
    if df is None or df.empty:
        return "(empty)"
    cols = list(df.columns[:12])
    head = df.head(n)
    lines = [f"  rows={len(df)} cols={len(df.columns)}"]
    for idx, row in head.iterrows():
        bits = []
        for c in cols:
            val = row[c] if c in row.index else ""
            if isinstance(val, (dict, list)):
                val = type(val).__name__
            bits.append(f"{c}={val!r}")
        lines.append(f"  [{idx}] " + ", ".join(bits[:8]))
    return "\n".join(lines)


def probe_espn(league: str | None, season: str | int | None) -> dict:
    import soccerdata as sd

    available = sd.ESPN.available_leagues()
    wc = _wc_like(available)
    out: dict = {"available_count": len(available), "wc_like": wc}

    if not league:
        out["sample_leagues"] = available[:15]
        return out

    kwargs: dict = {"leagues": league}
    if season is not None:
        kwargs["seasons"] = season
    kwargs["no_store"] = True

    espn = sd.ESPN(**kwargs)
    schedule = espn.read_schedule()
    out["schedule_rows"] = len(schedule)
    out["schedule_preview"] = _preview_df(schedule)

    finished = schedule
    if "home_score" in schedule.columns and "away_score" in schedule.columns:
        finished = schedule.dropna(subset=["home_score", "away_score"])
    elif "score" in schedule.columns:
        finished = schedule[schedule["score"].notna()]

    if finished.empty:
        out["lineup"] = "no finished matches in schedule"
        return out

    row = finished.iloc[0]
    game_id = row.get("game_id") if hasattr(row, "get") else row["game_id"]
    out["sample_game_id"] = int(game_id) if game_id is not None else None
    out["sample_game"] = str(finished.index[0]) if hasattr(finished.index, "__getitem__") else str(row.name)

    try:
        lineup = espn.read_lineup(match_id=int(game_id))
        out["lineup_rows"] = len(lineup)
        out["lineup_preview"] = _preview_df(lineup)
        starters = lineup[lineup.get("position", lineup.iloc[:, 0]) != "Substitute"] if not lineup.empty else lineup
        if "position" in lineup.columns:
            starters = lineup[lineup["position"] != "Substitute"]
        out["starter_count"] = len(starters) if not lineup.empty else 0
    except Exception as e:
        out["lineup_error"] = repr(e)

    try:
        sheet = espn.read_matchsheet(match_id=int(game_id))
        out["matchsheet_rows"] = len(sheet)
        if not sheet.empty and "roster" in sheet.columns:
            roster = sheet.iloc[0].get("roster")
            out["matchsheet_has_roster"] = roster is not None and len(roster) > 0
    except Exception as e:
        out["matchsheet_error"] = repr(e)

    return out


def probe_espn_direct_wc(date: str = "20221218") -> dict:
    """ESPN hidden API — not wired into soccerdata's league list, but WC data exists."""
    import requests

    out: dict = {"date": date, "slug": "fifa.world"}
    sb = requests.get(
        "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
        params={"dates": date, "limit": 10},
        timeout=25,
    )
    out["scoreboard_status"] = sb.status_code
    if not sb.ok:
        out["error"] = sb.text[:200]
        return out
    events = sb.json().get("events") or []
    out["events"] = len(events)
    if not events:
        return out
    ev = events[0]
    eid = ev.get("id")
    out["sample_event"] = ev.get("name")
    out["sample_event_id"] = eid

    sm = requests.get(
        "https://site.web.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary",
        params={"event": eid},
        timeout=25,
    )
    out["summary_status"] = sm.status_code
    if not sm.ok:
        return out
    rosters = sm.json().get("rosters") or []
    teams = []
    for roster in rosters:
        team = (roster.get("team") or {}).get("displayName")
        formation = roster.get("formation")
        players = roster.get("roster") or []
        starters = [p for p in players if p.get("starter")]
        teams.append({
            "team": team,
            "formation": formation,
            "players": len(players),
            "starters": len(starters),
        })
    out["teams"] = teams
    return out


def probe_sofifa() -> dict:
    import soccerdata as sd

    out: dict = {}
    try:
        so = sd.SoFIFA(leagues="ENG-Premier League", versions="latest", no_store=True)
        ratings = so.read_player_ratings(team="Arsenal")
        out["arsenal_players"] = len(ratings)
        if not ratings.empty:
            row = ratings.iloc[0]
            out["sample_player"] = str(ratings.index[0])
            out["sample_overall"] = float(row.get("overallrating", 0))
            out["sample_cols"] = [c for c in ratings.columns if c in (
                "overallrating", "potential", "preferredfoot", "workrate", "position")]
    except Exception as e:
        out["error"] = repr(e)
    return out


def probe_sofascore(league: str | None, season: str | int | None) -> dict:
    import soccerdata as sd

    available = sd.Sofascore.available_leagues()
    wc = _wc_like(available)
    out: dict = {"available_count": len(available), "wc_like": wc}

    if not league:
        out["sample_leagues"] = available[:15]
        return out

    kwargs: dict = {"leagues": league}
    if season is not None:
        kwargs["seasons"] = season
    kwargs["no_store"] = True

    sofa = sd.Sofascore(**kwargs)
    schedule = sofa.read_schedule()
    out["schedule_rows"] = len(schedule)
    out["schedule_preview"] = _preview_df(schedule)

    finished = schedule.dropna(subset=["home_score", "away_score"]) if not schedule.empty else schedule
    if finished.empty:
        out["lineup"] = "no finished matches in schedule"
        return out

    game_id = finished.iloc[0]["game_id"]
    out["sample_game_id"] = int(game_id)
    out["sample_game"] = str(finished.index[0])

    for method in ("read_lineup", "read_lineups", "read_game_lineup"):
        fn = getattr(sofa, method, None)
        if not callable(fn):
            continue
        try:
            lineup = fn(match_id=int(game_id))
            out["lineup_method"] = method
            out["lineup_rows"] = len(lineup) if hasattr(lineup, "__len__") else "?"
            out["lineup_preview"] = _preview_df(lineup if hasattr(lineup, "head") else None)
            break
        except Exception as e:
            out[f"{method}_error"] = repr(e)
    else:
        out["lineup"] = "no read_lineup* method on Sofascore reader (check soccerdata version)"
        out["sofascore_methods"] = [m for m in dir(sofa) if m.startswith("read_")]

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe soccerdata ESPN/Sofascore coverage")
    parser.add_argument("--source", choices=("espn", "sofascore", "both"), default="both")
    parser.add_argument("--league", default=None, help="League id, e.g. INT-World Cup or ENG-Premier League")
    parser.add_argument("--season", default=None, help="Season, e.g. 2022 or 2022/2023")
    parser.add_argument("--wc-direct", action="store_true",
                        help="Also probe ESPN fifa.world JSON (World Cup lineups)")
    parser.add_argument("--sofifa", action="store_true", help="Smoke-test SoFIFA ratings")
    args = parser.parse_args()

    season = args.season
    if season is not None and season.isdigit() and len(season) == 4:
        season = int(season)

    results: dict = {}

    if args.source in ("espn", "both"):
        print("=== ESPN ===", flush=True)
        try:
            espn_league = args.league
            if espn_league is None and args.source == "both":
                # Default WC probe when no league specified for deep test
                pass
            r = probe_espn(espn_league, season)
            results["espn"] = r
            print(json.dumps(r, indent=2, default=str))
        except Exception as e:
            results["espn"] = {"fatal": repr(e)}
            print(json.dumps(results["espn"], indent=2))
            print(f"ESPN fatal: {e}", file=sys.stderr)

    if args.wc_direct or (args.source == "both" and args.league is None):
        print("\n=== ESPN direct (fifa.world) ===", flush=True)
        try:
            wc = probe_espn_direct_wc()
            results["espn_direct_wc"] = wc
            print(json.dumps(wc, indent=2, default=str))
        except Exception as e:
            results["espn_direct_wc"] = {"fatal": repr(e)}
            print(json.dumps(results["espn_direct_wc"], indent=2))

    if args.sofifa or (args.source == "both" and args.league is None):
        print("\n=== SoFIFA ===", flush=True)
        try:
            sf = probe_sofifa()
            results["sofifa"] = sf
            print(json.dumps(sf, indent=2, default=str))
        except Exception as e:
            results["sofifa"] = {"fatal": repr(e)}
            print(json.dumps(results["sofifa"], indent=2))

    if args.source in ("sofascore", "both"):
        print("\n=== Sofascore ===", flush=True)
        try:
            r = probe_sofascore(args.league, season)
            results["sofascore"] = r
            print(json.dumps(r, indent=2, default=str))
        except Exception as e:
            results["sofascore"] = {"fatal": repr(e)}
            print(json.dumps(results["sofascore"], indent=2))
            print(f"Sofascore fatal: {e}", file=sys.stderr)

    # If no league given, suggest WC candidates
    if args.league is None:
        print("\n=== Suggested WC / international league ids ===", flush=True)
        for src, data in results.items():
            wc = data.get("wc_like") or []
            print(f"  {src}: {wc if wc else '(none matched)'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
