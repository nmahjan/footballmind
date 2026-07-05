"""Lineup slot assignment (no DB)."""

from footballmind_lineup import FORMATION_SLOTS, _pick_xi


def _player(pid, name, line_role, goals=0, assists=0, score=50.0, position=None):
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
    }


def test_4321_puts_striker_and_wingers_correctly():
    squad = [
        _player(1, "Raya", "GK", position="GK"),
        _player(2, "Timber", "LB", position="DEF", score=58),
        _player(3, "Saliba", "CB", position="DEF", score=62),
        _player(4, "Gabriel", "CB", position="DEF", score=61),
        _player(5, "White", "RB", position="DEF", score=60),
        _player(6, "Rice", "CDM", position="MID", score=70, assists=3),
        _player(7, "Zubimendi", "CM", position="MID", score=65),
        _player(8, "Odegaard", "CAM", position="MID", score=68, assists=8),
        _player(9, "Saka", "WING", goals=8, assists=14, score=72),
        _player(10, "Martinelli", "WING", goals=6, assists=10, score=66),
        _player(11, "Gyokeres", "ST", goals=22, assists=5, score=75),
        _player(12, "Trossard", "WING", goals=10, assists=6, score=55),
    ]
    xi = _pick_xi(FORMATION_SLOTS["4-3-2-1"], squad, set())
    by_slot = {p["slot"]: p["name"] for p in xi}
    assert by_slot[11] == "Gyokeres"
    assert by_slot[9] in ("Saka", "Martinelli", "Trossard")
    assert by_slot[10] in ("Saka", "Martinelli", "Trossard")
    assert by_slot[9] != by_slot[10]
    assert by_slot[8] == "Odegaard"
    assert by_slot[6] == "Rice"
    assert by_slot[2] == "Timber"
    assert by_slot[3] == "Saliba"
    assert by_slot[4] == "Gabriel"
    assert by_slot[5] == "White"


def test_4231_puts_cdm_and_cam_correctly():
    squad = [
        _player(1, "Keeper", "GK", position="GK"),
        _player(2, "LB", "LB", position="DEF", score=55),
        _player(3, "CB1", "CB", position="DEF", score=60),
        _player(4, "CB2", "CB", position="DEF", score=59),
        _player(5, "RB", "RB", position="DEF", score=56),
        _player(6, "Anchor", "CDM", position="MID", score=70),
        _player(7, "Partner", "CDM", position="MID", score=65),
        _player(8, "LW", "WING", goals=5, assists=7, score=62),
        _player(9, "Ten", "CAM", position="MID", score=72, assists=9),
        _player(10, "RW", "WING", goals=6, assists=8, score=64),
        _player(11, "Striker", "ST", goals=18, score=74),
        _player(12, "CM", "CM", position="MID", score=58),
    ]
    xi = _pick_xi(FORMATION_SLOTS["4-2-3-1"], squad, set())
    by_slot = {p["slot"]: p["name"] for p in xi}
    assert by_slot[9] == "Ten"
    assert by_slot[6] == "Anchor"
    assert by_slot[7] == "Partner"
    assert by_slot[11] == "Striker"
