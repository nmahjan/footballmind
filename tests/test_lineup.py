"""Lineup formation normalization (no DB)."""

from footballmind_lineup import FORMATION_SLOTS, normalize_formation


def test_normalize_4321():
    assert normalize_formation("4321") == "4-3-2-1"
    assert normalize_formation("4-3-2-1") == "4-3-2-1"


def test_normalize_4231_is_two_three_one():
    assert normalize_formation("4231") == "4-2-3-1"


def test_4321_in_formation_slots():
    assert "4-3-2-1" in FORMATION_SLOTS
    assert len(FORMATION_SLOTS["4-3-2-1"]) == 11
