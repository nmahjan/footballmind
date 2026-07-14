"""Prediction grading and stale-score regrade."""

from unittest.mock import patch

import requests

from footballmind_grading import _bulk_link_predictions_by_teams, grade_predictions


class _FakeCursor:
    def __init__(self):
        self.executed = []
        self._fetch = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))
        self.rowcount = 0
        if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
            self._fetch = [
                # pid, hw, dw, aw, hg, ag, stage, adv_id, home_tid,
                # went_to_pens, home_pens, away_pens, away_tid
                (1, 0.2, 0.6, 0.2, 1, 1, "regular_season", None, 10,
                 False, None, None, 20),
            ]
        elif "WITH nearest AS" in sql:
            self.rowcount = 2
            self._fetch = []
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


def test_bulk_link_predictions_skips_duplicate_session_match_links():
    conn = _FakeConn()
    n = _bulk_link_predictions_by_teams(conn, "WC")
    assert n == 2
    assert conn.committed
    sql, params = conn.cur.executed[0]
    assert params == ["WC"]
    assert "row_number() OVER" in sql
    assert "PARTITION BY nearest.session_id, nearest.match_id" in sql
    assert "NOT EXISTS" in sql
    assert "existing.session_id IS NOT DISTINCT FROM nearest.session_id" in sql
    assert "ranked.link_rank = 1" in sql


def test_grade_predictions_uses_pen_shootout_winner():
    class _PenCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
                self._fetch = [
                    (2, 0.16, 0.0, 0.84, 1, 1, "round_of_32", None, 10,
                     True, 2, 3, 20),
                ]

    conn = _FakeConn()
    conn.cur = _PenCursor()
    n = grade_predictions(conn)
    assert n == 1
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates[0][1] == (1, 1, True, 2)  # predicted away, actual away (pens)


def test_grade_predictions_home_wins_pen_shootout():
    class _PenCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
                self._fetch = [
                    (3, 0.55, 0.0, 0.45, 1, 1, "quarter_final", None, 10,
                     True, 4, 3, 20),
                ]

    conn = _FakeConn()
    conn.cur = _PenCursor()
    n = grade_predictions(conn)
    assert n == 1
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates[0][1] == (1, 1, True, 3)  # predicted home, home won pens


def test_grade_predictions_advancing_team_overrides_pens():
    class _AdvCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
                self._fetch = [
                    (4, 0.2, 0.0, 0.8, 1, 1, "semi_final", 20, 10,
                     True, 3, 3, 20),
                ]

    conn = _FakeConn()
    conn.cur = _AdvCursor()
    n = grade_predictions(conn)
    assert n == 1
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates[0][1] == (1, 1, True, 4)  # away advanced despite tied pens


def test_grade_predictions_force_regrades_all():
    class _ForceCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql:
                self._fetch = [
                    (5, 0.5, 0.3, 0.2, 2, 0, "regular_season", None, 10,
                     False, None, None, 20),
                ]

    conn = _FakeConn()
    conn.cur = _ForceCursor()
    n = grade_predictions(conn, force=True)
    assert n == 1
    assert not any("DISTINCT FROM" in q[0] for q in conn.cur.executed)


def test_grade_knockout_regulation_draw():
    class _DrawCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
                self._fetch = [
                    (6, 0.2, 0.55, 0.25, 1, 1, "quarter_final", None, 10,
                     False, None, None, 20),
                ]

    conn = _FakeConn()
    conn.cur = _DrawCursor()
    n = grade_predictions(conn)
    assert n == 1
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates[0][1][2] is True  # predicted draw, actual draw at 90'


def test_grade_knockout_extra_time_still_uses_regulation_score():
    """Regulation goals in DB; no pens/advancing_team — draw stands."""
    class _EtCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
                self._fetch = [
                    (7, 0.15, 0.25, 0.60, 2, 2, "semi_final", None, 10,
                     False, None, None, 20),
                ]

    conn = _FakeConn()
    conn.cur = _EtCursor()
    n = grade_predictions(conn)
    assert n == 1
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates[0][1][2] is False  # predicted away, actual draw at 90'


def test_grade_two_leg_aggregate_uses_advancing_team():
    class _AggCursor(_FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql.strip(), params))
            if "SELECT p.id" in sql and "DISTINCT FROM" in sql:
                self._fetch = [
                    (8, 0.75, 0.0, 0.25, 0, 0, "semi_final", 10, 10,
                     False, None, None, 20),
                ]

    conn = _FakeConn()
    conn.cur = _AggCursor()
    n = grade_predictions(conn)
    assert n == 1
    updates = [q for q in conn.cur.executed if q[0].startswith("UPDATE predictions")]
    assert updates[0][1][2] is True  # home predicted, home advanced on aggregate
