"""
FootballMind — predicted lineups and availability.

Prefers recent confirmed lineups/formations when synced; otherwise builds XI from
squad depth weighted by comp appearances and recent starts (not goals alone).
"""

from __future__ import annotations

from footballmind_services import (
    _affil_kind_for_comp,
    _compute_standout_rating,
    classify_line_role,
    get_team_formations,
)

FORMATION_SLOTS: dict[str, list[str]] = {
    "4-3-3": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "WING", "ST", "WING"],
    "4-4-2": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "ST", "ST"],
    "4-2-3-1": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "WING", "MID", "WING", "ST"],
    "4-3-2-1": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "WING", "WING", "ST"],
    "3-5-2": ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "ST", "ST"],
    "5-3-2": ["GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "ST", "ST"],
    "3-4-3": ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "WING", "ST", "WING"],
}

# When no synced formation, try these first for club sides (modern default shapes).
_CLUB_FORMATION_PREF = (
    "4-3-2-1", "4-2-3-1", "4-3-3", "3-4-3", "4-4-2", "3-5-2", "5-3-2",
)

_FORMATION_ALIASES = {
    "4321": "4-3-2-1",
    "4312": "4-3-1-2",
    "4231": "4-2-3-1",
    "433": "4-3-3",
    "442": "4-4-2",
    "343": "3-4-3",
    "352": "3-5-2",
    "532": "5-3-2",
}


def normalize_formation(raw: str | None) -> str | None:
    """Map API formation strings to our template keys."""
    if not raw:
        return None
    s = raw.strip()
    compact = s.replace("-", "").replace(" ", "")
    if compact in _FORMATION_ALIASES:
        return _FORMATION_ALIASES[compact]
    if s in FORMATION_SLOTS:
        return s
    if len(compact) == 4 and compact.isdigit():
        return "-".join(compact)  # e.g. 4321 -> 4-3-2-1
    return s


def _recent_starter_counts(cur, team_id: int, comp: str, matches: int = 5) -> dict[int, int]:
    """How often each player started in the last N comp matches with lineup data."""
    cur.execute(
        "SELECT p.id, COUNT(*)::int "
        "FROM match_lineup_players mlp "
        "JOIN matches m ON m.id = mlp.match_id "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE mlp.team_id = %s AND mlp.role = 'starter' AND c.code = %s "
        "  AND m.home_goals IS NOT NULL "
        "  AND m.id IN ("
        "    SELECT m2.id FROM matches m2 "
        "    JOIN competition_editions e2 ON e2.id = m2.edition_id "
        "    JOIN competitions c2 ON c2.id = e2.competition_id "
        "    WHERE c2.code = %s AND (m2.home_team_id = %s OR m2.away_team_id = %s) "
        "      AND m2.home_goals IS NOT NULL "
        "    ORDER BY m2.match_date DESC NULLS LAST LIMIT %s"
        "  ) "
        "GROUP BY p.id",
        (team_id, comp, comp, team_id, team_id, matches))
    return {row[0]: row[1] for row in cur.fetchall()}


def _last_match_starters(cur, team_id: int, comp: str) -> tuple[str | None, list[dict]]:
    """Most recent confirmed XI + formation for this team in comp."""
    cur.execute(
        "SELECT m.id, mtl.formation "
        "FROM matches m "
        "JOIN match_team_lineups mtl ON mtl.match_id = m.id AND mtl.team_id = %s "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s AND m.home_goals IS NOT NULL "
        "  AND EXISTS ("
        "    SELECT 1 FROM match_lineup_players mlp "
        "    WHERE mlp.match_id = m.id AND mlp.team_id = %s AND mlp.role = 'starter'"
        "  ) "
        "ORDER BY m.match_date DESC NULLS LAST LIMIT 1",
        (team_id, comp, team_id))
    row = cur.fetchone()
    if not row:
        return None, []
    match_id, formation = row
    cur.execute(
        "SELECT p.id, p.name, COALESCE(mlp.position, p.position, '?'), mlp.shirt_number "
        "FROM match_lineup_players mlp "
        "JOIN players p ON p.id = mlp.player_id "
        "WHERE mlp.match_id = %s AND mlp.team_id = %s AND mlp.role = 'starter' "
        "ORDER BY mlp.shirt_number NULLS LAST, p.name",
        (match_id, team_id))
    starters = [
        {"player_id": pid, "name": name, "position": pos or "?", "shirt_number": num}
        for pid, name, pos, num in cur.fetchall()
    ]
    return normalize_formation(formation), starters


