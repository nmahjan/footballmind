"""Match stakes / pressure context from table position and stage."""

from __future__ import annotations

KNOCKOUT_STAGES = frozenset({
    "round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "third_place",
})

_STAGE_LABELS = {
    "round_of_32": "Round of 32 — win to advance",
    "round_of_16": "Round of 16 — win to advance",
    "quarter_final": "Quarter-final — win to advance",
    "semi_final": "Semi-final — win to advance",
    "final": "Final — winner takes all",
    "third_place": "Third-place playoff",
}


def _team_table_row(table: list[dict], team_name: str) -> dict | None:
    needle = (team_name or "").lower()
    for row in table:
        if (row.get("team") or "").lower() == needle:
            return row
    for row in table:
        t = (row.get("team") or "").lower()
        if needle in t or t in needle:
            return row
    return None


def _group_row(groups: dict, team_name: str) -> tuple[str | None, dict | None, int | None]:
    """Return (group_letter, row, rank_in_group)."""
    needle = (team_name or "").lower()
    for letter, rows in groups.items():
        for i, row in enumerate(rows, 1):
            t = (row.get("team") or "").lower()
            if t == needle or needle in t or t in needle:
                return letter, row, i
    return None, None, None


def _league_labels(home: dict | None, away: dict | None) -> list[str]:
    labels: list[str] = []
    hz = (home or {}).get("zone") or {}
    az = (away or {}).get("zone") or {}
    hid, aid = hz.get("id"), az.get("id")

    if hid == "rel" and aid == "rel":
        labels.append("Relegation six-pointer")
    elif hid == "rel" or aid == "rel":
        labels.append("Relegation survival clash")
    elif hid == "playoff" or aid == "playoff":
        labels.append("Relegation play-off pressure")

    if hid == "ucl" and aid == "ucl":
        labels.append("Top-four clash")
    elif {hid, aid} == {"ucl", "uel"}:
        labels.append("Champions League spot on the line")
    elif hid == "ucl" or aid == "ucl":
        if hid != az.get("id") and aid != hz.get("id"):
            labels.append("Champions League qualification at stake")
    elif hid == "uel" and aid == "uel":
        labels.append("Europa League race")
    elif {hid, aid} == {"uel", "uecl"}:
        labels.append("European qualification battle")

    return labels


def _group_labels(home_rank: int | None, away_rank: int | None,
                    home_pts: int, away_pts: int) -> list[str]:
    labels: list[str] = []
    if home_rank and away_rank:
        if home_rank <= 2 and away_rank <= 2:
            labels.append("Group top-two clash")
        elif max(home_rank, away_rank) >= 3:
            labels.append("Knockout qualification on the line")
    if home_rank and home_rank >= 3 and away_rank and away_rank >= 3:
        if abs(home_pts - away_pts) <= 3:
            labels.append("Must-win for knockout hope")
    return labels


def _build_summary(labels: list[str], stage: str, home: dict | None, away: dict | None) -> str:
    if stage in KNOCKOUT_STAGES:
        return "Knockout football — defeat ends the campaign."
    if "Relegation six-pointer" in labels:
        return "Both teams are in the relegation zone; the loser likely drops further into trouble."
    if "Relegation survival clash" in labels:
        side = "home" if (home or {}).get("zone", {}).get("id") == "rel" else "away"
        return f"A relegation-battle side needs points to climb out of the drop zone."
    if "Top-four clash" in labels or "Champions League spot on the line" in labels:
        return "European qualification pressure — both sides need the points."
    if "Knockout qualification on the line" in labels:
        return "Group-stage points are precious; a loss could end knockout hopes."
    if labels:
        return "High-stakes fixture where table position adds extra pressure."
    if home and away:
        hr, ar = home.get("rank"), away.get("rank")
        if hr and ar and abs(hr - ar) <= 2:
            return f"Close in the table ({hr} vs {ar}) — a result shifts the pecking order."
    return ""


