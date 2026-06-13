"""ESPN WC lineup ingest helpers (no network)."""

from footballmind_espn_wc import (
    _espn_team_name,
    _event_finished,
    _parse_event_teams,
    _find_espn_event_for_match,
)


def test_espn_team_alias():
    assert _espn_team_name("USA") == "United States"
    assert _espn_team_name("Argentina") == "Argentina"


def test_parse_event_teams():
    event = {
        "id": "633850",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Argentina"}},
                {"homeAway": "away", "team": {"displayName": "France"}},
            ],
        }],
    }
    assert _parse_event_teams(event) == ("Argentina", "France", "633850")


def test_event_finished():
    done = {"competitions": [{"status": {"type": {"completed": True}}}]}
    live = {"competitions": [{"status": {"type": {"completed": False}}}]}
    assert _event_finished(done) is True
    assert _event_finished(live) is False


def test_find_espn_event_for_match():
    events = [{
        "id": "1",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Mexico"}},
                {"homeAway": "away", "team": {"displayName": "United States"}},
            ],
        }],
    }]
    found = _find_espn_event_for_match(events, "Mexico", "United States")
    assert found and found["id"] == "1"
    assert _find_espn_event_for_match(events, "Brazil", "Argentina") is None