def _ranked_squad(cur, team_id: int, kind: str, comp: str | None,
                  recent_starts: dict[int, int]) -> list[dict]:
    comp_join = ""
    comp_params: list = []
    if comp:
        comp_join = (
            "LEFT JOIN LATERAL ("
            "  SELECT pes.goals, pes.assists, pes.appearances "
            "  FROM player_edition_stats pes "
            "  JOIN competition_editions e ON e.id = pes.edition_id "
            "  JOIN competitions c ON c.id = e.competition_id "
            "  WHERE pes.player_id = p.id AND c.code = %s "
            "  ORDER BY e.start_date DESC NULLS LAST LIMIT 1"
            ") comp_stats ON true "
        )
        comp_params = [comp]

    cur.execute(
        "SELECT p.id, p.name, p.position, tr.rating, "
        "       COALESCE(comp_stats.goals, cs.goals, 0), "
        "       COALESCE(comp_stats.assists, cs.assists, 0), "
        "       COALESCE(comp_stats.appearances, cs.appearances, 0), cs.club_team "
        "FROM player_affiliations pa "
        "JOIN players p ON p.id = pa.player_id "
        "LEFT JOIN team_ratings tr ON tr.team_id = pa.team_id "
        f"LEFT JOIN LATERAL ("
        "  SELECT pes.goals, pes.assists, pes.appearances, t2.name AS club_team "
        "  FROM player_edition_stats pes "
        "  JOIN teams t2 ON t2.id = pes.team_id "
        "  WHERE pes.player_id = p.id "
        "  ORDER BY pes.appearances DESC, (pes.goals + pes.assists) DESC "
        "  LIMIT 1"
        ") cs ON true "
        f"{comp_join}"
        "WHERE pa.team_id = %s AND pa.end_date IS NULL AND pa.kind = %s "
        "ORDER BY p.name",
        (*comp_params, team_id, kind))
    squad = []
    for pid, name, pos, rating, goals, ast, apps, club in cur.fetchall():
        position = pos or "?"
        line_role = classify_line_role(pos, goals, ast)
        base = _compute_standout_rating(rating, goals, ast, apps, position)
        starts = recent_starts.get(pid, 0)
        # Recent starters and regulars in this comp rank above raw goal scorers.
        score = base + starts * 12 + min(apps, 30) * 0.35
        squad.append({
            "player_id": pid,
            "name": name,
            "position": position,
            "line_role": line_role,
            "goals": goals,
            "assists": ast,
            "score": round(score, 1),
            "club_team": club,
            "recent_starts": starts,
            "appearances": apps,
        })
    squad.sort(key=lambda p: (-p["score"], p["name"]))
    return squad


def _slot_matches_player(slot: str, player: dict) -> bool:
    lr = player.get("line_role") or player.get("position") or "?"
    if slot == lr:
        return True
    if slot == "WING" and lr == "WING":
        return True
    if slot == "ST" and lr == "ST":
        return True
    if slot == "MID" and lr in ("MID", "?"):
        return True
    if slot == "FWD" and lr in ("ST", "WING"):
        return True
    return False


def _candidates_for_slot(slot: str, squad: list[dict], taken: set[int]) -> list[dict]:
    """Best-fit players for a lineup slot (striker vs winger vs mid)."""
    avail = [p for p in squad if p["player_id"] not in taken]
    if slot == "ST":
        primary = [p for p in avail if p.get("line_role") == "ST"]
        primary.sort(key=lambda p: (-(p.get("goals") or 0), -p["score"], p["name"]))
        if primary:
            return primary
        fwd = [p for p in avail if p.get("position") == "FWD"]
        fwd.sort(key=lambda p: (-(p.get("goals") or 0), -p["score"], p["name"]))
        return fwd
    if slot == "WING":
        primary = [p for p in avail if p.get("line_role") == "WING"]
        primary.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        if primary:
            return primary
        wide = [p for p in avail if p.get("position") == "FWD" and p.get("line_role") != "ST"]
        wide.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        mids = [p for p in avail if p.get("position") == "MID"]
        mids.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        return wide + mids
    if slot == "MID":
        primary = [p for p in avail if p.get("line_role") == "MID"]
        primary.sort(key=lambda p: (-p["score"], p["name"]))
        if primary:
            return primary
        return sorted(avail, key=lambda p: (-p["score"], p["name"]))
    if slot == "DEF":
        defs = [p for p in avail if p.get("line_role") == "DEF" or p.get("position") == "DEF"]
        defs.sort(key=lambda p: (-p["score"], p["name"]))
        return defs
    if slot == "GK":
        gks = [p for p in avail if p.get("line_role") == "GK" or p.get("position") == "GK"]
        gks.sort(key=lambda p: (-p["score"], p["name"]))
        return gks
    return sorted(avail, key=lambda p: (-p["score"], p["name"]))


