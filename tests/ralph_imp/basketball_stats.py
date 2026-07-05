"""
Basketball Stats Analyzer
Loads and analyzes college basketball player statistics from a CSV file.
"""

import csv
import os
from typing import Optional


DATA_FILE = os.path.join(os.path.dirname(__file__), "basketball_stats.csv")


def load_stats(filepath: str = DATA_FILE) -> list[dict]:
    """Load player stats from CSV. Returns a list of player dicts with numeric fields cast."""
    players = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            player = {
                "player_name": row["player_name"],
                "team": row["team"],
                "points": float(row["points"]),
                "rebounds": float(row["rebounds"]),
                "assists": float(row["assists"]),
                "turnovers": float(row["turnovers"]) if row["turnovers"].strip() else None,
                "field_goal_pct": float(row["field_goal_pct"]),
                "three_point_pct": float(row["three_point_pct"]),
                "free_throw_pct": float(row["free_throw_pct"]),
            }
            players.append(player)
    return players


def rank_by(players: list[dict], stat: str, top_n: int = 5, ascending: bool = False) -> list[dict]:
    """Return top_n players sorted by stat. Players with None for that stat are excluded."""
    valid = [p for p in players if p.get(stat) is not None]
    sorted_players = sorted(valid, key=lambda p: p[stat], reverse=not ascending)
    return sorted_players[:top_n]


def compute_averages(players: list[dict]) -> dict:
    """Compute league-wide averages for all numeric stats."""
    numeric_stats = ["points", "rebounds", "assists", "turnovers",
                     "field_goal_pct", "three_point_pct", "free_throw_pct"]
    averages = {}
    for stat in numeric_stats:
        values = [p[stat] for p in players if p[stat] is not None]
        averages[stat] = round(sum(values) / len(values), 3) if values else None
    return averages


def efficiency_rating(player: dict) -> Optional[float]:
    """
    Simple efficiency rating: points + rebounds + assists - turnovers.
    Returns None if turnovers is missing.
    """
    if player["turnovers"] is None:
        return None
    return round(
        player["points"] + player["rebounds"] + player["assists"] - player["turnovers"], 2
    )


def summary_report(players: list[dict]) -> str:
    """Generate a human-readable summary report of key stats."""
    lines = ["=" * 50, "COLLEGE BASKETBALL STATS SUMMARY", "=" * 50]

    avgs = compute_averages(players)
    lines.append(f"Total players: {len(players)}")
    lines.append(f"League averages:")
    for stat, val in avgs.items():
        lines.append(f"  {stat:20s}: {val}")

    lines.append("")
    lines.append("Top 5 Scorers:")
    for i, p in enumerate(rank_by(players, "points"), 1):
        lines.append(f"  {i}. {p['player_name']:20s} ({p['team']:12s}) - {p['points']} pts")

    lines.append("")
    lines.append("Top 5 Rebounders:")
    for i, p in enumerate(rank_by(players, "rebounds"), 1):
        lines.append(f"  {i}. {p['player_name']:20s} ({p['team']:12s}) - {p['rebounds']} reb")

    lines.append("")
    lines.append("Top 5 Assist Leaders:")
    for i, p in enumerate(rank_by(players, "assists"), 1):
        lines.append(f"  {i}. {p['player_name']:20s} ({p['team']:12s}) - {p['assists']} ast")

    lines.append("")
    lines.append("Top 5 by Efficiency (pts+reb+ast-to):")
    rated = [(p, efficiency_rating(p)) for p in players if efficiency_rating(p) is not None]
    rated.sort(key=lambda x: x[1], reverse=True)
    for i, (p, rating) in enumerate(rated[:5], 1):
        lines.append(f"  {i}. {p['player_name']:20s} ({p['team']:12s}) - {rating}")

    lines.append("=" * 50)
    return "\n".join(lines)


if __name__ == "__main__":
    players = load_stats()
    print(summary_report(players))
