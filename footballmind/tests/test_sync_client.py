"""Football-data client query params (no network)."""

from unittest.mock import MagicMock, patch

from footballmind_sync import (
    FootballDataClient,
    TokenBucket,
    _api_match_has_events,
    _api_match_has_lineup,
    _sync_match_events,
)


def test_matches_pairs_date_to_with_date_from():
    """football-data.org returns 400 when dateFrom is sent without dateTo."""
    client = FootballDataClient("test-key", TokenBucket(10))
    with patch.object(client, "_get", return_value={"matches": []}) as get:
        client.matches("WC", status=None, date_from="2026-06-02")
    params = get.call_args[0][1]
    assert params["dateFrom"] == "2026-06-02"
    assert "dateTo" in params
    assert params["dateTo"] >= "2026-06-02"
    assert "status" not in params


def test_matches_respects_explicit_date_to():
    client = FootballDataClient("test-key", TokenBucket(10))
    with patch.object(client, "_get", return_value={"matches": []}) as get:
        client.matches("PL", date_from="2026-08-10", date_to="2026-08-20")
    params = get.call_args[0][1]
    assert params["dateFrom"] == "2026-08-10"
    assert params["dateTo"] == "2026-08-20"


def test_matches_passes_season_year():
    client = FootballDataClient("test-key", TokenBucket(10))
    with patch.object(client, "_get", return_value={"matches": []}) as get:
        client.matches("PL", season=2026)
    assert get.call_args[0][1]["season"] == 2026


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


def test_api_match_has_events_false_when_only_lineup():
    m = {
        "homeTeam": {"name": "Spain", "lineup": [{"name": "Simon"}]},
        "awayTeam": {"name": "Germany"},
    }
    assert _api_match_has_events(m) is False


def test_sync_match_events_skips_event_delete_without_api_events():
    """Lineup-only FDO payloads must not wipe ESPN goal timelines."""
    cur = MagicMock()
    m = {
        "homeTeam": {"name": "Spain", "id": 1, "lineup": [{"name": "Simon"}]},
        "awayTeam": {"name": "Germany", "id": 2, "lineup": [{"name": "Neuer"}]},
    }
    with patch("footballmind_sync.upsert_team", return_value=1), \
         patch("footballmind_sync._resolve_player_id", return_value=None):
        _sync_match_events(cur, 42, m, "national", "national")

    delete_sql = [call[0][0] for call in cur.execute.call_args_list]
    assert not any("DELETE FROM match_events" in s for s in delete_sql)
    assert any("DELETE FROM match_lineup_players" in s for s in delete_sql)


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