def _can_fill(slots: list[str], squad: list[dict]) -> bool:
    taken: set[int] = set()
    for slot in slots:
        if not _candidates_for_slot(slot, squad, taken):
            return False
        taken.add(_candidates_for_slot(slot, squad, taken)[0]["player_id"])
    return True


def _formation_score(slots: list[str], squad: list[dict]) -> float:
    if not _can_fill(slots, squad):
        return -1.0
    taken: set[int] = set()
    total = 0.0
    for slot in slots:
        picked = _candidates_for_slot(slot, squad, taken)[0]
        total += picked["score"]
        taken.add(picked["player_id"])
    return total


def _pick_formation(squad: list[dict], preferred: str | None, kind: str) -> str:
    preferred = normalize_formation(preferred)
    if preferred and preferred in FORMATION_SLOTS and _can_fill(FORMATION_SLOTS[preferred], squad):
        return preferred
    order = list(_CLUB_FORMATION_PREF) if kind == "club" else list(FORMATION_SLOTS)
    best_f, best_s = "4-3-3", -1.0
    for fname in order:
        if fname not in FORMATION_SLOTS:
            continue
        score = _formation_score(FORMATION_SLOTS[fname], squad)
        if score > best_s:
            best_s, best_f = score, fname
    return best_f


def _pick_xi(slots: list[str], squad: list[dict], unavailable: set[int],
             last_starters: list[dict] | None = None) -> list[dict]:
    """Fill XI; prefer last-match starters when still available."""
    last_starters = last_starters or []
    avail = [p for p in squad if p["player_id"] not in unavailable]
    # Enrich last starters with line_role from squad roster when possible.
    roster = {p["player_id"]: p for p in avail}
    for s in last_starters:
        if s["player_id"] in roster:
            s["line_role"] = roster[s["player_id"]].get("line_role")
            s["goals"] = roster[s["player_id"]].get("goals")
            s["assists"] = roster[s["player_id"]].get("assists")

    xi: list[dict | None] = [None] * len(slots)
    taken: set[int] = set()

    # Pass 1: keep recent starters in matching slots.
    for i, slot in enumerate(slots):
        for s in last_starters:
            pid = s["player_id"]
            if pid in unavailable or pid in taken:
                continue
            if not _slot_matches_player(slot, s):
                continue
            pool_match = roster.get(pid)
            if pool_match:
                xi[i] = {**pool_match, "slot": i + 1, "line_pos": slot}
                taken.add(pid)
                break

    # Pass 2: fill remaining slots by role fit.
    for i, slot in enumerate(slots):
        if xi[i] is not None:
            continue
        cands = _candidates_for_slot(slot, avail, taken)
        if cands:
            picked = cands[0]
            xi[i] = {**picked, "slot": i + 1, "line_pos": slot}
            taken.add(picked["player_id"])

    return [p for p in xi if p is not None]


def _team_last_and_next_match(cur, team_id: int, comp: str) -> tuple[int | None, int | None]:
    base = (
        "FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s AND (m.home_team_id = %s OR m.away_team_id = %s) "
    )
    cur.execute(
        f"SELECT m.id {base} AND m.home_goals IS NOT NULL "
        "ORDER BY m.match_date DESC NULLS LAST LIMIT 1",
        (comp, team_id, team_id))
    row = cur.fetchone()
    last_id = row[0] if row else None
    cur.execute(
        f"SELECT m.id {base} AND m.home_goals IS NULL "
        "ORDER BY m.match_date ASC NULLS LAST LIMIT 1",
        (comp, team_id, team_id))
    row = cur.fetchone()
    next_id = row[0] if row else None
    return last_id, next_id


def _card_suspensions(cur, team_id: int, comp: str) -> list[dict]:
    last_id, next_id = _team_last_and_next_match(cur, team_id, comp)
    if not last_id or not next_id:
        return []
    cur.execute(
        "SELECT p.id, p.name, me.minute "
        "FROM match_events me "
        "JOIN players p ON p.id = me.player_id "
        "WHERE me.match_id = %s AND me.team_id = %s AND me.event_type = 'RED_CARD'",
        (last_id, team_id))
    return [
        {"player_id": pid, "name": name, "status": "suspended",
         "reason": f"Red card last match ({minute or '?'}')" }
        for pid, name, minute in cur.fetchall()
    ]


def _manual_unavailable(cur, team_id: int, comp: str) -> list[dict]:
    cur.execute(
        "SELECT p.id, p.name, pa.status, pa.reason "
        "FROM player_availability pa "
        "JOIN players p ON p.id = pa.player_id "
        "WHERE pa.team_id = %s AND pa.comp_code = %s",
        (team_id, comp))
    return [
        {"player_id": pid, "name": name, "status": status, "reason": reason or status}
        for pid, name, status, reason in cur.fetchall()
    ]


