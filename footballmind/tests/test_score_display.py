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


def test_get_recent_match_results_with_prediction_does_not_crash():
    """Regression: stray probs.index() caused NameError on /api/results."""
    import datetime as dt
    from unittest.mock import MagicMock, patch

    with patch("footballmind_grading.ensure_result_predictions", return_value={}), \
         patch("footballmind_grading.grade_predictions", return_value=0), \
         patch("footballmind_services._bracket_fixture_labels", return_value={}):
        from footballmind_services import get_recent_match_results

        class _Cur:
            description = [
                ("id",), ("home_team_id",), ("away_team_id",), ("home",), ("away",),
                ("home_goals",), ("away_goals",), ("match_date",), ("stage",),
                ("went_to_et",), ("went_to_pens",), ("home_pens",), ("away_pens",),
                ("reg_home_goals",), ("reg_away_goals",), ("advances",),
                ("prediction_id",), ("home_win_prob",), ("draw_prob",),
                ("away_win_prob",), ("home_advance_prob",), ("was_correct",),
            ]

            def execute(self, *args, **kwargs):
                pass

            def fetchall(self):
                return [(
                    1, 1, 2, "Spain", "France", 2, 1,
                    dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc), "group",
                    False, False, None, None, None, None, None,
                    99, 0.5, 0.3, 0.2, None, True,
                )]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        conn = MagicMock()
        conn.cursor.return_value = _Cur()
        out = get_recent_match_results(conn, "WC", 10)
        assert len(out) == 1
        assert out[0]["was_correct"] is True
        assert out[0]["predicted"] == "Spain"
