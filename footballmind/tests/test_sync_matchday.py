"""Matchday sync window and WC knockout settlement guards."""

from unittest.mock import MagicMock, patch

from footballmind_jobs import _wc_has_unresolved_knockouts, cmd_sync_matchday


class _FakeCur:
    def __init__(self, fetchone=None):
        self.fetchone_result = fetchone

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, fetchone=None):
        self._fetchone = fetchone

    def cursor(self):
        return _FakeCur(self._fetchone)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_wc_has_unresolved_knockouts_true():
    conn = _FakeConn(fetchone=(1,))
    assert _wc_has_unresolved_knockouts(conn) is True


def test_wc_has_unresolved_knockouts_false():
    conn = _FakeConn(fetchone=None)
    assert _wc_has_unresolved_knockouts(conn) is False


def test_sync_matchday_runs_when_unresolved_knockouts_outside_window(capsys):
    """Between rounds the activity window can be empty while winners are unset."""
    with patch("footballmind_jobs._connect", return_value=_FakeConn()), \
         patch("footballmind_jobs._comps_with_activity", return_value=set()), \
         patch("footballmind_jobs._wc_has_unresolved_knockouts", return_value=True), \
         patch("footballmind_jobs.TokenBucket"), \
         patch("footballmind_jobs.FootballDataClient"), \
         patch("footballmind_jobs.sync_competition") as sync_comp, \
         patch("footballmind_jobs.sync_match_details", return_value=0), \
         patch("footballmind_jobs.refresh_knockout_scores", return_value=0), \
         patch("footballmind_jobs.link_orphan_predictions", return_value=0), \
         patch("footballmind_jobs.grade_predictions", return_value=0), \
         patch.dict("os.environ", {"FOOTBALL_DATA_API_KEY": "test-key"}):
        cmd_sync_matchday()

    assert sync_comp.called
    assert sync_comp.call_args[0][2] == "WC"
    out = capsys.readouterr().out
    assert "active comps: WC" in out
    assert "no fixtures in window" not in out