def _next_opponent(cur, team_id: int, comp: str) -> str | None:
    cur.execute(
        "SELECT th.name, ta.name, m.home_team_id "
        "FROM matches m "
        "JOIN teams th ON th.id = m.home_team_id "
        "JOIN teams ta ON ta.id = m.away_team_id "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s AND m.home_goals IS NULL "
        "  AND (m.home_team_id = %s OR m.away_team_id = %s) "
        "ORDER BY m.match_date ASC NULLS LAST LIMIT 1",
        (comp, team_id, team_id))
    row = cur.fetchone()
    if not row:
        return None
    home, away, home_id = row
    return away if home_id == team_id else home


_FORMATION_ROW_SLOTS: dict[str, list[tuple[str, list[int]]]] = {
    "4-3-2-1": [
        ("ST", [11]), ("WING", [9, 10]), ("MID", [6, 7, 8]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "4-3-3": [
        ("ST", [10]), ("WING", [9, 11]), ("MID", [6, 7, 8]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "4-2-3-1": [
        ("ST", [11]), ("WING", [8, 10]), ("MID", [9]), ("MID", [6, 7]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "4-4-2": [
        ("ST", [10, 11]), ("MID", [6, 7, 8, 9]), ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "3-5-2": [
        ("ST", [10, 11]), ("MID", [5, 6, 7, 8, 9]), ("DEF", [2, 3, 4]), ("GK", [1]),
    ],
    "5-3-2": [
        ("ST", [10, 11]), ("MID", [7, 8, 9]), ("DEF", [2, 3, 4, 5, 6]), ("GK", [1]),
    ],
    "3-4-3": [
        ("ST", [10]), ("WING", [9, 11]), ("MID", [5, 6, 7, 8]),
        ("DEF", [2, 3, 4]), ("GK", [1]),
    ],
}


def _formation_rows(xi: list[dict], formation: str) -> list[dict]:
    by_slot = {p["slot"]: p for p in xi}
    specs = _FORMATION_ROW_SLOTS.get(formation, _FORMATION_ROW_SLOTS["4-3-3"])
    rows = []
    for line, slots in specs:
        players = [
            {"name": by_slot[s]["name"], "score": by_slot[s]["score"]}
            for s in slots if s in by_slot
        ]
        if players:
            rows.append({"line": line, "players": players})
    return list(reversed(rows))


def get_predicted_lineup(conn, team_name: str, comp: str | None = "WC") -> dict:
    from footballmind_mcp_predict import _resolve_team

    comp = comp or "WC"
    kind = _affil_kind_for_comp(conn, comp)

    with conn.cursor() as cur:
        team_id, _ = _resolve_team(cur, team_name)
        cur.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
        resolved = cur.fetchone()[0]

        recent_starts = _recent_starter_counts(cur, team_id, comp)
        last_formation, last_starters = _last_match_starters(cur, team_id, comp)
        squad = _ranked_squad(cur, team_id, kind, comp, recent_starts)
        if not squad:
            return {"team": resolved, "comp": comp, "error": "No squad on file for this team."}

        unavailable_list = _card_suspensions(cur, team_id, comp) + _manual_unavailable(cur, team_id, comp)
        unavailable_ids = {u["player_id"] for u in unavailable_list}
        avail_squad = [p for p in squad if p["player_id"] not in unavailable_ids]
        opponent = _next_opponent(cur, team_id, comp)

    recent = get_team_formations(conn, resolved, comp, limit=3)
    preferred = last_formation or (recent[0]["formation"] if recent else None)
    preferred = normalize_formation(preferred)
    formation = _pick_formation(avail_squad, preferred, kind)
    xi = _pick_xi(FORMATION_SLOTS[formation], avail_squad, unavailable_ids, last_starters)

    used_recent = len(last_starters) >= 9 and formation == preferred
    xi_ids = {p["player_id"] for p in xi}
    bench = [p for p in squad if p["player_id"] not in xi_ids and p["player_id"] not in unavailable_ids][:7]

    return {
        "team": resolved,
        "comp": comp,
        "formation": formation,
        "source": "recent_lineup" if used_recent else (
            "recent_formation" if preferred and preferred == formation else "predicted"),
        "recent_formations": [
            normalize_formation(r["formation"]) or r["formation"]
            for r in recent if r.get("formation")
        ],
        "next_opponent": opponent,
        "starters": [
            {"name": p["name"], "position": p["line_pos"], "score": p["score"],
             "club_team": p.get("club_team")}
            for p in xi
        ],
        "rows": _formation_rows(xi, formation),
        "bench": [{"name": p["name"], "position": p["position"], "score": p["score"]} for p in bench],
        "unavailable": unavailable_list,
    }
