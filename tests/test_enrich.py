"""Enrichment helpers (no network)."""

from unittest.mock import MagicMock, patch

from footballmind_enrich import (
    _fpl_team_name,
    _norm,
    _parse_understat_matches,
    sync_fpl_availability,
)


def test_norm_strips_accents():
    assert _norm("Martin Ødegaard") == "martin odegaard"


def test_fpl_team_name_mapping():
    assert _fpl_team_name({"name": "Man City"}) == "Manchester City FC"
    assert _fpl_team_name({"name": "Arsenal"}) == "Arsenal FC"
    assert _fpl_team_name({"name": "Bournemouth"}) == "AFC Bournemouth"
    assert _fpl_team_name({"name": "Sunderland"}) == "Sunderland AFC"


def test_parse_understat_matches_string_json():
    raw = {"dates": '[{"id": "1", "isResult": true}]'}
    assert len(_parse_understat_matches(raw)) == 1


def test_sync_fpl_skips_available_players():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    payload = {
        "teams": [{"id": 1, "name": "Arsenal"}],
        "elements": [
            {"id": 10, "team": 1, "status": "a", "web_name": "Saka",
             "first_name": "Bukayo", "second_name": "Saka"},
            {"id": 11, "team": 1, "status": "i", "web_name": "White",
             "first_name": "Ben", "second_name": "White", "news": "Knee injury"},
        ],
    }
    with patch("footballmind_enrich._get_json", return_value=payload), patch(
        "footballmind_enrich._resolve_team_id", return_value=42
    ), patch("footballmind_enrich._resolve_player_on_team", return_value=99):
        n = sync_fpl_availability(conn)
    assert n == 1
    delete_sql = cur.execute.call_args_list[0][0][0]
    assert "source = 'fpl'" in delete_sql
