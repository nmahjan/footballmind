"""Bench and goalkeeper selection (no DB)."""

from datetime import date

from footballmind_lineup import _gk_rank_key


def test_gk_rank_prefers_career_apps_and_penalizes_youth():
    senior = {"name": "Raya", "recent_starts": 0, "career_apps": 60,
              "appearances": 0, "score": 50, "birth_date": date(1995, 9, 15)}
    backup = {"name": "Kepa", "recent_starts": 0, "career_apps": 10,
              "appearances": 0, "score": 50, "birth_date": date(1994, 10, 3)}
    youth = {"name": "Porter", "recent_starts": 0, "career_apps": 0,
             "appearances": 0, "score": 50, "birth_date": date(2008, 1, 1)}
    ranked = sorted([backup, youth, senior], key=_gk_rank_key)
    assert ranked[0]["name"] == "Raya"
    assert ranked[-1]["name"] == "Porter"
