"""Football-data client query params (no network)."""

from datetime import date
from unittest.mock import patch

from footballmind_sync import FootballDataClient, TokenBucket


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
