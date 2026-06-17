"""Prediction grading and stale-score regrade."""

from footballmind_grading import grade_predictions


class _FakeCursor:
    def __init__(self):
        self.executed = []
        self._fetch = []

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))
        if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
            self._fetch = [
                (1, 0.2, 0.6, 0.2, 1, 1),  # predicted draw, actual draw
            ]
        else:
            self._fetch = []

    def fetchall(self):
        return self._fetch

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeConn:
    def __init__(self):
        self.cur = _FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_grade_predictions_regrades_when_scores_differ():
    conn = _FakeConn()
    n = grade_predictions(conn)
    assert n == 1
    assert conn.committed
    assert any("DISTINCT FROM" in q[0] for q in conn.cur.executed)
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates
    assert updates[0][1] == (1, 1, True, 1)
