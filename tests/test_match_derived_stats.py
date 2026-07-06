"""Competition-scoped stats from match events (no live DB)."""

from unittest.mock import MagicMock, patch

from footballmind_services import (
    _edition_player_stats_from_matches,
    _prefer_match_derived_stats,
)


def _mock_conn(fetchall_side_effects):
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_side_effects
    cur.fetchone.side_effect = [None] * 10
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_prefer_match_derived_for_international():
    conn = MagicMock()
    with patch("footballmind_services._affil_kind_for_comp", return_value="national"):
        assert _prefer_match_derived_stats(conn, "WC", 39) is True


def test_edition_player_stats_aggregates():
    conn, cur = _mock_conn([
        [(10, 2), (11, 1)],   # goals
        [(12, 1)],             # assists
        [(10, 3, 100), (11, 2, 101)],  # apps
        [(13, 8)],             # saves
    ])
    stats = _edition_player_stats_from_matches(conn, 39)
    assert stats[10]["goals"] == 2
    assert stats[10]["appearances"] == 3
    assert stats[12]["assists"] == 1
    assert stats[13]["saves"] == 8
