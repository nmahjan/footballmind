"""Score display formatting."""

from footballmind_services import _format_match_score


def test_pen_shootout_shows_regulation_score():
    assert _format_match_score(
        3, 3, went_to_pens=True, home_pens=3, away_pens=4,
        reg_home=1, reg_away=1,
    ) == "1–1 Pens (3–4)"


def test_extra_time_without_pens():
    assert _format_match_score(3, 4, went_to_et=True) == "3–4 (aet)"


def test_pen_shootout_without_pen_totals():
    assert _format_match_score(
        1, 1, went_to_pens=True, went_to_et=True,
        reg_home=1, reg_away=1,
    ) == "1–1 Pens"


def test_regular_finish():
    assert _format_match_score(2, 1) == "2–1"
