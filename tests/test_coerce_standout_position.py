"""Standout position coercion (no DB)."""

from footballmind_services import _coerce_standout_position, normalize_position


def test_null_position_with_goals_is_not_gk():
    assert _coerce_standout_position(None, goals=3, assists=1) == "FWD"


def test_null_position_scorer_defaults_forward_or_mid():
    assert _coerce_standout_position(None, goals=0, assists=4) == "MID"


def test_null_position_saves_only_is_gk():
    assert _coerce_standout_position(None, saves=6) == "GK"


def test_offence_normalizes_to_fwd():
    assert normalize_position("Offence") == "FWD"
    assert _coerce_standout_position("Offence", goals=2) == "FWD"
