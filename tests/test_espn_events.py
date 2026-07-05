"""ESPN WC goal / box-stat parsing."""

from unittest.mock import MagicMock, patch

from footballmind_espn_wc import _espn_scoring_events, _stat_value, _sync_espn_key_events


def test_stat_value_reads_saves():
    stats = [{"name": "saves", "value": 4.0}]
    assert _stat_value(stats, "saves") == 4


def test_sync_key_events_inserts_goals():
    summary = {
        "keyEvents": [{
            "scoringPlay": True,
            "type": {"type": "goal"},
            "team": {"displayName": "Argentina"},
            "participants": [
                {"athlete": {"id": "1", "displayName": "Lionel Messi"}},
                {"athlete": {"id": "2", "displayName": "Assist Guy"}},
            ],
            "clock": {"value": 1200.0},
        }],
    }
    cur = MagicMock()
    name_to_id = {"Argentina": 5}
    with patch(
        "footballmind_espn_wc._resolve_or_create_player",
        side_effect=[100, 101],
    ) as resolve:
        n = _sync_espn_key_events(cur, 42, summary, name_to_id)
    assert n == 1
    assert resolve.call_count == 2
    insert_sql = cur.execute.call_args_list[-1][0][0]
    assert "INSERT INTO match_events" in insert_sql


def test_sync_key_events_skips_delete_without_scoring_plays():
    summary = {"keyEvents": [{"scoringPlay": False, "type": {"type": "substitution"}}]}
    cur = MagicMock()
    n = _sync_espn_key_events(cur, 42, summary, {})
    assert n == 0
    delete_sql = [call[0][0] for call in cur.execute.call_args_list]
    assert not any("DELETE FROM match_events" in s for s in delete_sql)


def test_espn_scoring_events_filters_non_scoring():
    summary = {
        "keyEvents": [
            {"scoringPlay": True, "type": {"type": "goal"}},
            {"scoringPlay": False, "type": {"type": "yellowcard"}},
        ],
    }
    assert len(_espn_scoring_events(summary)) == 1
