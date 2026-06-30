"""FDO v4 score parsing (no network)."""

from footballmind_sync import _parse_fdo_scores, _score_side


def test_score_side_accepts_home_team_keys():
    assert _score_side({"homeTeam": 3, "awayTeam": 4}, home=True) == 3
    assert _score_side({"homeTeam": 3, "awayTeam": 4}, home=False) == 4
    assert _score_side({"home": 2, "away": 1}, home=True) == 2


def test_parse_fdo_scores_prefers_goal_timeline():
    m = {
        "status": "FINISHED",
        "score": {
            "duration": "EXTRA_TIME",
            "winner": "AWAY_TEAM",
            "fullTime": {"homeTeam": 4, "awayTeam": 4},
            "regularTime": {"homeTeam": 2, "awayTeam": 2},
            "extraTime": {"homeTeam": 2, "awayTeam": 2},
        },
        "goals": [
            {"score": {"home": 0, "away": 1}},
            {"score": {"home": 3, "away": 4}},
        ],
    }
    parsed = _parse_fdo_scores(m)
    assert parsed["home_goals"] == 3
    assert parsed["away_goals"] == 4
    assert parsed["went_to_et"] is True
    assert parsed["winner"] == "AWAY_TEAM"


def test_parse_fdo_scores_pen_shootout():
    m = {
        "status": "FINISHED",
        "score": {
            "duration": "PENALTY_SHOOTOUT",
            "winner": "AWAY_TEAM",
            "fullTime": {"homeTeam": 4, "awayTeam": 4},
            "penalties": {"homeTeam": 3, "awayTeam": 4},
        },
        "goals": [],
    }
    parsed = _parse_fdo_scores(m)
    assert parsed["home_goals"] == 4
    assert parsed["away_goals"] == 4
    assert parsed["went_to_pens"] is True
    assert parsed["home_pens"] == 3
    assert parsed["away_pens"] == 4
