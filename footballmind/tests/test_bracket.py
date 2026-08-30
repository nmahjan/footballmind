"""Bracket API and knockout sync helpers."""

from footballmind_services import (
    _add_bracket_projection,
    _bracket_team_label,
    _enrich_fixture_display,
    _propagate_bracket_winners,
    _propagate_third_place_losers,
    get_bracket,
    get_groups,
)
from footballmind_sync import upsert_match


class _FakeCur:
    def __init__(self, rows=None):
        self.executes = []
        self._fetch = rows or []
        self.description = [
            ("stage",), ("home",), ("away",), ("match_date",),
            ("home_goals",), ("away_goals",), ("matchday",),
            ("advances",), ("went_to_pens",), ("home_pens",), ("away_pens",),
        ]

    def execute(self, sql, params=None):
        self.executes.append((sql, params))

    def fetchone(self):
        if self.executes and "SELECT e.season FROM" in self.executes[-1][0]:
            return ("2026",)
        return self._fetch[0] if self._fetch else None

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


def test_get_bracket_orders_wc_round_of_32_by_feeder_path():
    # R32 rows arrive in kickoff order. The visual bracket needs FIFA
    # match-number feeder order: 73/75, 74/77, 83/84, 81/82, etc.
    kickoff_order = [
        "M73", "M76", "M74", "M75", "M78", "M77", "M79", "M80",
        "M82", "M81", "M84", "M83", "M85", "M88", "M86", "M87",
    ]
    fake = _FakeCur([
        ("round_of_32", m, f"{m} away", None, None, None, None, None)
        for m in kickoff_order
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
    assert [m["home"] for m in r32["matches"]] == [
        "M73", "M75", "M74", "M77", "M83", "M84", "M81", "M82",
        "M76", "M78", "M79", "M80", "M86", "M88", "M85", "M87",
    ]


def test_get_bracket_orders_wc_round_of_16_and_quarters_by_feeder_path():
    r16_kickoff_order = [
        ("round_of_16", "M89 home", "M89 away", None, 1, 0, None, "W89"),
        ("round_of_16", "M90 home", "M90 away", None, 1, 0, None, "W90"),
        ("round_of_16", "M91 home", "M91 away", None, 1, 0, None, "W91"),
        ("round_of_16", "M92 home", "M92 away", None, 1, 0, None, "W92"),
        ("round_of_16", "M93 home", "M93 away", None, 1, 0, None, "W93"),
        ("round_of_16", "M94 home", "M94 away", None, 1, 0, None, "W94"),
        ("round_of_16", "M95 home", "M95 away", None, 1, 0, None, "W95"),
        ("round_of_16", "M96 home", "M96 away", None, 1, 0, None, "W96"),
    ]
    qf_kickoff_order = [
        ("quarter_final", "W89", "W90", None, None, None, None, None),
        ("quarter_final", "W91", "W92", None, None, None, None, None),
        ("quarter_final", "W93", "W94", None, None, None, None, None),
        ("quarter_final", "W95", "W96", None, None, None, None, None),
    ]
    fake = _FakeCur(r16_kickoff_order + qf_kickoff_order)

    class _Ctx:
        def __enter__(self):
            return fake

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return _Ctx()

    bracket = get_bracket(Conn(), "WC")
    r16 = next(r for r in bracket if r["round"] == "round_of_16")
    qf = next(r for r in bracket if r["round"] == "quarter_final")
    assert [m["home"] for m in r16["matches"]] == [
        "M89 home", "M90 home", "M93 home", "M94 home",
        "M91 home", "M92 home", "M95 home", "M96 home",
    ]
    assert [m["home"] for m in qf["matches"]] == ["W89", "W93", "W91", "W95"]


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


def test_propagate_bracket_penalty_winner():
    rounds = [
        {"round": "round_of_16", "matches": [
            {"home": "France", "away": "Portugal", "home_goals": 2, "away_goals": 1},
            {
                "home": "England", "away": "Italy", "home_goals": 1, "away_goals": 1,
                "went_to_pens": True, "home_pens": 4, "away_pens": 3,
            },
        ]},
        {"round": "quarter_final", "matches": [
            {"home": "France", "away": "TBD", "home_goals": None, "away_goals": None},
        ]},
    ]

    _propagate_bracket_winners(rounds)

    qf = rounds[1]["matches"][0]
    assert qf["home"] == "France"
    assert qf["away"] == "England"


def test_propagate_third_place_uses_semifinal_losers():
    rounds = [
        {"round": "semi_final", "matches": [
            {"home": "Spain", "away": "France", "home_goals": 2, "away_goals": 1},
            {"home": "England", "away": "Argentina", "home_goals": 0, "away_goals": 2},
        ]},
        {"round": "final", "matches": [
            {"home": "Spain", "away": "Argentina", "home_goals": None, "away_goals": None},
        ]},
        {"round": "third_place", "matches": [
            {"home": "France", "away": "TBD", "home_goals": None, "away_goals": None},
        ]},
    ]

    _propagate_third_place_losers(rounds)

    third = rounds[2]["matches"][0]
    assert third["home"] == "France"
    assert third["away"] == "England"


def test_add_bracket_projection_carries_model_winners_forward(monkeypatch):
    def fake_predict(conn, home, away, match_date, stage, session_id=None,
                     neutral=None, comp=None, *, persist=True):
        winner = home if home in ("Spain", "Brazil") else away
        return {
            "prediction": f"{winner} advance",
            "confidence": 0.71,
            "home_win_prob": 0.38,
            "draw_prob": 0.33,
            "away_win_prob": 0.29,
            "progression": {"home_advance": 0.71 if winner == home else 0.29},
            "is_knockout": True,
        }

    monkeypatch.setattr("footballmind_mcp_predict._predict_match", fake_predict)
    rounds = [
        {"round": "quarter_final", "matches": [
            {"home": "Spain", "away": "France", "home_goals": None, "away_goals": None},
            {"home": "Brazil", "away": "Argentina", "home_goals": None, "away_goals": None},
        ]},
        {"round": "semi_final", "matches": [
            {"home": "TBD", "away": "TBD", "home_goals": None, "away_goals": None},
        ]},
    ]

    _add_bracket_projection(object(), rounds, "WC")

    assert rounds[0]["matches"][0]["projected_winner"] == "Spain"
    assert rounds[0]["matches"][1]["projected_winner"] == "Brazil"
    semi = rounds[1]["matches"][0]
    assert semi["projected_home"] == "Spain"
    assert semi["projected_away"] == "Brazil"
    assert semi["projected_winner"] == "Spain"


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


def _conn_with_cursor(fake):
    class _Ctx:
        def __enter__(self):
            return fake

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return _Ctx()

    return Conn()


def test_get_bracket_scopes_to_current_season(monkeypatch):
    season = "2026"
    monkeypatch.setattr(
        "footballmind_services._current_season_for_comp",
        lambda conn, comp: season,
    )
    fake = _FakeCur([])
    get_bracket(_conn_with_cursor(fake), "WC")
    sql, params = fake.executes[0]
    assert "e.season = %s" in sql
    assert params == ("WC", season, season)


def test_get_groups_scopes_to_current_season(monkeypatch):
    season = "2026"
    monkeypatch.setattr(
        "footballmind_services._current_season_for_comp",
        lambda conn, comp: season,
    )

    class _GroupsCur(_FakeCur):
        def __init__(self):
            super().__init__()
            self.description = [
                ("g",), ("team",), ("W",), ("D",), ("L",),
                ("GF",), ("GA",), ("Pts",),
            ]

    fake = _GroupsCur()
    get_groups(_conn_with_cursor(fake), "WC")
    sql, params = fake.executes[0]
    assert "e.season = %s" in sql
    assert params == ("WC", season, season, "WC", season, season)
