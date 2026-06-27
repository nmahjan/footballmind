"""Football-data client query params (no network)."""

from datetime import date
from unittest.mock import MagicMock, patch

from footballmind_sync import (
    FootballDataClient,
    TokenBucket,
    _api_match_has_lineup,
    _sync_match_events,
)


def test_matches_adds_date_to_when_date_from_set():
    client = FootballDataClient("test-key", TokenBucket(10))
    with patch.object(client, "_get", return_value={"matches": []}) as get:
        client.matches("WC", status=None, date_from="2026-06-02")
    params = get.call_args[0][1]
    assert params["dateFrom"] == "2026-06-02"
    assert params["dateTo"] == date.today().isoformat()
    assert "status" not in params


def test_scorers_default_limit_is_500():
    client = FootballDataClient("test-key", TokenBucket(10))
    with patch.object(client, "_get", return_value={"scorers": []}) as get:
        client.scorers("PL", season=2025)
    assert get.call_args[0][1]["limit"] == 500


def test_matches_omits_status_when_none():
    client = FootballDataClient("test-key", TokenBucket(10))
    with patch.object(client, "_get", return_value={"matches": []}) as get:
        client.matches("WC")
    assert "status" not in get.call_args[0][1]


def test_api_match_has_lineup_false_when_only_goals():
    m = {
        "goals": [{"team": {"name": "Spain"}, "scorer": {"name": "Morata"}}],
        "homeTeam": {"name": "Spain"},
        "awayTeam": {"name": "Germany"},
    }
    assert _api_match_has_lineup(m) is False


def test_api_match_has_lineup_true_when_xi_present():
    m = {
        "homeTeam": {"name": "Spain", "lineup": [{"name": "Simon"}]},
        "awayTeam": {"name": "Germany"},
    }
    assert _api_match_has_lineup(m) is True


def test_sync_match_events_skips_lineup_delete_without_api_lineup():
    cur = MagicMock()
    m = {
        "goals": [{
            "team": {"name": "Spain", "id": 1},
            "scorer": {"name": "Morata"},
            "type": "REGULAR",
            "minute": 10,
        }],
        "homeTeam": {"name": "Spain", "id": 1},
        "awayTeam": {"name": "Germany", "id": 2},
    }
    with patch("footballmind_sync.upsert_team", return_value=1), \
         patch("footballmind_sync._resolve_player_id", return_value=None):
        _sync_match_events(cur, 42, m, "national", "national")

    delete_sql = [call[0][0] for call in cur.execute.call_args_list]
    assert any("DELETE FROM match_events" in s for s in delete_sql)
    assert not any("DELETE FROM match_lineup_players" in s for s in delete_sql)
    assert not any("DELETE FROM match_team_lineups" in s for s in delete_sql)
