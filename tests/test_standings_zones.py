"""Standings qualification / relegation zones."""

from footballmind_standings_zones import (
    STANDING_ZONE_CONFIG,
    WC_GROUP_ZONES,
    annotate_standings,
    zone_for_rank,
    zone_legend,
)


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
