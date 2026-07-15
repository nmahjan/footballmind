"""Score display formatting."""

from footballmind_services import (
    _format_match_score,
    _match_actual_outcome,
    _prediction_outcome_for_match,
)


def test_pen_shootout_shows_regulation_score():
    assert _format_match_score(
        3, 3, went_to_pens=True, home_pens=3, away_pens=4,
        reg_home=1, reg_away=1,
    ) == "1–1 (3–4 pens)"


def test_extra_time_without_pens():
    assert _format_match_score(3, 4, went_to_et=True) == "3–4 (aet)"


def test_pen_shootout_without_pen_totals():
    assert _format_match_score(
        1, 1, went_to_pens=True, went_to_et=True,
        reg_home=1, reg_away=1,
    ) == "1–1 (pens)"


def test_regular_finish():
    assert _format_match_score(2, 1) == "2–1"


def test_pen_shootout_actual_outcome():
    actual = _match_actual_outcome(
        "Netherlands", "Morocco", 1, 1, "round_of_32",
        went_to_pens=True, home_pens=2, away_pens=3,
    )
    assert actual == "Morocco"


def test_knockout_prediction_display_uses_advance_probability():
    predicted, confidence, idx = _prediction_outcome_for_match(
        "Spain", "France", "semi_final",
        0.38, 0.33, 0.29, home_advance_prob=0.71,
    )
    assert predicted == "Spain"
    assert confidence == 0.71
    assert idx == 0


def test_group_prediction_display_uses_regulation_probability():
    predicted, confidence, idx = _prediction_outcome_for_match(
        "Spain", "France", "group",
        0.38, 0.33, 0.29, home_advance_prob=0.71,
    )
    assert predicted == "Spain"
    assert confidence == 0.38
    assert idx == 0
