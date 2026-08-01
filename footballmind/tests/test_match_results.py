"""Upcoming vs finished fixture classification."""

import datetime as dt
from unittest.mock import MagicMock, patch

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


def test_get_recent_match_results_with_prediction():
    """Regression: stray probs.index() caused NameError on /api/results."""
    class FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, sql, params=None):
            self.description = [
                ("id",), ("home_team_id",), ("away_team_id",), ("home",), ("away",),
                ("home_goals",), ("away_goals",), ("match_date",), ("stage",),
                ("went_to_et",), ("went_to_pens",), ("home_pens",), ("away_pens",),
                ("reg_home_goals",), ("reg_away_goals",), ("advances",),
                ("prediction_id",), ("home_win_prob",), ("draw_prob",), ("away_win_prob",),
                ("home_advance_prob",), ("was_correct",),
            ]
            self._rows = [
                (1, 10, 20, "France", "Germany", 2, 1,
                 dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc), "group",
                 False, False, None, None, 2, 1, None,
                 99, 0.55, 0.25, 0.20, None, None),
            ]
        def fetchall(self):
            return self._rows

    conn = MagicMock()
    conn.cursor.return_value = FakeCursor()

    with patch("footballmind_grading.ensure_result_predictions"), \
         patch("footballmind_grading.grade_predictions"), \
         patch("footballmind_services._bracket_fixture_labels", return_value={}):
        results = get_recent_match_results(conn, "WC", 10)

    assert len(results) == 1
    assert results[0]["predicted"] == "France"
    assert results[0]["was_correct"] is True
