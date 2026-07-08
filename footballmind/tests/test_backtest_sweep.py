from datetime import date, timedelta

import pytest

from footballmind_backtest import sweep


def test_sweep_raises_when_no_folds_score():
    today = date.today()
    matches = [
        {"home": 1, "away": 2, "hg": 1, "ag": 0, "date": today - timedelta(days=3),
         "neutral": False},
    ]
    with pytest.raises(ValueError, match="no backtest folds scored"):
        sweep(matches, test_start=today - timedelta(days=30), min_history=60)
