"""Lineup slot assignment (no DB)."""

from footballmind_lineup import FORMATION_SLOTS, _pick_xi


def _player(pid, name, line_role, goals=0, assists=0, score=50.0, position="FWD"):
    return {
        "player_id": pid,
        "name": name,
        "position": position,
        "line_role": line_role,
        "goals": goals,
        "assists": assists,
        "score": score,
    }


def test_4321_puts_striker_and_wingers_correctly():
    squad = [
        _player(1, "Raya", "GK", position="GK"),
        _player(2, "White", "DEF", position="DEF", score=60),
        _player(3, "Saliba", "DEF", position="DEF", score=62),
        _player(4, "Gabriel", "DEF", position="DEF", score=61),
        _player(5, "Timber", "DEF", position="DEF", score=58),
        _player(6, "Rice", "MID", position="MID", score=70, assists=3),
        _player(7, "Zubimendi", "MID", position="MID", score=65),
        _player(8, "Odegaard", "MID", position="MID", score=68, assists=8),
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
