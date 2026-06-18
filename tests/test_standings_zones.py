"""Standings qualification / relegation zones."""

from footballmind_standings_zones import (
    STANDING_ZONE_CONFIG,
    WC_GROUP_ZONES,
    annotate_standings,
    finalize_mls_standings,
    zone_for_rank,
    zone_legend,
)


class _FakeConn:
    def __init__(self, conferences: dict[str, str]):
        self._conferences = conferences

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self._sql = sql

    def fetchall(self):
        return list(self._conferences.items())


def test_pl_ucl_zone():
    z = zone_for_rank("PL", 3, 20)
    assert z and z["id"] == "ucl"


def test_pl_relegation_zone():
    z = zone_for_rank("PL", 20, 20)
    assert z and z["id"] == "rel"


def test_bl1_playoff_not_relegation():
    z16 = zone_for_rank("BL1", 16, 18)
    z17 = zone_for_rank("BL1", 17, 18)
    z18 = zone_for_rank("BL1", 18, 18)
    assert z16 and z16["id"] == "playoff"
    assert z17 and z17["id"] == "rel"
    assert z18 and z18["id"] == "rel"


def test_mid_table_unmarked():
    assert zone_for_rank("PL", 10, 20) is None


def test_annotate_standings():
    table = [{"rank": i, "team": f"T{i}", "Pts": 40 - i} for i in range(1, 21)]
    out = annotate_standings(table, "PL")
    assert out[0]["zone"]["id"] == "ucl"
    assert out[-1]["zone"]["id"] == "rel"


def test_zone_legend_dedupes():
    leg = zone_legend("PL")
    ids = [z["id"] for z in leg]
    assert "ucl" in ids and "rel" in ids
    assert len(ids) == len(set(ids))


def test_mls_playoff_zones_per_conference():
    z1 = zone_for_rank("MLS", 1, 15)
    z7 = zone_for_rank("MLS", 7, 15)
    z8 = zone_for_rank("MLS", 8, 15)
    z10 = zone_for_rank("MLS", 10, 15)
    assert z1 and z1["id"] == "r1"
    assert z7 and z7["id"] == "r1"
    assert z8 and z8["id"] == "wc"
    assert z10 and z10["id"] == "out"


def test_finalize_mls_standings_ranks_within_conference():
    table = [
        {"team": "Team A", "P": 10, "W": 3, "D": 1, "L": 6, "GF": 12, "GA": 15, "GD": -3, "Pts": 10},
        {"team": "Team B", "P": 10, "W": 5, "D": 2, "L": 3, "GF": 18, "GA": 12, "GD": 6, "Pts": 17},
        {"team": "Team C", "P": 10, "W": 4, "D": 3, "L": 3, "GF": 14, "GA": 13, "GD": 1, "Pts": 15},
        {"team": "Team D", "P": 10, "W": 2, "D": 2, "L": 6, "GF": 9, "GA": 16, "GD": -7, "Pts": 8},
    ]
    conn = _FakeConn({"Team A": "East", "Team B": "East", "Team C": "West", "Team D": "West"})
    out = finalize_mls_standings(conn, table)
    east = [r for r in out if r["conference"] == "East"]
    west = [r for r in out if r["conference"] == "West"]
    assert east[0]["team"] == "Team B" and east[0]["rank"] == 1
    assert east[0]["zone"]["id"] == "r1"
    assert west[0]["team"] == "Team C" and west[0]["rank"] == 1
