"""Footballdata.io position parsing (no network)."""

from footballmind_footballdata_io import (
    extract_position_raw,
    map_footballdata_position,
    _unwrap,
)


def test_unwrap_success_payload():
    raw = {"success": True, "data": [{"id": 1, "name": "Arsenal"}]}
    assert _unwrap(raw) == [{"id": 1, "name": "Arsenal"}]


def test_unwrap_error_raises():
    import pytest

    with pytest.raises(RuntimeError, match="Invalid"):
        _unwrap({"success": False, "error": {"message": "Invalid API key"}})


def test_extract_position_variants():
    assert extract_position_raw({"position": "RW"}) == "RW"
    assert extract_position_raw({"primary_position": "Left Back"}) == "Left Back"
    assert extract_position_raw({"position": {"code": "ST", "name": "Striker"}}) == "ST"


def test_map_footballdata_position():
    assert map_footballdata_position("RW") == "WING"
    assert map_footballdata_position("Left Back") == "LB"
    assert map_footballdata_position("Striker") == "ST"
    assert map_footballdata_position("Centre-Back") == "CB"
