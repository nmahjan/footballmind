"""
FootballMind — predicted lineups and availability.

Prefers recent confirmed lineups/formations when synced; otherwise builds XI from
squad depth weighted by comp appearances and recent starts (not goals alone).
"""

from __future__ import annotations

from footballmind_services import (
    _affil_kind_for_comp,
    _compute_standout_rating,
    _player_age,
    classify_line_role,
    get_team_formations,
)

FORMATION_SLOTS: dict[str, list[str]] = {
    "4-3-3": ["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CM", "WING", "ST", "WING"],
    "4-4-2": ["GK", "LB", "CB", "CB", "RB", "CM", "CM", "WING", "WING", "ST", "ST"],
    "4-2-3-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "WING", "CAM", "WING", "ST"],
    "4-3-2-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CAM", "WING", "WING", "ST"],
    "3-5-2": ["GK", "CB", "CB", "CB", "LB", "CDM", "CM", "CM", "RB", "ST", "ST"],
    "5-3-2": ["GK", "LB", "CB", "CB", "CB", "RB", "CM", "CM", "CM", "ST", "ST"],
    "3-4-3": ["GK", "CB", "CB", "CB", "WING", "CM", "CM", "WING", "WING", "ST", "WING"],
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
        "SELECT mlp.player_id, COUNT(*)::int "
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
        "GROUP BY mlp.player_id",
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
            "LEFT JOIN LATERAL ("
            "  SELECT pes.goals, pes.assists, pes.appearances "
            "  FROM player_edition_stats pes "
            "  JOIN competition_editions e ON e.id = pes.edition_id "
            "  JOIN competitions c ON c.id = e.competition_id "
            "  WHERE pes.player_id = p.id AND c.code = %s "
            "    AND pes.appearances > 0 "
            "  ORDER BY e.start_date DESC NULLS LAST LIMIT 1"
            ") prior_comp ON true "
        )
        comp_params = [comp, comp]

    cur.execute(
        "SELECT p.id, p.name, p.position, p.birth_date, tr.rating, "
        "       COALESCE(comp_stats.goals, 0), "
        "       COALESCE(comp_stats.assists, 0), "
        "       COALESCE(comp_stats.appearances, 0), "
        "       COALESCE(prior_comp.goals, cs.goals, 0), "
        "       COALESCE(prior_comp.assists, cs.assists, 0), "
        "       COALESCE(prior_comp.appearances, cs.appearances, 0), "
        "       COALESCE(team_career.career_apps, 0), "
        "       cs.club_team, "
        "       COALESCE(pa.is_captain, FALSE) "
        "FROM player_affiliations pa "
        "JOIN players p ON p.id = pa.player_id "
        "LEFT JOIN team_ratings tr ON tr.team_id = pa.team_id "
        "LEFT JOIN LATERAL ("
        "  SELECT COALESCE(SUM(pes.appearances), 0)::int AS career_apps "
        "  FROM player_edition_stats pes "
        "  WHERE pes.player_id = p.id AND pes.team_id = pa.team_id"
        ") team_career ON true "
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
    for (pid, name, pos, dob, rating, c_goals, c_ast, c_apps,
         goals, ast, apps, career_apps, club, is_captain) in cur.fetchall():
        position = pos or "?"
        if c_apps > 0:
            goals, ast, apps = c_goals, c_ast, c_apps
        line_role = classify_line_role(pos, goals, ast)
        if is_captain and line_role in ("CM", "CDM", "MID"):
            line_role = "CAM"
        base = _compute_standout_rating(rating, goals, ast, apps, position)
        if c_apps == 0 and apps > 0:
            # Prior-season fallback — slight penalty for not featuring yet this campaign.
            base = round(base * 0.88, 1)
        elif c_apps == 0 and apps == 0:
            age = _player_age(dob)
            if age and age >= 23 and line_role in ("CM", "CAM", "CDM", "WING", "ST", "MID"):
                # Senior outfielder with no synced stats (e.g. long injury) — stay in contention.
                base = max(base, _compute_standout_rating(rating, 2, 3, 20, position) * 0.85)
        starts = recent_starts.get(pid, 0)
        # Recent starters and regulars in this comp rank above raw goal scorers.
        score = base + starts * 12 + min(apps, 30) * 0.35
        if is_captain:
            score += 25
        if line_role == "GK" or position == "GK":
            score += min(career_apps, 80) * 0.4 + starts * 8
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
            "career_apps": career_apps,
            "birth_date": dob,
            "is_captain": is_captain,
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
    if slot == "CM" and lr in ("CM", "CDM", "CAM"):
        return True
    if slot == "CDM" and lr in ("CDM", "CM"):
        return True
    if slot == "CAM" and lr in ("CAM", "CM"):
        return True
    if slot == "CB" and lr == "CB":
        return True
    if slot in ("LB", "RB") and lr == slot:
        return True
    # Legacy coarse slots (older formations / synced data)
    if slot == "MID" and lr in ("MID", "CM", "CDM", "CAM", "?"):
        return True
    if slot == "DEF" and lr in ("DEF", "CB", "LB", "RB"):
        return True
    if slot == "FWD" and lr in ("ST", "WING"):
        return True
    return False


def _sorted_candidates(candidates: list[dict], key_fn) -> list[dict]:
    candidates.sort(key=key_fn)
    return candidates


def _prefer_senior(candidates: list[dict], min_age: int = 20) -> list[dict]:
    """Prefer established players over academy names when scores are close."""
    senior = [p for p in candidates if (_player_age(p.get("birth_date")) or 99) >= min_age]
    return senior if senior else candidates


def _gk_rank_key(player: dict) -> tuple:
    age = _player_age(player.get("birth_date")) or 0
    youth = age < 21
    return (
        -(player.get("recent_starts") or 0),
        -(player.get("career_apps") or 0),
        -(player.get("appearances") or 0),
        1 if youth else 0,
        -player["score"],
        player["name"],
    )


def _candidates_for_slot(slot: str, squad: list[dict], taken: set[int]) -> list[dict]:
    """Best-fit players for a lineup slot (role-aware)."""
    avail = [p for p in squad if p["player_id"] not in taken]
    score_key = lambda p: (-p["score"], p["name"])
    if slot == "ST":
        primary = [p for p in avail if p.get("line_role") == "ST"]
        primary.sort(key=lambda p: (-(p.get("goals") or 0), -p["score"], p["name"]))
        if primary:
            return _prefer_senior(primary)
        fwd = [p for p in avail if p.get("position") == "FWD"]
        fwd.sort(key=lambda p: (-(p.get("goals") or 0), -p["score"], p["name"]))
        return _prefer_senior(fwd)
    if slot == "WING":
        primary = [p for p in avail if p.get("line_role") == "WING"]
        primary.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        if primary:
            return _prefer_senior(primary)
        wide = [p for p in avail if p.get("position") == "FWD" and p.get("line_role") != "ST"]
        wide.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        mids = [p for p in avail if p.get("position") == "MID"]
        mids.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        return _prefer_senior(wide + mids)
    if slot == "CAM":
        primary = [p for p in avail if p.get("line_role") == "CAM"]
        primary.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        if primary:
            return _prefer_senior(primary)
        cms = [p for p in avail if p.get("line_role") == "CM"]
        cms.sort(key=lambda p: (-(p.get("assists") or 0), -p["score"], p["name"]))
        return _prefer_senior(cms)
    if slot == "CDM":
        primary = [p for p in avail if p.get("line_role") == "CDM"]
        primary.sort(key=lambda p: (-p["score"], p["name"]))
        if primary:
            return primary
        cms = [p for p in avail if p.get("line_role") == "CM"]
        cms.sort(key=lambda p: (-p["score"], p["name"]))
        return cms
    if slot == "CM":
        primary = [p for p in avail if p.get("line_role") == "CM"]
        primary.sort(key=score_key)
        if primary:
            return primary
        mids = [p for p in avail if p.get("line_role") in ("CDM", "CAM")]
        return _sorted_candidates(mids, score_key)
    if slot == "LB":
        primary = [p for p in avail if p.get("line_role") == "LB"]
        if primary:
            return _sorted_candidates(_prefer_senior(primary), score_key)
        fallback = [p for p in avail if p.get("line_role") == "RB"]
        if fallback:
            return _sorted_candidates(_prefer_senior(fallback), score_key)
        wide_defs = [p for p in avail if p.get("line_role") in ("CB", "DEF")
                     or p.get("position") == "DEF"]
        return _sorted_candidates(_prefer_senior(wide_defs), score_key)
    if slot == "RB":
        primary = [p for p in avail if p.get("line_role") == "RB"]
        if primary:
            return _sorted_candidates(_prefer_senior(primary), score_key)
        fallback = [p for p in avail if p.get("line_role") == "LB"]
        if fallback:
            return _sorted_candidates(_prefer_senior(fallback), score_key)
        wide_defs = [p for p in avail if p.get("line_role") in ("CB", "DEF")
                     or p.get("position") == "DEF"]
        return _sorted_candidates(_prefer_senior(wide_defs), score_key)
    if slot == "CB":
        primary = [p for p in avail if p.get("line_role") == "CB"]
        if primary:
            return _sorted_candidates(primary, score_key)
        defs = [p for p in avail if p.get("position") == "DEF" and p.get("line_role") not in ("LB", "RB")]
        return _sorted_candidates(defs, score_key)
    if slot == "MID":
        primary = [p for p in avail if p.get("line_role") in ("CM", "CDM", "CAM", "MID")]
        if primary:
            return _sorted_candidates(primary, score_key)
        return _sorted_candidates(avail, score_key)
    if slot == "DEF":
        defs = [p for p in avail if p.get("line_role") in ("CB", "LB", "RB", "DEF")
                or p.get("position") == "DEF"]
        return _sorted_candidates(defs, score_key)
    if slot == "GK":
        gks = [p for p in avail if p.get("line_role") == "GK" or p.get("position") == "GK"]
        return _sorted_candidates(gks, _gk_rank_key)
    return _sorted_candidates(avail, score_key)


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
    scores: dict[str, float] = {}
    for fname in order:
        if fname not in FORMATION_SLOTS:
            continue
        score = _formation_score(FORMATION_SLOTS[fname], squad)
        scores[fname] = score
        if score > best_s:
            best_s, best_f = score, fname
    if kind == "club" and best_s > 0:
        for fname in _CLUB_FORMATION_PREF:
            if scores.get(fname, -1) >= best_s * 0.97:
                return fname
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
        ("ST", [11]), ("WING", [9, 10]), ("CAM", [8]), ("CM", [7]), ("CDM", [6]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "4-3-3": [
        ("ST", [10]), ("WING", [9, 11]), ("CM", [7, 8]), ("CDM", [6]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "4-2-3-1": [
        ("ST", [11]), ("WING", [8, 10]), ("CAM", [9]), ("CDM", [6, 7]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "4-4-2": [
        ("ST", [10, 11]), ("WING", [8, 9]), ("CM", [6, 7]),
        ("DEF", [2, 3, 4, 5]), ("GK", [1]),
    ],
    "3-5-2": [
        ("ST", [10, 11]), ("CM", [7, 8]), ("CDM", [6]), ("WING", [5, 9]),
        ("DEF", [2, 3, 4]), ("GK", [1]),
    ],
    "5-3-2": [
        ("ST", [10, 11]), ("CM", [7, 8, 9]),
        ("DEF", [2, 3, 4, 5, 6]), ("GK", [1]),
    ],
    "3-4-3": [
        ("ST", [10]), ("WING", [8, 9, 11]), ("CM", [6, 7]),
        ("DEF", [2, 3, 4]), ("GK", [1]),
    ],
}


def _formation_rows(xi: list[dict], formation: str) -> list[dict]:
    by_slot = {p["slot"]: p for p in xi}
    specs = _FORMATION_ROW_SLOTS.get(formation, _FORMATION_ROW_SLOTS["4-3-3"])
    rows = []
    for line, slots in specs:
        players = [
            {
                "name": by_slot[s]["name"],
                "score": by_slot[s]["score"],
                "position": by_slot[s].get("line_pos") or line,
            }
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
    pool = [p for p in squad if p["player_id"] not in xi_ids
            and p["player_id"] not in unavailable_ids]
    outfield = [p for p in pool if p.get("line_role") != "GK" and p.get("position") != "GK"]
    keepers = sorted(
        [p for p in pool if p.get("line_role") == "GK" or p.get("position") == "GK"],
        key=_gk_rank_key,
    )
    bench = outfield[:6 if keepers else 7]
    if keepers:
        # One backup GK on the bench — never four keepers.
        starter_gk = next((p["player_id"] for p in xi if p.get("line_pos") == "GK"), None)
        backups = [k for k in keepers if k["player_id"] != starter_gk]
        if backups:
            bench.append(backups[0])
        elif len(bench) < 7:
            bench.extend(outfield[6:7])

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
