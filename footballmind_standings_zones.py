"""Qualification / relegation zones for league tables."""

from __future__ import annotations

# Each zone: id, label, short (legend), color (hex), from/to rank or from_end count.
# Ranks are 1-based. from_end applies to the last N places in the table.

STANDING_ZONE_CONFIG: dict[str, list[dict]] = {
    "PL": [
        {"id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8", "from": 1, "to": 4},
        {"id": "uel", "label": "Europa League", "short": "UEL", "color": "#fb923c", "from": 5, "to": 5},
        {"id": "uecl", "label": "Conference League", "short": "UECL", "color": "#a78bfa", "from": 6, "to": 6},
        {"id": "rel", "label": "Relegation", "short": "REL", "color": "#f87171", "from_end": 3, "to_end": 1},
    ],
    "PD": [
        {"id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8", "from": 1, "to": 4},
        {"id": "uel", "label": "Europa League", "short": "UEL", "color": "#fb923c", "from": 5, "to": 5},
        {"id": "uecl", "label": "Conference League", "short": "UECL", "color": "#a78bfa", "from": 6, "to": 6},
        {"id": "rel", "label": "Relegation", "short": "REL", "color": "#f87171", "from_end": 3, "to_end": 1},
    ],
    "BL1": [
        {"id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8", "from": 1, "to": 4},
        {"id": "uel", "label": "Europa League", "short": "UEL", "color": "#fb923c", "from": 5, "to": 5},
        {"id": "uecl", "label": "Conference League", "short": "UECL", "color": "#a78bfa", "from": 6, "to": 6},
        {"id": "playoff", "label": "Relegation play-off", "short": "PO", "color": "#fbbf24", "from_end": 3, "to_end": 3},
        {"id": "rel", "label": "Relegation", "short": "REL", "color": "#f87171", "from_end": 2, "to_end": 1},
    ],
    "SA": [
        {"id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8", "from": 1, "to": 4},
        {"id": "uel", "label": "Europa League", "short": "UEL", "color": "#fb923c", "from": 5, "to": 5},
        {"id": "uecl", "label": "Conference League", "short": "UECL", "color": "#a78bfa", "from": 6, "to": 6},
        {"id": "rel", "label": "Relegation", "short": "REL", "color": "#f87171", "from_end": 3, "to_end": 1},
    ],
    "FL1": [
        {"id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8", "from": 1, "to": 3},
        {"id": "uel", "label": "Europa League", "short": "UEL", "color": "#fb923c", "from": 4, "to": 4},
        {"id": "uecl", "label": "Conference League", "short": "UECL", "color": "#a78bfa", "from": 5, "to": 5},
        {"id": "rel", "label": "Relegation", "short": "REL", "color": "#f87171", "from_end": 3, "to_end": 1},
    ],
    "DED": [
        {"id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8", "from": 1, "to": 2},
        {"id": "uel", "label": "Europa League", "short": "UEL", "color": "#fb923c", "from": 3, "to": 3},
        {"id": "playoff", "label": "Relegation play-off", "short": "PO", "color": "#fbbf24", "from_end": 3, "to_end": 3},
        {"id": "rel", "label": "Relegation", "short": "REL", "color": "#f87171", "from_end": 2, "to_end": 1},
    ],
    "CL": [
        {"id": "r16", "label": "Round of 16", "short": "R16", "color": "#34d399", "from": 1, "to": 8},
        {"id": "kopo", "label": "Knockout play-offs", "short": "PO", "color": "#fbbf24", "from": 9, "to": 24},
        {"id": "out", "label": "Eliminated", "short": "OUT", "color": "#64748b", "from": 25, "to": 99},
    ],
}

WC_GROUP_ZONES = [
    {"id": "adv", "label": "Knockout stage", "short": "KO", "color": "#34d399", "from": 1, "to": 2},
]


def _zone_matches_rank(zone: dict, rank: int, team_count: int) -> bool:
    if "from_end" in zone:
        n_from = int(zone["from_end"])
        n_to = int(zone.get("to_end", 1))
        rank_hi = team_count - n_from + 1  # e.g. 3rd from bottom
        rank_lo = team_count - n_to + 1    # e.g. last place
        return rank_hi <= rank <= rank_lo
    lo, hi = int(zone["from"]), int(zone["to"])
    return lo <= rank <= hi


def zone_for_rank(comp_code: str, rank: int, team_count: int) -> dict | None:
    """Return zone metadata for a table row, or None if unmarked."""
    zones = STANDING_ZONE_CONFIG.get(comp_code)
    if not zones or rank < 1 or team_count < 1:
        return None
    for zone in zones:
        if _zone_matches_rank(zone, rank, team_count):
            return {
                "id": zone["id"],
                "label": zone["label"],
                "short": zone["short"],
                "color": zone["color"],
            }
    return None


def annotate_standings(table: list[dict], comp_code: str) -> list[dict]:
    """Attach zone + legend fields to each standings row."""
    n = len(table)
    out = []
    for row in table:
        copy = dict(row)
        z = zone_for_rank(comp_code, int(copy.get("rank", 0)), n)
        copy["zone"] = z
        out.append(copy)
    return out


def zone_legend(comp_code: str) -> list[dict]:
    """Legend entries for a competition (deduped, display order)."""
    zones = STANDING_ZONE_CONFIG.get(comp_code, [])
    seen: set[str] = set()
    legend = []
    for z in zones:
        if z["id"] in seen:
            continue
        seen.add(z["id"])
        legend.append({
            "id": z["id"],
            "label": z["label"],
            "short": z["short"],
            "color": z["color"],
        })
    return legend
