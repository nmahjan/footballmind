"""Tactical line_role resolution (ST, WING, LB, …)."""

from footballmind_roles import (
    map_sofifa_position,
    resolve_player_line_role,
    apply_player_line_roles,
    PLAYER_LINE_ROLE_OVERRIDES,
)


def test_map_sofifa_position():
    assert map_sofifa_position("RW") == "WING"
    assert map_sofifa_position("LW") == "WING"
    assert map_sofifa_position("ST") == "ST"
    assert map_sofifa_position("LB") == "LB"
    assert map_sofifa_position("RCM") == "CM"
    assert map_sofifa_position(None) is None


def test_resolve_prefers_stored_line_role():
    role = resolve_player_line_role(
        name="Anyone",
        db_line_role="LB",
        db_position="Offence",
        goals=20,
        assists=0,
    )
    assert role == "LB"


def test_resolve_manual_overrides():
    assert resolve_player_line_role(
        name="Viktor Gyökeres",
        db_line_role=None,
        db_position="Offence",
        goals=25,
        assists=2,
    ) == "ST"
    assert resolve_player_line_role(
        name="Lamine Yamal",
        db_line_role=None,
        db_position="Offence",
        goals=8,
        assists=12,
    ) == "WING"
    assert resolve_player_line_role(
        name="Riccardo Calafiori",
        db_line_role=None,
        db_position="Defence",
    ) == "LB"


def test_parse_profile_position():
    from footballmind_sofifa import parse_player_profile_html

    html = """
    <html><body>
    <div class="profile"><h1>Lamine Yamal</h1></div>
    <p>Position RW Right Winger</p>
    <p>25y.o. 180cm 72kg</p>
    </body></html>
    """
    attrs = parse_player_profile_html(html, sofifa_id=1)
    assert attrs["primary_position"] == "RW"
    assert attrs["line_role"] == "WING"


def test_apply_overrides_sqlite_style(monkeypatch):
    """apply_player_line_roles runs UPDATE per override (smoke test with mock cursor)."""
    executed = []

    class FakeCursor:
        rowcount = 1

        def execute(self, sql, params):
            executed.append((sql.strip(), params))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    n = apply_player_line_roles(FakeConn())
    assert n == len(PLAYER_LINE_ROLE_OVERRIDES)
    assert any("line_role" in q[0] for q in executed)
