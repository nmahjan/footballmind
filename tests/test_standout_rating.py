"""Position-aware standout rating (no DB)."""

from footballmind_services import _compute_standout_rating


def test_midfielder_with_assists_ranks_well():
    mid = _compute_standout_rating(1700, 5, 14, 34, "MID")
    assert mid >= 55


def test_goalkeeper_uses_appearances_not_goals():
    starter = _compute_standout_rating(1750, 0, 0, 36, "GK")
    backup = _compute_standout_rating(1750, 0, 0, 8, "GK")
    assert starter > backup


def test_defender_favoured_by_minutes():
    regular = _compute_standout_rating(1720, 1, 2, 35, "DEF")
    fringe = _compute_standout_rating(1720, 1, 2, 10, "DEF")
    assert regular > fringe


def test_forward_favoured_by_goals():
    scorer = _compute_standout_rating(1700, 18, 4, 32, "FWD")
    low = _compute_standout_rating(1700, 4, 4, 32, "FWD")
    assert scorer > low
