"""Bracket API and knockout sync helpers."""

from footballmind_services import (
    _bracket_team_label,
    _enrich_fixture_display,
    _propagate_bracket_winners,
    get_bracket,
)
from footballmind_sync import upsert_match


class _FakeCur:
    def __init__(self, rows=None):
        self.executes = []
        self._fetch = rows or []
        self.description = [
            ("stage",), ("home",), ("away",), ("match_date",),
            ("home_goals",), ("away_goals",),
        ]

    def execute(self, sql, params=None):
        self.executes.append((sql, params))

    def fetchall(self):
        return self._fetch


def test_bracket_team_label_strips_placeholder():
    assert _bracket_team_label("TBD (123-h)") == "TBD"
    assert _bracket_team_label("France") == "France"
    assert _bracket_team_label(None) == "TBD"


def test_get_bracket_pads_tbd_slots(monkeypatch):
    fake = _FakeCur([
        ("round_of_32", "South Africa", "Canada", None, None, None),
    ])

    class _Ctx:
        def __enter__(self):
            return fake

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return _Ctx()

    bracket = get_bracket(Conn(), "WC")
    r32 = next(r for r in bracket if r["round"] == "round_of_32")
    assert len(r32["matches"]) == 16
    assert r32["matches"][0]["home"] == "South Africa"
    assert r32["matches"][1]["home"] == "TBD"


def test_knockout_upsert_uses_tbd_placeholders(monkeypatch):
    teams = {}

    def fake_upsert_team(cur, name, team_type, ext_id, country_id=None):
        key = (name, team_type)
        if key not in teams:
            teams[key] = len(teams) + 1
        return teams[key]

    monkeypatch.setattr("footballmind_sync.upsert_team", fake_upsert_team)
    cur = _FakeCur()
    upsert_match(cur, 99, {
        "homeTeam": None,
        "awayTeam": None,
        "stage": "LAST_32",
        "utcDate": "2026-06-28T15:00:00Z",
        "status": "SCHEDULED",
        "id": 555,
    }, "national")
    assert cur.executes
    params = cur.executes[-1][1]
    assert params[3] == 1
    assert params[4] == 2
    assert ("TBD (555-h)", "national") in teams
    assert ("TBD (555-a)", "national") in teams


def test_propagate_bracket_winners():
    rounds = [
        {"round": "round_of_32", "matches": [
            {"home": "South Africa", "away": "Canada", "home_goals": 0, "away_goals": 1},
            {"home": "Netherlands", "away": "Morocco", "home_goals": 3, "away_goals": 4},
        ]},
        {"round": "round_of_16", "matches": [
            {"home": "TBD", "away": "TBD", "home_goals": None, "away_goals": None},
        ]},
    ]
    _propagate_bracket_winners(rounds)
    r16 = rounds[1]["matches"][0]
    assert r16["home"] == "Canada"
    assert r16["away"] == "Morocco"


def test_enrich_fixture_display_uses_bracket_labels():
    labels = {
        ("round_of_16", "2026-07-04T17:00:00+00:00"): ("Canada", "Morocco"),
    }
    f = {
        "home": "Canada",
        "away": "TBD (537376-a)",
        "stage": "round_of_16",
        "match_date": "2026-07-04T17:00:00+00:00",
    }
    _enrich_fixture_display(f, labels)
    assert f["home"] == "Canada"
    assert f["away"] == "Morocco"
