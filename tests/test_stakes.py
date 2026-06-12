"""Match stakes labels (no DB)."""

from footballmind_stakes import _build_summary, _group_labels, _league_labels


def test_relegation_six_pointer():
    home = {"rank": 18, "zone": {"id": "rel", "short": "REL"}}
    away = {"rank": 19, "zone": {"id": "rel", "short": "REL"}}
    labels = _league_labels(home, away)
    assert "Relegation six-pointer" in labels
    assert "relegation zone" in _build_summary(labels, "regular_season", home, away).lower()


def test_top_four_clash():
    home = {"rank": 3, "zone": {"id": "ucl"}}
    away = {"rank": 4, "zone": {"id": "ucl"}}
    labels = _league_labels(home, away)
    assert "Top-four clash" in labels


def test_ucl_vs_uel_spot():
    home = {"rank": 4, "zone": {"id": "ucl"}}
    away = {"rank": 5, "zone": {"id": "uel"}}
    labels = _league_labels(home, away)
    assert "Champions League spot on the line" in labels


def test_group_must_win():
    labels = _group_labels(3, 4, 3, 4)
    assert "Knockout qualification on the line" in labels


def test_knockout_summary():
    s = _build_summary([], "quarter_final", None, None)
    assert "Knockout" in s
