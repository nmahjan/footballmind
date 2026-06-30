"""FDO v4 score parsing (no network)."""

from footballmind_sync import (
    _derive_pen_score,
    _parse_fdo_scores,
    _playing_time_score,
    _score_side,
)


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


def test_playing_time_score_sums_regular_and_extra():
    score = {
        "regularTime": {"homeTeam": 2, "awayTeam": 2},
        "extraTime": {"homeTeam": 1, "awayTeam": 1},
    }
    assert _playing_time_score(score) == (3, 3)


def test_derive_pen_score_from_fulltime_aggregate():
    score = {
        "fullTime": {"homeTeam": 7, "awayTeam": 6},
        "regularTime": {"homeTeam": 1, "awayTeam": 1},
        "extraTime": {"homeTeam": 0, "awayTeam": 0},
    }
    assert _derive_pen_score(score) == (6, 5)


def test_parse_fdo_scores_pen_shootout():
    m = {
        "status": "FINISHED",
        "score": {
            "duration": "PENALTY_SHOOTOUT",
            "winner": "AWAY_TEAM",
            "fullTime": {"homeTeam": 7, "awayTeam": 7},
            "regularTime": {"homeTeam": 2, "awayTeam": 2},
            "extraTime": {"homeTeam": 1, "awayTeam": 1},
            "penalties": {"homeTeam": 3, "awayTeam": 4},
        },
        "goals": [],
    }
    parsed = _parse_fdo_scores(m)
    assert parsed["home_goals"] == 3
    assert parsed["away_goals"] == 3
    assert parsed["went_to_pens"] is True
    assert parsed["home_pens"] == 3
    assert parsed["away_pens"] == 4


def test_parse_fdo_scores_pen_shootout_derives_pens_when_api_tied():
    """When score.penalties is wrongly tied, derive from fullTime aggregate."""
    m = {
        "status": "FINISHED",
        "homeTeam": {"id": 1},
        "awayTeam": {"id": 2},
        "score": {
            "duration": "PENALTY_SHOOTOUT",
            "winner": "AWAY_TEAM",
            "fullTime": {"homeTeam": 6, "awayTeam": 7},
            "regularTime": {"homeTeam": 2, "awayTeam": 2},
            "extraTime": {"homeTeam": 1, "awayTeam": 1},
            "penalties": {"homeTeam": 3, "awayTeam": 3},
        },
        "goals": [{"score": {"home": 3, "away": 4}}],
    }
    parsed = _parse_fdo_scores(m)
    assert parsed["home_goals"] == 3
    assert parsed["away_goals"] == 3
    assert parsed["home_pens"] == 3
    assert parsed["away_pens"] == 4


def test_parse_fdo_scores_pen_shootout_from_kick_list():
    m = {
        "status": "FINISHED",
        "homeTeam": {"id": 10},
        "awayTeam": {"id": 20},
        "score": {
            "duration": "PENALTY_SHOOTOUT",
            "winner": "HOME_TEAM",
            "fullTime": {"homeTeam": 5, "awayTeam": 4},
            "regularTime": {"homeTeam": 1, "awayTeam": 1},
            "extraTime": {"homeTeam": 0, "awayTeam": 0},
            "penalties": {"homeTeam": 2, "awayTeam": 2},
        },
        "penalties": [
            {"team": {"id": 10}, "scored": True},
            {"team": {"id": 10}, "scored": True},
            {"team": {"id": 10}, "scored": True},
            {"team": {"id": 10}, "scored": True},
            {"team": {"id": 20}, "scored": True},
            {"team": {"id": 20}, "scored": True},
            {"team": {"id": 20}, "scored": True},
        ],
    }
    parsed = _parse_fdo_scores(m)
    assert parsed["home_goals"] == 1
    assert parsed["away_goals"] == 1
    assert parsed["home_pens"] == 4
    assert parsed["away_pens"] == 3
