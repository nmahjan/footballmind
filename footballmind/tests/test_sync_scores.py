"""Match sync guards against stale or premature scores."""

from footballmind_sync import FINISHED_STATUSES, upsert_match


class _FakeCur:
    def __init__(self):
        self.rows = []
        self.params = None

    def execute(self, sql, params=None):
        self.params = params

    def fetchone(self):
        return [1]


def test_upsert_skips_scores_for_scheduled_match(monkeypatch):
    captured = {}

    def fake_upsert_team(cur, name, team_type, ext_id, country_id=None):
        return 10 if "Home" in name else 20

    monkeypatch.setattr("footballmind_sync.upsert_team", fake_upsert_team)
    cur = _FakeCur()
    upsert_match(cur, 99, {
        "homeTeam": {"name": "Home FC", "id": 1},
        "awayTeam": {"name": "Away FC", "id": 2},
        "stage": "REGULAR_SEASON",
        "utcDate": "2026-06-20T15:00:00Z",
        "status": "SCHEDULED",
        "score": {"fullTime": {"home": 2, "away": 1}},
        "id": 999,
    }, "club")
    assert cur.params[5] is None
    assert cur.params[6] is None


def test_finished_statuses_include_awarded():
    assert "FINISHED" in FINISHED_STATUSES
    assert "AWARDED" in FINISHED_STATUSES