def compute_match_stakes(
    conn,
    comp: str | None,
    home_id: int,
    away_id: int,
    home_name: str,
    away_name: str,
    stage: str = "regular_season",
) -> dict:
    """Derive human-readable stakes from comp, stage, and standings."""
    from footballmind_services import get_groups, get_standings

    labels: list[str] = []
    home_ctx = away_ctx = None

    if stage in KNOCKOUT_STAGES:
        labels.append(_STAGE_LABELS.get(stage, "Knockout — lose and out"))
    elif stage == "group" and comp:
        groups = get_groups(conn, comp)
        _, home_row, home_rank = _group_row(groups, home_name)
        _, away_row, away_rank = _group_row(groups, away_name)
        if home_row:
            home_ctx = {"rank": home_rank, "pts": home_row.get("Pts"), "group": True}
        if away_row:
            away_ctx = {"rank": away_rank, "pts": away_row.get("Pts"), "group": True}
        labels.extend(_group_labels(
            home_rank, away_rank,
            home_row.get("Pts", 0) if home_row else 0,
            away_row.get("Pts", 0) if away_row else 0,
        ))
    elif comp and comp not in ("WC",) and stage == "regular_season":
        table = get_standings(conn, comp)
        home_row = _team_table_row(table, home_name)
        away_row = _team_table_row(table, away_name)
        if home_row:
            home_ctx = {
                "rank": home_row.get("rank"),
                "pts": home_row.get("Pts"),
                "zone": home_row.get("zone"),
            }
        if away_row:
            away_ctx = {
                "rank": away_row.get("rank"),
                "pts": away_row.get("Pts"),
                "zone": away_row.get("zone"),
            }
        labels.extend(_league_labels(home_row, away_row))
    elif comp == "WC" and stage == "group":
        groups = get_groups(conn, "WC")
        _, home_row, home_rank = _group_row(groups, home_name)
        _, away_row, away_rank = _group_row(groups, away_name)
        if home_row:
            home_ctx = {"rank": home_rank, "pts": home_row.get("Pts"), "group": True}
        if away_row:
            away_ctx = {"rank": away_rank, "pts": away_row.get("Pts"), "group": True}
        labels.extend(_group_labels(
            home_rank, away_rank,
            home_row.get("Pts", 0) if home_row else 0,
            away_row.get("Pts", 0) if away_row else 0,
        ))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_labels = []
    for lbl in labels:
        if lbl not in seen:
            seen.add(lbl)
            unique_labels.append(lbl)

    summary = _build_summary(unique_labels, stage, home_ctx, away_ctx)
    high_pressure = bool(unique_labels) or stage in KNOCKOUT_STAGES

    return {
        "labels": unique_labels,
        "summary": summary,
        "high_pressure": high_pressure,
        "context": {
            "comp": comp,
            "stage": stage,
            "home": home_ctx,
            "away": away_ctx,
        },
    }


MAX_TOTAL_XG_SHRINK = 0.06   # up to 6% lower combined expected goals
MAX_DRAW_TILT = 0.05         # pull lambdas toward parity → more draws
MIN_LAMBDA = 0.05

_CAGEY_LABELS = frozenset({
    "Relegation six-pointer",
    "Relegation survival clash",
    "Relegation play-off pressure",
    "Top-four clash",
    "Champions League spot on the line",
    "Champions League qualification at stake",
    "Europa League race",
    "European qualification battle",
    "Knockout qualification on the line",
    "Must-win for knockout hope",
    "Group top-two clash",
})


def pressure_intensity(stakes: dict) -> float:
    """0–1 score from stakes labels and stage."""
    if not stakes.get("high_pressure"):
        return 0.0
    labels = stakes.get("labels") or []
    stage = (stakes.get("context") or {}).get("stage", "regular_season")
    intensity = min(1.0, 0.25 + 0.12 * len(labels))
    if stage in KNOCKOUT_STAGES:
        intensity = min(1.0, intensity + 0.12)
    if labels and any(lbl in _CAGEY_LABELS for lbl in labels):
        intensity = min(1.0, intensity + 0.08)
    return round(intensity, 3)


