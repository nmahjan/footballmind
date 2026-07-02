"""Sync job status helpers."""

from footballmind_sync_status import _repeat_skips, record_sync_run


class _FakeCursor:
    def __init__(self, prev_summary=None):
        self.prev_summary = prev_summary
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))
        self._fetch = [self.prev_summary] if "SELECT summary" in sql else []

    def fetchone(self):
        return self._fetch[0] if self._fetch else None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeConn:
    def __init__(self, prev_summary=None):
        self.cur = _FakeCursor(prev_summary)
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_repeat_skips_detects_consecutive_club_failures():
    prev = {"clubs": {"skipped_clubs": ["Arsenal", "Chelsea"]}}
    new = {"clubs": {"skipped_clubs": ["Chelsea", "Liverpool"]}}
    assert _repeat_skips(prev, new) == ["Chelsea"]


def test_record_sync_run_adds_alert_on_repeat():
    prev = {"clubs": {"skipped_clubs": ["Bournemouth"]}}
    conn = _FakeConn(prev_summary=(prev,))
    summary = record_sync_run(
        conn,
        "wikipedia",
        status="partial",
        summary={"clubs": {"skipped_clubs": ["Bournemouth"]}},
    )
    assert summary["repeat_skips"] == ["Bournemouth"]
    assert "alert" in summary
    assert conn.committed
