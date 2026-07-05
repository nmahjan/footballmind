"""Position-aware standout rating (no DB)."""

from footballmind_services import _compute_standout_rating


def test_midfielder_with_assists_ranks_well():
    mid = _compute_standout_rating(1700, 5, 14, 34, "MID")
    assert mid >= 55


def test_goalkeeper_low_ga_beats_high_ga():
    stingy = _compute_standout_rating(1750, 0, 0, 34, "GK", ga_per_game=0.8, clean_sheets=14, team_gp=34)
    leaky = _compute_standout_rating(1750, 0, 0, 34, "GK", ga_per_game=1.9, clean_sheets=4, team_gp=34)
    assert stingy > leaky


def test_goalkeeper_with_saves_ranks_higher():
    active = _compute_standout_rating(1720, 0, 0, 30, "GK", ga_per_game=1.1, saves=95, team_gp=30)
    quiet = _compute_standout_rating(1720, 0, 0, 30, "GK", ga_per_game=1.1, saves=40, team_gp=30)
    assert active > quiet


def test_goalkeeper_uses_appearances_not_goals():
    starter = _compute_standout_rating(1750, 0, 0, 36, "GK", ga_per_game=1.0, team_gp=36)
    backup = _compute_standout_rating(1750, 0, 0, 8, "GK", ga_per_game=1.0, team_gp=36)
    assert starter > backup


def test_defender_strong_defense_beats_weak():
    solid = _compute_standout_rating(1720, 1, 2, 35, "DEF", ga_per_game=0.9, clean_sheets=16, team_gp=35)
    porous = _compute_standout_rating(1720, 1, 2, 35, "DEF", ga_per_game=1.8, clean_sheets=5, team_gp=35)
    assert solid > porous


def test_defender_favoured_by_minutes():
    regular = _compute_standout_rating(1720, 1, 2, 35, "DEF", ga_per_game=1.1, clean_sheets=10, team_gp=35)
    fringe = _compute_standout_rating(1720, 1, 2, 10, "DEF", ga_per_game=1.1, clean_sheets=10, team_gp=35)
    assert regular > fringe


def test_forward_favoured_by_goals():
    scorer = _compute_standout_rating(1700, 18, 4, 32, "FWD")
    low = _compute_standout_rating(1700, 4, 4, 32, "FWD")
    assert scorer > low
