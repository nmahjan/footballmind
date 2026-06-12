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


def test_no_adjustment_without_pressure():
    from footballmind_stakes import apply_stakes_to_lambdas

    lh, la, meta = apply_stakes_to_lambdas(1.5, 1.1, {"high_pressure": False, "labels": []})
    assert meta["applied"] is False
    assert lh == 1.5 and la == 1.1


def test_relegation_lowers_total_xg():
    from footballmind_stakes import apply_stakes_to_lambdas

    stakes = {
        "high_pressure": True,
        "labels": ["Relegation six-pointer"],
        "context": {"stage": "regular_season"},
    }
    lh, la, meta = apply_stakes_to_lambdas(1.6, 1.2, stakes)
    assert meta["applied"]
    assert lh + la < 1.6 + 1.2


def test_pressure_increases_draw_prob():
    from footballmind_predict import predict
    from footballmind_stakes import apply_stakes_to_lambdas

    base = predict(1.7, 1.0, stage="regular_season")
    stakes = {
        "high_pressure": True,
        "labels": ["Top-four clash", "Champions League spot on the line"],
        "context": {"stage": "regular_season"},
    }
    lh, la, _ = apply_stakes_to_lambdas(1.7, 1.0, stakes)
    adj = predict(lh, la, stage="regular_season")
    assert adj["draw_prob"] >= base["draw_prob"]
    assert adj["home_win_prob"] <= base["home_win_prob"] + 0.001
