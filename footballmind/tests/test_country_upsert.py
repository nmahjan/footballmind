"""Country upsert handles shared FIFA codes."""

from footballmind_sync import upsert_country


class _FakeCur:
    def __init__(self, by_code=None):
        self.by_code = by_code or {}
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))
        if "SELECT id FROM countries WHERE fifa_code" in sql:
            self._fetch = [(self.by_code.get(params[0]),)] if params[0] in self.by_code else []
        elif sql.strip().startswith("INSERT INTO countries"):
            self._fetch = [(999,)]
        else:
            self._fetch = []

    def fetchone(self):
        rows = getattr(self, "_fetch", [])
        return rows[0] if rows else None


def test_upsert_country_reuses_existing_fifa_code():
    cur = _FakeCur(by_code={"CUW": 42})
    cid = upsert_country(cur, "CUW", "CUW")
    assert cid == 42
    inserts = [q for q in cur.executed if q[0].startswith("INSERT")]
    assert inserts == []


def test_upsert_country_inserts_when_code_unknown():
    cur = _FakeCur()
    cid = upsert_country(cur, "Curaçao", "CUW")
    assert cid == 999
    inserts = [q for q in cur.executed if q[0].startswith("INSERT")]
    assert inserts[0][1] == ("Curaçao", "CUW")
