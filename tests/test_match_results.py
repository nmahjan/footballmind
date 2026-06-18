"""Upcoming vs finished fixture classification."""

import datetime as dt

from footballmind_services import is_finished_match


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
