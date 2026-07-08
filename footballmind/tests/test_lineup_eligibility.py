"""Starter eligibility and CDM selection (no DB)."""

from datetime import date

from footballmind_lineup import FORMATION_SLOTS, _eligible_starter, _pick_formation, _pick_xi


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


def test_youth_academy_not_model_picked():
    youth = _player(99, "Academy Kid", "CDM", score=80, birth_date=date(2009, 12, 31), appearances=3)
    assert not _eligible_starter(youth)


def test_cdm_prefers_senior_cm_over_youth_cdm():
    squad = [
        _player(1, "Keeper", "GK", position="GK"),
        _player(2, "LB", "LB", position="DEF", score=55),
        _player(3, "CB1", "CB", position="DEF", score=60),
        _player(4, "CB2", "CB", position="DEF", score=59),
        _player(5, "RB", "RB", position="DEF", score=56),
        _player(6, "Rice", "CM", position="MID", score=71, assists=3),
        _player(7, "Partner", "CM", position="MID", score=65),
        _player(8, "LW", "WING", goals=5, assists=7, score=62),
        _player(9, "Ten", "CAM", position="MID", score=72, assists=9),
        _player(10, "RW", "WING", goals=6, assists=8, score=64),
        _player(11, "Striker", "ST", goals=18, score=74),
        _player(12, "Youth", "CDM", score=48, birth_date=date(2009, 12, 31), appearances=3),
    ]
    xi = _pick_xi(FORMATION_SLOTS["4-2-3-1"], squad, set())
    names = {p["name"] for p in xi}
    assert "Youth" not in names
    assert "Rice" in names


def test_club_formation_prefers_4231():
    squad = [
        _player(i, f"P{i}", "CM", score=50 + i) for i in range(1, 12)
    ]
    squad[0] = _player(1, "GK", "GK", position="GK")
    for i, role in enumerate(["LB", "CB", "CB", "RB", "CDM", "CM", "WING", "CAM", "WING", "ST"], start=2):
        squad[i - 1] = _player(i, f"P{i}", role, score=55 + i,
                                 position={"LB": "DEF", "CB": "DEF", "RB": "DEF"}.get(role, None))
    assert _pick_formation(squad, None, "club") == "4-2-3-1"