def apply_stakes_to_lambdas(
    lam_home: float,
    lam_away: float,
    stakes: dict,
) -> tuple[float, float, dict]:
    """Nudge expected goals for high-pressure fixtures (Phase B).

    - Cagey stakes → slightly lower total xG (both sides)
    - League/group pressure → small draw tilt (favorites less dominant)
    Capped so adjustments stay within ~±6% on goal expectation.
    """
    intensity = pressure_intensity(stakes)
    if intensity <= 0:
        return lam_home, lam_away, {"applied": False}

    labels = set(stakes.get("labels") or [])
    stage = (stakes.get("context") or {}).get("stage", "regular_season")
    lh, la = float(lam_home), float(lam_away)
    meta: dict = {"applied": True, "intensity": intensity}

    cagey = bool(labels & _CAGEY_LABELS) or stage in KNOCKOUT_STAGES
    if cagey:
        shrink = 1.0 - MAX_TOTAL_XG_SHRINK * intensity
        lh *= shrink
        la *= shrink
        meta["total_xg_multiplier"] = round(shrink, 4)

    if stage in ("regular_season", "group") and labels:
        tilt = MAX_DRAW_TILT * intensity
        mid = (lh + la) / 2.0
        lh = lh + (mid - lh) * tilt
        la = la + (mid - la) * tilt
        meta["draw_tilt"] = round(tilt, 4)

    return max(lh, MIN_LAMBDA), max(la, MIN_LAMBDA), meta


def infer_comp_for_fixture(cur, home_id: int, away_id: int,
                           comp_code: str | None = None) -> tuple[str | None, str | None]:
    """Best-effort comp + stage from the next fixture between these teams."""
    comp_filter = " AND c.code = %s " if comp_code else ""
    params = [home_id, away_id]
    if comp_code:
        params.append(comp_code)
    cur.execute(
        "SELECT c.code, m.stage FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE m.home_team_id = %s AND m.away_team_id = %s "
        "  AND m.home_goals IS NULL "
        + comp_filter +
        "ORDER BY m.match_date ASC NULLS LAST LIMIT 1",
        params)
    row = cur.fetchone()
    if row:
        return row[0], row[1]
    params = [home_id, away_id, away_id, home_id]
    if comp_code:
        params.append(comp_code)
    cur.execute(
        "SELECT c.code, m.stage FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE ((m.home_team_id = %s AND m.away_team_id = %s) "
        "    OR (m.home_team_id = %s AND m.away_team_id = %s)) "
        "  AND m.home_goals IS NULL "
        + comp_filter +
        "ORDER BY m.match_date ASC NULLS LAST LIMIT 1",
        params)
    row = cur.fetchone()
    if row:
        return row[0], row[1]
    params = [home_id, away_id, away_id, home_id]
    if comp_code:
        params.append(comp_code)
    cur.execute(
        "SELECT c.code, m.stage FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE ((m.home_team_id = %s AND m.away_team_id = %s) "
        "    OR (m.home_team_id = %s AND m.away_team_id = %s)) "
        + comp_filter +
        "ORDER BY CASE WHEN m.home_goals IS NULL THEN 0 ELSE 1 END, "
        "         m.match_date DESC NULLS LAST LIMIT 1",
        params)
    row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


def infer_knockout_stage_in_comp(cur, comp_code: str,
                                 home_id: int, away_id: int) -> str | None:
    """When a tournament comp is selected, pick a knockout stage for predictions."""
    if comp_code not in KNOCKOUT_STAGES and comp_code not in ("WC", "CL"):
        return None
    cur.execute(
        "SELECT m.stage FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s "
        "  AND m.stage NOT IN ('regular_season', 'group') "
        "  AND m.home_goals IS NULL "
        "  AND (m.home_team_id IN (%s, %s) OR m.away_team_id IN (%s, %s)) "
        "ORDER BY m.match_date ASC NULLS LAST LIMIT 1",
        (comp_code, home_id, away_id, home_id, away_id))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "SELECT 1 FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = %s "
        "  AND m.stage NOT IN ('regular_season', 'group') "
        "LIMIT 1",
        (comp_code,))
    if cur.fetchone():
        return "round_of_32"
    return None
