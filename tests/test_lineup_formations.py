"""Formation layout and national-team XI heuristics (no DB)."""

from datetime import date

from footballmind_lineup import (
    FORMATION_SLOTS,
    _eligible_starter,
    _formation_rows,
    _pick_formation,
    _pick_xi,
    _rows_from_confirmed_starters,
)


def _player(pid, name, line_role, goals=0, assists=0, score=50.0, position=None,
            birth_date=None, appearances=20):
    coarse = position or {
        "GK": "GK", "LB": "DEF", "RB": "DEF", "CB": "DEF",
        "CDM": "MID", "CM": "MID", "CAM": "MID",
        "ST": "FWD", "WING": "FWD",
    }.get(line_role, "MID")
    return {
        "player_id": pid,
        "name": name,
        "position": coarse,
        "line_role": line_role,
        "goals": goals,
        "assists": assists,
        "score": score,
        "birth_date": birth_date,
        "appearances": appearances,
    }


def test_442_midfield_on_one_row():
    squad = [
        _player(1, "Keeper", "GK", position="GK"),
        _player(2, "LB", "LB", position="DEF", score=55),
        _player(3, "CB1", "CB", position="DEF", score=60),
        _player(4, "CB2", "CB", position="DEF", score=59),
        _player(5, "RB", "RB", position="DEF", score=56),
        _player(6, "CM1", "CM", position="MID", score=65),
        _player(7, "CM2", "CM", position="MID", score=64),
        _player(8, "LW", "WING", goals=5, assists=7, score=68),
        _player(9, "RW", "WING", goals=6, assists=8, score=67),
        _player(10, "ST1", "ST", goals=12, score=70),
        _player(11, "ST2", "ST", goals=10, score=69),
    ]
    xi = _pick_xi(FORMATION_SLOTS["4-4-2"], squad, set())
    rows = _formation_rows(xi, "4-4-2")
    mid_rows = [r for r in rows if r["line"] == "MID"]
    assert len(mid_rows) == 1
    assert len(mid_rows[0]["players"]) == 4


def test_established_teen_winger_eligible():
    yamal = _player(
        99, "Lamine Yamal", "WING", score=93.6,
        birth_date=date(2007, 7, 13), appearances=3,
    )
    assert _eligible_starter(yamal)


def test_national_prefers_wide_shape_for_spain_like_squad():
    squad = [
        _player(1, "GK", "GK", position="GK"),
        _player(2, "LB", "LB", position="DEF", score=60),
        _player(3, "CB1", "CB", position="DEF", score=62),
        _player(4, "CB2", "CB", position="DEF", score=61),
        _player(5, "RB", "RB", position="DEF", score=59),
        _player(6, "Pivot", "CDM", position="MID", score=70),
        _player(7, "CM1", "CM", position="MID", score=68),
        _player(8, "CM2", "CM", position="MID", score=66),
        _player(9, "Yamal", "WING", goals=8, assists=14, score=94),
        _player(10, "ST", "ST", goals=15, score=72),
        _player(11, "Williams", "WING", goals=6, assists=10, score=78),
        _player(12, "Extra CM", "CM", position="MID", score=55),
    ]
    formation = _pick_formation(squad, None, "national")
    assert formation in ("4-3-3", "4-2-3-1", "4-4-2", "4-1-4-1", "4-3-2-1", "3-4-3")
    xi = _pick_xi(FORMATION_SLOTS[formation], squad, set())
    names = {p["name"] for p in xi}
    assert "Yamal" in names


def test_confirmed_rows_use_synced_starters():
    roster = {
        1: _player(1, "Keeper", "GK", position="GK"),
        2: _player(2, "LB", "LB", position="DEF"),
        3: _player(3, "CB", "CB", position="DEF"),
        4: _player(4, "CB2", "CB", position="DEF"),
        5: _player(5, "RB", "RB", position="DEF"),
        6: _player(6, "CDM", "CDM", position="MID"),
        7: _player(7, "CM", "CM", position="MID"),
        8: _player(8, "Wing", "WING", position="FWD"),
        9: _player(9, "ST", "ST", position="FWD"),
        10: _player(10, "Wing2", "WING", position="FWD"),
        11: _player(11, "CM2", "CM", position="MID"),
    }
    starters = [
        {"player_id": i, "name": roster[i]["name"], "position": roster[i]["position"],
         "shirt_number": i}
        for i in range(1, 12)
    ]
    rows = _rows_from_confirmed_starters(starters, roster)
    all_names = {p["name"] for r in rows for p in r["players"]}
    assert len(all_names) == 11
    assert "Keeper" in all_names
