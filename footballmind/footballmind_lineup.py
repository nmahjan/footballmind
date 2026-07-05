"""
FootballMind — predicted lineups and availability.

Builds a most-likely XI from squad depth + form scores, prefers recent
confirmed formations when synced, and excludes players suspended (red cards)
or flagged injured/doubtful in player_availability.
"""

from __future__ import annotations

from footballmind_services import (
    _affil_kind_for_comp,
    _compute_standout_rating,
    get_team_formations,
)

FORMATION_SLOTS: dict[str, list[str]] = {
    "4-3-3": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "FWD", "FWD", "FWD"],
    "4-4-2": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD"],
    "4-2-3-1": ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD"],
    "3-5-2": ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD"],
    "5-3-2": ["GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "FWD", "FWD"],
    "3-4-3": ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"],
}


def _ranked_squad(cur, team_id: int, kind: str) -> list[dict]:
    cur.execute(
        "SELECT p.id, p.name, p.position, tr.rating, "
        "       COALESCE(cs.goals, 0), COALESCE(cs.assists, 0), "
        "       COALESCE(cs.appearances, 0), cs.club_team "
        "FROM player_affiliations pa "
        "JOIN players p ON p.id = pa.player_id "
        "LEFT JOIN team_ratings tr ON tr.team_id = pa.team_id "
        "LEFT JOIN LATERAL ("
        "  SELECT pes.goals, pes.assists, pes.appearances, t2.name AS club_team "
        "  FROM player_edition_stats pes "
        "  JOIN teams t2 ON t2.id = pes.team_id "
        "  WHERE pes.player_id = p.id "
        "  ORDER BY (pes.goals + pes.assists * 0.6) DESC, pes.appearances DESC "
        "  LIMIT 1"
        ") cs ON true "
        "WHERE pa.team_id = %s AND pa.end_date IS NULL AND pa.kind = %s "
        "ORDER BY p.name",
        (team_id, kind))
    squad = []
    for pid, name, pos, rating, goals, ast, apps, club in cur.fetchall():
        position = pos or "?"
        score = _compute_standout_rating(rating, goals, ast, apps, position)
        squad.append({
            "player_id": pid,
            "name": name,
            "position": position,
            "score": score,
            "club_team": club,
        })
    squad.sort(key=lambda p: (-p["score"], p["name"]))
    return squad


def _pools_by_position(squad: list[dict]) -> dict[str, list[dict]]:
    pools: dict[str, list[dict]] = {"GK": [], "DEF": [], "MID": [], "FWD": [], "?": []}
    for p in squad:
        pools.setdefault(p["position"], []).append(p)
    for pos in pools:
        pools[pos].sort(key=lambda x: (-x["score"], x["name"]))
    return pools


def _can_fill(slots: list[str], pools: dict[str, list[dict]]) -> bool:
    need: dict[str, int] = {}
    for pos in slots:
        need[pos] = need.get(pos, 0) + 1
    return all(len(pools.get(pos, [])) >= n for pos, n in need.items())


def _formation_score(slots: list[str], pools: dict[str, list[dict]]) -> float:
    if not _can_fill(slots, pools):
        return -1.0
    used: dict[str, int] = {}
    total = 0.0
    for pos in slots:
        idx = used.get(pos, 0)
        total += pools[pos][idx]["score"]
        used[pos] = idx + 1
    return total


def _pick_formation(pools: dict[str, list[dict]], preferred: str | None) -> str:
    if preferred and preferred in FORMATION_SLOTS and _can_fill(FORMATION_SLOTS[preferred], pools):
        return preferred
    best_f, best_s = "4-3-3", -1.0
    for fname, slots in FORMATION_SLOTS.items():
        score = _formation_score(slots, pools)
        if score > best_s:
            best_s, best_f = score, fname
    return best_f


def _pick_xi(slots: list[str], pools: dict[str, list[dict]], unavailable: set[int]) -> list[dict]:
    used: dict[str, int] = {}
    xi: list[dict] = []
    taken: set[int] = set()
    for i, pos in enumerate(slots):
        idx = used.get(pos, 0)
        picked = None
        while idx < len(pools.get(pos, [])):
            cand = pools[pos][idx]
            idx += 1
            if cand["player_id"] not in unavailable and cand["player_id"] not in taken:
                picked = {**cand, "slot": i + 1, "line_pos": pos}
                taken.add(cand["player_id"])
                break
        if picked:
            xi.append(picked)
        used[pos] = idx
    return xi


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


def _formation_rows(xi: list[dict], formation: str) -> list[dict]:
    if formation == "4-2-3-1":
        groups = [("FWD", 1), ("MID", 3), ("MID", 2), ("DEF", 4), ("GK", 1)]
    elif formation == "3-5-2":
        groups = [("FWD", 2), ("MID", 5), ("DEF", 3), ("GK", 1)]
    elif formation == "5-3-2":
        groups = [("FWD", 2), ("MID", 3), ("DEF", 5), ("GK", 1)]
    elif formation == "4-4-2":
        groups = [("FWD", 2), ("MID", 4), ("DEF", 4), ("GK", 1)]
    elif formation == "3-4-3":
        groups = [("FWD", 3), ("MID", 4), ("DEF", 3), ("GK", 1)]
    else:
        groups = [("FWD", 3), ("MID", 3), ("DEF", 4), ("GK", 1)]

    by_pos: dict[str, list] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in xi:
        by_pos.setdefault(p["line_pos"], []).append(p)

    rows = []
    for pos, count in groups:
        chunk = by_pos.get(pos, [])[:count]
        by_pos[pos] = by_pos.get(pos, [])[count:]
        rows.append({"line": pos, "players": [{"name": p["name"], "score": p["score"]} for p in chunk]})
    return list(reversed(rows))


def get_predicted_lineup(conn, team_name: str, comp: str | None = "WC") -> dict:
    from footballmind_mcp_predict import _resolve_team

    comp = comp or "WC"
    kind = _affil_kind_for_comp(conn, comp)

    with conn.cursor() as cur:
        team_id, _ = _resolve_team(cur, team_name)
        cur.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
        resolved = cur.fetchone()[0]

        squad = _ranked_squad(cur, team_id, kind)
        if not squad:
            return {"team": resolved, "comp": comp, "error": "No squad on file for this team."}

        unavailable_list = _card_suspensions(cur, team_id, comp) + _manual_unavailable(cur, team_id, comp)
        unavailable_ids = {u["player_id"] for u in unavailable_list}
        pools = _pools_by_position([p for p in squad if p["player_id"] not in unavailable_ids])
        opponent = _next_opponent(cur, team_id, comp)

    recent = get_team_formations(conn, resolved, comp, limit=3)
    preferred = recent[0]["formation"] if recent else None
    formation = _pick_formation(pools, preferred)
    xi = _pick_xi(FORMATION_SLOTS[formation], pools, unavailable_ids)

    xi_ids = {p["player_id"] for p in xi}
    bench = [p for p in squad if p["player_id"] not in xi_ids and p["player_id"] not in unavailable_ids][:7]

    return {
        "team": resolved,
        "comp": comp,
        "formation": formation,
        "source": "recent_lineup" if preferred and preferred == formation else "predicted",
        "recent_formations": [r["formation"] for r in recent if r.get("formation")],
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
