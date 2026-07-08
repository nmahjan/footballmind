"""Quick-refit job helpers (no database)."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from footballmind_jobs import cmd_quick_refit


def test_quick_refit_if_new_results_uses_rating_history():
    """--if-new-results must not reference matches.updated_at (column does not exist)."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [
        ("2026-07-01T00:00:00+00:00",),  # MIN(trained_at)
        None,  # no new rating_history rows
    ]

    @contextmanager
    def fake_connect():
        yield conn

    with patch("footballmind_jobs._connect", fake_connect), \
         patch("footballmind_jobs._editions_for") as editions:
        cmd_quick_refit(if_new_results=True)

    sqls = [call[0][0] for call in cur.execute.call_args_list]
    assert any("rating_history" in s and "as_of" in s for s in sqls)
    assert not any("matches" in s and "updated_at" in s for s in sqls)
    editions.assert_not_called()
