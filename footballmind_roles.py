"""Player tactical roles for lineup placement (ST, WING, LB, …)."""

from __future__ import annotations

import re

# Slots used by footballmind_lineup.FORMATION_SLOTS
LINE_ROLES = frozenset({
    "GK", "LB", "CB", "RB", "CDM", "CM", "CAM", "WING", "ST",
})

# Manual overrides when FDO position is coarse ("Offence") or SoFIFA not synced yet.
# Keys are player names as stored in DB (ILIKE match).
PLAYER_LINE_ROLE_OVERRIDES: dict[str, str] = {
    # Arsenal
    "Viktor Gyökeres": "ST",
    "Kai Havertz": "ST",
    "Gabriel Jesus": "ST",
    "Bukayo Saka": "WING",
    "Leandro Trossard": "WING",
    "Martinelli": "WING",
    "Gabriel Martinelli": "WING",
    "Noni Madueke": "WING",
    "Martin Ødegaard": "CAM",
    "Eberechi Eze": "CAM",
    "Declan Rice": "CDM",
    "Martín Zubimendi": "CDM",
    "Mikel Merino": "CM",
    "Christian Nørgaard": "CDM",
    "Riccardo Calafiori": "LB",
    "Ben White": "RB",
    "Jurrien Timber": "RB",
    "William Saliba": "CB",
    "Gabriel Magalhães": "CB",
    "Myles Lewis-Skelly": "LB",
    "David Raya": "GK",
    # Spain / WC
    "Lamine Yamal": "WING",
    "Nico Williams": "WING",
    "Dani Olmo": "CAM",
    "Pedri": "CM",
    "Rodri": "CDM",
    "Álvaro Morata": "ST",
    "Ferran Torres": "WING",
    # Argentina
    "Lionel Messi": "CAM",
    "Ángel Di María": "WING",
    "Lautaro Martínez": "ST",
    "Julián Álvarez": "ST",
    "Enzo Fernández": "CM",
    "Alexis Mac Allister": "CM",
    # England
    "Harry Kane": "ST",
    "Bukayo Saka": "WING",
    "Phil Foden": "WING",
    "Declan Rice": "CDM",
    "Jude Bellingham": "CAM",
    # France
    "Kylian Mbappé": "WING",
    "Olivier Giroud": "ST",
    "Antoine Griezmann": "CAM",
    "N'Golo Kanté": "CDM",
}

# SoFIFA short codes -> our lineup slots
SOFIFA_POSITION_MAP: dict[str, str] = {
    "GK": "GK",
    "LB": "LB", "LWB": "LB",
    "RB": "RB", "RWB": "RB",
    "CB": "CB", "SW": "CB",
    "CDM": "CDM", "DM": "CDM",
    "CM": "CM", "LCM": "CM", "RCM": "CM", "LDM": "CDM", "RDM": "CDM",
    "CAM": "CAM", "AM": "CAM", "LAM": "CAM", "RAM": "CAM",
    "LM": "WING", "RM": "WING", "LW": "WING", "RW": "WING",
    "LF": "WING", "RF": "WING", "LS": "WING", "RS": "WING",
    "ST": "ST", "CF": "ST",
}


def map_sofifa_position(raw: str | None) -> str | None:
    if not raw:
        return None
    code = re.sub(r"[^A-Za-z]", "", raw).upper()
    if not code:
        return None
    if code in SOFIFA_POSITION_MAP:
        return SOFIFA_POSITION_MAP[code]
    for prefix, role in (
        ("LWB", "LB"), ("RWB", "RB"), ("RCM", "CM"), ("LCM", "CM"),
        ("CDM", "CDM"), ("CAM", "CAM"), ("CAM", "CAM"),
    ):
        if code.startswith(prefix) or code == prefix:
            return role
    if "WING" in code or code.endswith("W"):
        return "WING"
    return None


def resolve_player_line_role(
    *,
    name: str,
    db_line_role: str | None,
    db_position: str | None,
    goals: int = 0,
    assists: int = 0,
) -> str:
    """Pick the best tactical role for lineup placement."""
    from footballmind_services import classify_line_role

    if db_line_role and db_line_role.upper() in LINE_ROLES:
        return db_line_role.upper()
    for key, role in PLAYER_LINE_ROLE_OVERRIDES.items():
        if key.lower() == name.lower():
            return role
    if db_position and db_position.upper() in LINE_ROLES:
        return db_position.upper()
    return classify_line_role(db_position, goals, assists)


def apply_player_line_roles(conn) -> int:
    """Write manual overrides into players.line_role."""
    updated = 0
    with conn.cursor() as cur:
        for name, role in PLAYER_LINE_ROLE_OVERRIDES.items():
            cur.execute(
                "UPDATE players SET line_role = %s "
                "WHERE name ILIKE %s AND (line_role IS NULL OR line_role <> %s)",
                (role, name, role),
            )
            updated += cur.rowcount
    conn.commit()
    return updated
