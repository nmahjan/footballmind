"""Lineup formation normalization and striker/winger roles (no DB)."""

from footballmind_lineup import FORMATION_SLOTS, normalize_formation
from footballmind_services import classify_line_role


def test_normalize_4321():
    assert normalize_formation("4321") == "4-3-2-1"
    assert normalize_formation("4-3-2-1") == "4-3-2-1"


def test_normalize_4231_is_two_three_one():
    assert normalize_formation("4231") == "4-2-3-1"


def test_4321_in_formation_slots():
    assert "4-3-2-1" in FORMATION_SLOTS
    assert FORMATION_SLOTS["4-3-2-1"].count("ST") == 1
    assert FORMATION_SLOTS["4-3-2-1"].count("WING") == 2


def test_striker_vs_winger_by_output():
    st = classify_line_role("Offence", goals=20, assists=4)
    wing = classify_line_role("Offence", goals=8, assists=12)
    assert st == "ST"
    assert wing == "WING"


def test_winger_from_api_string():
    assert classify_line_role("Right Winger") == "WING"
    assert classify_line_role("Centre-Forward") == "ST"
