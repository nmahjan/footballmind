"""Team squad response shaping (no live DB)."""

import sys
import types
from datetime import date
from unittest.mock import MagicMock, patch

from footballmind_services import get_team_squad


def _mock_conn():
    cur = MagicMock()
    cur.fetchone.side_effect = [
        ("Argentina",),
        (1911,),
    ]
    cur.fetchall.return_value = [
        (1, "Emiliano Martinez", "Goalkeeper", None, 23, date(1992, 9, 2), "Argentina"),
        (2, "Nicolas Otamendi", "Defence", None, 19, date(1988, 2, 12), "Argentina"),
        (3, "Rodrigo De Paul", "Midfield", None, 7, date(1994, 5, 24), "Argentina"),
        (4, "Lionel Messi", "Offence", None, 10, date(1987, 6, 24), "Argentina"),
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def test_team_squad_normalizes_source_positions_into_visible_groups():
    conn = _mock_conn()
    fake_sofifa = types.SimpleNamespace(get_eafc_attributes_bulk=lambda _conn, _pids: {})
    with patch("footballmind_mcp_predict._resolve_team", return_value=(10, "national")), \
         patch.dict(sys.modules, {"footballmind_sofifa": fake_sofifa}), \
         patch("footballmind_roles.resolve_player_line_role", side_effect=lambda **kw: kw["db_position"]):
        squad = get_team_squad(conn, "Argentina", "WC")

    assert squad["squad_size"] == 4
    assert [p["position"] for p in squad["squad"]] == ["GK", "DEF", "MID", "FWD"]
    assert {k: len(v) for k, v in squad["by_position"].items()} == {
        "GK": 1,
        "DEF": 1,
        "MID": 1,
        "FWD": 1,
    }
