"""
FootballMind Squad Scraper (local CSV export)
-----------------------------------------------
Thin CLI around footballmind_wikipedia club parsing.
For DB sync use: python footballmind_jobs.py sync-wikipedia

Run locally with: python scrape_squads.py
"""

from __future__ import annotations

import csv
import time

from footballmind_wikipedia import (
    LEAGUE_CLUB_WIKI_PAGES,
    extract_first_squad_block,
    fetch_wikitext,
    parse_fs_player_lines,
)

LEAGUE_LABELS = {
    "PL": "Premier League",
}


def main():
    all_rows = []

    for league_code, clubs in LEAGUE_CLUB_WIKI_PAGES.items():
        league = LEAGUE_LABELS.get(league_code, league_code)
        print(f"\n=== {league} ===")
        for wiki_title, db_name in clubs.items():
            try:
                print(f"Fetching: {wiki_title} ...", end=" ")
                wikitext = fetch_wikitext(wiki_title)
                section = extract_first_squad_block(wikitext)
                if not section:
                    print("NO SQUAD SECTION FOUND — needs manual check")
                    continue
                players = parse_fs_player_lines(section)
                print(f"{len(players)} players found")

                for p in players:
                    all_rows.append((
                        league,
                        db_name,
                        p.get("shirt_number") or "",
                        p.get("position") or "",
                        p["name"],
                        p.get("nationality_code") or "",
                    ))

                time.sleep(0.5)
            except Exception as e:
                print(f"ERROR: {e}")

    csv_path = "squads_output.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "league", "club", "shirt_number", "position", "player_name", "nationality_code",
        ])
        writer.writerows(all_rows)
    print(f"\nCSV written: {csv_path} ({len(all_rows)} rows)")
    print("For Neon sync run: python footballmind_jobs.py sync-wikipedia")


if __name__ == "__main__":
    main()
