"""Position-balanced standouts selection (no DB)."""

from footballmind_services import (
    _balance_standouts_by_position,
    _finalize_standouts,
    _has_standout_signal,
)


def _p(name, pos, rating, team="Club"):
    return {
        "name": name,
        "position": pos,
        "standout_rating": rating,
        "team": team,
    }


def test_balance_takes_quota_from_each_position():
    # Defenders dominate absolute ratings (the PL bug).
    players = (
        [_p(f"Def{i}", "DEF", 90 - i * 0.1, f"T{i}") for i in range(30)]
        + [_p(f"Fwd{i}", "FWD", 50 - i * 0.1, f"F{i}") for i in range(10)]
        + [_p(f"Mid{i}", "MID", 48 - i * 0.1, f"M{i}") for i in range(10)]
        + [_p(f"Gk{i}", "GK", 70 - i * 0.1, f"G{i}") for i in range(10)]
    )
    out = _balance_standouts_by_position(players, limit=20)
    counts = {}
    for p in out:
        counts[p["position"]] = counts.get(p["position"], 0) + 1
    assert counts.get("DEF", 0) == 5
    assert counts.get("FWD", 0) == 5
    assert counts.get("MID", 0) == 5
    assert counts.get("GK", 0) == 5
    assert len(out) == 20


def test_balance_picks_strongest_within_each_position():
    players = [
        _p("WeakFwd", "FWD", 40, "A"),
        _p("StrongFwd", "FWD", 55, "B"),
        _p("WeakDef", "DEF", 80, "C"),
        _p("StrongDef", "DEF", 95, "D"),
        _p("Mid", "MID", 50, "E"),
        _p("Gk", "GK", 60, "F"),
    ]
    out = _balance_standouts_by_position(players, limit=4)
    names = {p["name"] for p in out}
    assert "StrongFwd" in names
    assert "StrongDef" in names
    assert "WeakFwd" not in names
    assert "WeakDef" not in names


def test_balance_fills_from_leftovers_when_position_scarce():
    players = (
        [_p(f"Def{i}", "DEF", 90 - i, f"D{i}") for i in range(20)]
        + [_p("OnlyFwd", "FWD", 40, "F0")]
    )
    out = _balance_standouts_by_position(players, limit=8)
    assert any(p["name"] == "OnlyFwd" for p in out)
    assert sum(1 for p in out if p["position"] == "DEF") == 7


def test_finalize_unfiltered_balances_positions():
    players = (
        [_p(f"Def{i}", "DEF", 90 - i * 0.1, f"T{i}") for i in range(40)]
        + [_p(f"Fwd{i}", "FWD", 45 - i * 0.1, f"F{i}") for i in range(10)]
        + [_p(f"Mid{i}", "MID", 44 - i * 0.1, f"M{i}") for i in range(10)]
        + [_p(f"Gk{i}", "GK", 60 - i * 0.1, f"G{i}") for i in range(10)]
    )
    out = _finalize_standouts(players, limit=40)
    counts = {}
    for p in out:
        counts[p["position"]] = counts.get(p["position"], 0) + 1
    assert counts["DEF"] == 10
    assert counts["FWD"] == 10
    assert counts["MID"] == 10
    assert counts["GK"] == 10


def test_finalize_with_position_filter_keeps_global_sort():
    players = [
        _p("D1", "DEF", 99, "A"),
        _p("D2", "DEF", 50, "B"),
        _p("F1", "FWD", 80, "C"),
    ]
    out = _finalize_standouts(players, limit=10, pos_filter="DEF")
    assert [p["name"] for p in out] == ["D1", "D2"]


def test_has_standout_signal_allows_defender_minutes():
    assert _has_standout_signal("DEF", 0, 0, 8, None) is True
    assert _has_standout_signal("DEF", 0, 0, 1, None) is False
    assert _has_standout_signal("FWD", 0, 0, 8, None) is False
    assert _has_standout_signal("FWD", 1, 0, 8, None) is True


def test_balance_allows_same_club_across_positions():
    """Defenders must not consume the team cap before that club's forward."""
    players = [
        _p("ArsenalDef1", "DEF", 95, "Arsenal"),
        _p("ArsenalDef2", "DEF", 94, "Arsenal"),
        _p("ArsenalFwd", "FWD", 50, "Arsenal"),
        _p("OtherMid", "MID", 48, "Chelsea"),
        _p("OtherGk", "GK", 60, "Spurs"),
    ]
    out = _balance_standouts_by_position(players, limit=4)
    names = {p["name"] for p in out}
    assert "ArsenalFwd" in names
    # Cap is 2 per team overall — one DEF + one FWD from Arsenal is fine.
    arsenal = [p for p in out if p["team"] == "Arsenal"]
    assert len(arsenal) <= 2
    assert any(p["position"] == "FWD" for p in arsenal)
