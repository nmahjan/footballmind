"""Upcoming vs finished fixture classification."""

import datetime as dt
from unittest.mock import patch

from footballmind_services import get_recent_match_results, is_finished_match


def test_is_finished_match_past_with_score():
    now = dt.datetime(2026, 6, 18, 12, 0, tzinfo=dt.timezone.utc)
    kick = dt.datetime(2026, 6, 17, 19, 0, tzinfo=dt.timezone.utc)
    assert is_finished_match(2, 1, kick, now=now)


def test_is_finished_match_live_window():
    now = dt.datetime(2026, 6, 17, 20, 30, tzinfo=dt.timezone.utc)
    kick = dt.datetime(2026, 6, 17, 19, 0, tzinfo=dt.timezone.utc)
    assert not is_finished_match(1, 0, kick, now=now)


def test_is_finished_match_no_score():
    now = dt.datetime(2026, 6, 18, 12, 0, tzinfo=dt.timezone.utc)
    kick = dt.datetime(2026, 6, 17, 19, 0, tzinfo=dt.timezone.utc)
    assert not is_finished_match(None, None, kick, now=now)


class _ResultsCursor:
    def __init__(self):
        self.description = [
            ("id",), ("home_team_id",), ("away_team_id",), ("home",), ("away",),
            ("home_goals",), ("away_goals",), ("match_date",), ("stage",),
            ("went_to_et",), ("went_to_pens",), ("home_pens",), ("away_pens",),
            ("reg_home_goals",), ("reg_away_goals",), ("advances",),
            ("prediction_id",), ("home_win_prob",), ("draw_prob",),
            ("away_win_prob",), ("home_advance_prob",), ("was_correct",),
        ]
        self._rows = [(
            1, 10, 20, "Spain", "France",
            1, 1, dt.date(2026, 7, 10), "semi_final",
            False, True, 4, 3,
            1, 1, "Spain",
            99, 0.38, 0.33, 0.29, 0.71, None,
        )]

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _ResultsConn:
    def cursor(self):
        return _ResultsCursor()


@patch("footballmind_grading.grade_predictions", return_value=0)
@patch("footballmind_grading.ensure_result_predictions", return_value={"linked": 0, "backfilled": 0})
@patch("footballmind_services._bracket_fixture_labels", return_value={})
def test_get_recent_match_results_grades_linked_predictions(_labels, _ensure, _grade):
    """Regression: stray probs.index() raised NameError and broke /api/results."""
    results = get_recent_match_results(_ResultsConn(), comp="WC", limit=5)
    assert len(results) == 1
    row = results[0]
    assert row["predicted"] == "Spain"
    assert row["actual"] == "Spain"
    assert row["was_correct"] is True
