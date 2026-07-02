"""
FootballMind -- the predict_match MCP tool (the integration point).

Chains the whole stack on one request:
  resolve team names  ->  read current Elo ratings  ->  ratings to expected
  goals  ->  goals model (W/D/L or knockout progression)  ->  persist  ->
  return the structured answer the chat UI renders as a prediction card.

The core logic lives in _predict_match(conn, ...) as a plain function so it is
unit-testable; the MCP tool is a thin wrapper around it.
"""

from footballmind_elo import ratings_to_lambdas
from footballmind_predict import predict
from footballmind_production import load_hybrid


_TEAM_ALIASES = {
    # Names must match football-data.org exactly (see sync upsert_team).
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.": "United States",
    "usmnt": "United States",
    "united states of america": "United States",
    "south korea": "South Korea",
    "korea": "South Korea",
    "korea republic": "South Korea",
    "republic of korea": "South Korea",
    "koreans": "South Korea",
    "england": "England",
    "uk": "England",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
    "ivory coast": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "dr congo": "Congo DR",
    "democratic republic of congo": "Congo DR",
    "congo dr": "Congo DR",
    "bosnia": "Bosnia-Herzegovina",
    "bosnia and herzegovina": "Bosnia-Herzegovina",
    "cape verde": "Cape Verde Islands",
    "czech republic": "Czechia",
    "turkey": "Turkey",
    "türkiye": "Turkey",
    "iran": "Iran",
    "ir iran": "Iran",
}


def _resolve_team(cur, name: str):
    """Look up a team by name; returns (id, type) or raises.

    Tries in order:
      0. Alias map (common abbreviations / alternate names)
      1. Exact case-insensitive match   ("Arsenal FC")
      2. Starts-with match              ("Arsenal" -> "Arsenal FC")
      3. Contains match                 ("city"    -> "Manchester City FC")
    If multiple rows match steps 2/3 the shortest name wins (most specific).
    """
    term = name.strip()
    # Step 0: alias map
    term = _TEAM_ALIASES.get(term.lower(), term)
    cur.execute("SELECT id, type, name FROM teams WHERE lower(name) = lower(%s)", (term,))
    row = cur.fetchone()
    if row:
        return row[0], row[1]

    cur.execute(
        "SELECT id, type, name FROM teams "
        "WHERE lower(name) LIKE lower(%s) || '%%' "
        "ORDER BY length(name) LIMIT 1", (term,))
    row = cur.fetchone()
    if row:
        return row[0], row[1]

    cur.execute(
        "SELECT id, type, name FROM teams "
        "WHERE lower(name) LIKE '%%' || lower(%s) || '%%' "
        "ORDER BY length(name) LIMIT 1", (term,))
    row = cur.fetchone()
    if row:
        return row[0], row[1]

    raise ValueError(f"Unknown team: {name!r}")


def _build_narrative(home, away, home_elo, away_elo, lam_h, lam_a,
                     home_form, away_form, h2h, neutral) -> str:
    """Generate a broadcast-style one-paragraph explanation."""
    parts = []

    # --- Rating edge ---
    gap = home_elo - away_elo
    if abs(gap) < 40:
        parts.append(f"{home} and {away} are closely matched on current ratings "
                     f"({home_elo:.0f} vs {away_elo:.0f})")
    elif gap > 250:
        parts.append(f"{home} are the heavy favourites, rated {gap:.0f} points "
                     f"above {away} ({home_elo:.0f} vs {away_elo:.0f})")
    elif gap > 0:
        parts.append(f"{home} hold a {gap:.0f}-point rating edge over {away} "
                     f"({home_elo:.0f} vs {away_elo:.0f})")
    elif gap < -250:
        parts.append(f"{away} are the heavy favourites, rated {-gap:.0f} points "
                     f"above {home} ({away_elo:.0f} vs {home_elo:.0f})")
    else:
        parts.append(f"{away} carry a {-gap:.0f}-point rating advantage "
                     f"({away_elo:.0f} vs {home_elo:.0f})")

    # --- xG / attacking model ---
    if lam_h > lam_a * 1.6:
        parts.append(f"the model expects a dominant attacking display from {home} "
                     f"(xG {lam_h:.2f} vs {lam_a:.2f})")
    elif lam_a > lam_h * 1.6:
        parts.append(f"the model gives {away} a clear attacking edge "
                     f"(xG {lam_h:.2f} vs {lam_a:.2f})")
    else:
        parts.append(f"both sides are expected to find the net "
                     f"(xG {lam_h:.2f}–{lam_a:.2f})")

    # --- Form ---
    def _form_phrase(team, form):
        if not form:
            return None
        wins = form.count("W")
        losses = form.count("L")
        seq = " ".join(form)
        if wins >= 4:
            return f"{team} arrive in excellent form ({seq})"
        if wins == 3:
            return f"{team} have been solid recently ({seq})"
        if losses >= 3:
            return f"{team} have been struggling ({seq})"
        if losses >= 2 and wins <= 1:
            return f"{team} come in on the back of a difficult run ({seq})"
        return None

    h_phrase = _form_phrase(home, home_form)
    a_phrase = _form_phrase(away, away_form)
    if h_phrase and a_phrase:
        parts.append(h_phrase + ", while " + a_phrase[0].lower() + a_phrase[1:])
    elif h_phrase:
        parts.append(h_phrase)
    elif a_phrase:
        parts.append(a_phrase)

    # --- H2H ---
    if h2h and h2h.get("played", 0) >= 3:
        hw, d, aw, pl = h2h["home_wins"], h2h["draws"], h2h["away_wins"], h2h["played"]
        if hw > aw + 1:
            parts.append(f"historically {home} have dominated this fixture, "
                         f"winning {hw} of the last {pl} meetings")
        elif aw > hw + 1:
            parts.append(f"historically {away} have the better of this matchup, "
                         f"winning {aw} of the last {pl} meetings")

    # --- Venue ---
    if not neutral:
        parts.append(f"home advantage gives {home} an additional boost")

    # Join into one flowing sentence chain
    if len(parts) == 1:
        return parts[0].capitalize() + "."
    return parts[0].capitalize() + "; " + "; ".join(parts[1:]) + "."


def _current_rating(cur, team_id: int) -> float:
    cur.execute("SELECT rating FROM team_ratings WHERE team_id = %s", (team_id,))
    row = cur.fetchone()
    return row[0] if row else 1500.0


def _team_form(cur, team_id: int, n: int = 5) -> list[str]:
    """Last n results for a team: list of 'W'/'D'/'L' newest-first."""
    cur.execute(
        "SELECT home_team_id, home_goals, away_goals FROM matches "
        "WHERE (home_team_id = %s OR away_team_id = %s) "
        "  AND home_goals IS NOT NULL "
        "ORDER BY match_date DESC LIMIT %s",
        (team_id, team_id, n))
    results = []
    for home_id, hg, ag in cur.fetchall():
        if home_id == team_id:
            results.append("W" if hg > ag else ("D" if hg == ag else "L"))
        else:
            results.append("W" if ag > hg else ("D" if ag == hg else "L"))
    return results


def _head_to_head(cur, home_id: int, away_id: int, n: int = 5) -> dict:
    """Last n meetings between two teams regardless of orientation."""
    cur.execute(
        "SELECT home_team_id, home_goals, away_goals FROM matches "
        "WHERE ((home_team_id = %s AND away_team_id = %s) "
        "    OR (home_team_id = %s AND away_team_id = %s)) "
        "  AND home_goals IS NOT NULL "
        "ORDER BY match_date DESC LIMIT %s",
        (home_id, away_id, away_id, home_id, n))
    h_wins = d = a_wins = 0
    for side_home, hg, ag in cur.fetchall():
        # normalise: "home" refers to the home_id team regardless of who was home
        first_won = hg > ag if side_home == home_id else ag > hg
        second_won = hg > ag if side_home == away_id else ag > hg
        if hg == ag:
            d += 1
        elif first_won:
            h_wins += 1
        else:
            a_wins += 1
    return {"home_wins": h_wins, "draws": d, "away_wins": a_wins,
            "played": h_wins + d + a_wins}


def _save_prediction(cur, session_id, match_id, home_id, away_id,
                     lam_h, lam_a, out, knockout, confidence, reasoning):
    """Insert or refresh an open prediction for this session + fixture."""
    sid = session_id or None
    hw, dw, aw = out["home_win_prob"], out["draw_prob"], out["away_win_prob"]
    ha = out["progression"]["home_advance"] if knockout else None
    cols = (
        "expected_home_goals = %s, expected_away_goals = %s, "
        "home_win_prob = %s, draw_prob = %s, away_win_prob = %s, "
        "home_advance_prob = %s, confidence = %s, reasoning = %s, "
        "created_at = now()"
    )
    vals = (lam_h, lam_a, hw, dw, aw, ha, confidence, reasoning)

    if match_id:
        cur.execute(
            "SELECT id FROM predictions "
            "WHERE session_id = %s AND match_id = %s AND was_correct IS NULL "
            "LIMIT 1",
            (sid, match_id))
    else:
        cur.execute(
            "SELECT id FROM predictions "
            "WHERE session_id = %s AND home_team_id = %s AND away_team_id = %s "
            "  AND was_correct IS NULL "
            "LIMIT 1",
            (sid, home_id, away_id))
    row = cur.fetchone()

    if row:
        cur.execute(f"UPDATE predictions SET {cols} WHERE id = %s", (*vals, row[0]))
        return

    cur.execute(
        "INSERT INTO predictions (session_id, match_id, home_team_id, away_team_id, "
        " expected_home_goals, expected_away_goals, home_win_prob, draw_prob, "
        " away_win_prob, home_advance_prob, confidence, reasoning) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (sid, match_id, home_id, away_id, lam_h, lam_a, hw, dw, aw, ha,
         confidence, reasoning))


def _predict_match(conn, home_team, away_team, match_date,
                   stage="regular_season", session_id=None, neutral=None,
                   comp=None):
    """Predict a match.

    neutral: True  = no home-field bonus (WC / Euros / all international tournaments)
             False = home-field bonus applied (club home ground)
             None  = auto-detect: always neutral for national teams; for clubs,
                     neutral only in knockout rounds.
    """
    with conn.cursor() as cur:
        home_id, home_type = _resolve_team(cur, home_team)
        away_id, away_type = _resolve_team(cur, away_team)
        if home_type != away_type:                       # guard: no club vs nation
            raise ValueError("Cannot predict a club against a national team.")

        # clubs and nations are separate ladders -> separate deployed models
        model = load_hybrid(conn, name=("production_club" if home_type == "club"
                                        else "production_international"))

        home_elo = _current_rating(cur, home_id)
        away_elo = _current_rating(cur, away_id)

        if neutral is None:
            # National team tournaments are always at neutral venues.
            # Club matches: neutral only in knockout rounds (Champions League
            # finals, etc.) — domestic league games always have a home team.
            neutral = (home_type == "national") or (stage != "regular_season")

        # Use the deployed Dixon-Coles/Elo hybrid if one exists; otherwise fall
        # back to pure Elo so the tool still works on a fresh database.
        if model is None:
            lam_h, lam_a = ratings_to_lambdas(home_elo, away_elo, neutral)
        else:
            lam_h, lam_a = model.expected_goals(home_id, away_id, neutral)
        et_edge = max(-0.15, min(0.15, (home_elo - away_elo) / 2000.0))

        from footballmind_stakes import (
            apply_stakes_to_lambdas,
            compute_match_stakes,
            infer_comp_for_fixture,
            infer_knockout_stage_in_comp,
        )
        inf_comp, inf_stage = infer_comp_for_fixture(
            cur, home_id, away_id, comp_code=comp)
        eff_comp = comp or inf_comp
        eff_stage = stage
        if inf_stage and eff_stage in ("regular_season", "group"):
            if not comp or inf_comp == comp:
                eff_stage = inf_stage
        elif eff_stage == "regular_season" and eff_comp in ("WC", "CL"):
            fallback = infer_knockout_stage_in_comp(
                cur, eff_comp, home_id, away_id)
            if fallback:
                eff_stage = fallback
        stakes = compute_match_stakes(
            conn, eff_comp, home_id, away_id, home_team, away_team, eff_stage)

        lam_h_base, lam_a_base = lam_h, lam_a
        lam_h, lam_a, stakes_adj = apply_stakes_to_lambdas(lam_h, lam_a, stakes)

        out = predict(lam_h, lam_a, stage=eff_stage, et_edge=et_edge)

        knockout = "progression" in out
        if knockout:
            home_adv = out["progression"]["home_advance"]
            label = f"{home_team} advance" if home_adv >= 0.5 else f"{away_team} advance"
            confidence = max(home_adv, 1 - home_adv)
        else:
            probs = {home_team: out["home_win_prob"],
                     "Draw":    out["draw_prob"],
                     away_team: out["away_win_prob"]}
            label = max(probs, key=probs.get)
            confidence = probs[label]

        raw_confidence = confidence
        from footballmind_calibration import adjust_confidence_from_calibration
        confidence, cal_gap = adjust_confidence_from_calibration(conn, confidence)

        home_form = _team_form(cur, home_id)
        away_form = _team_form(cur, away_id)
        h2h = _head_to_head(cur, home_id, away_id)

        # Replace terse numeric string with full narrative
        reasoning = _build_narrative(home_team, away_team, home_elo, away_elo,
                                     lam_h, lam_a, home_form, away_form, h2h, neutral)
        if stakes.get("summary"):
            reasoning = reasoning.rstrip(".") + f". {stakes['summary']}"
        if stakes_adj.get("applied"):
            reasoning = (
                reasoning.rstrip(".")
                + ". Model nudged for high stakes — slightly tighter and more draw-prone."
            )
        key_factors = [
            f"Rating gap: {home_elo - away_elo:+.0f}",
            "Neutral venue" if neutral else "Home advantage applied",
            f"xG: {lam_h:.2f} – {lam_a:.2f}",
        ]
        if stakes_adj.get("applied"):
            key_factors.append("High-pressure λ adjustment applied")
        if cal_gap is not None and abs(confidence - raw_confidence) >= 0.005:
            key_factors.append(
                f"Calibration-adjusted ({int(raw_confidence * 100)}% → {int(confidence * 100)}%)"
            )
        key_factors.extend(stakes.get("labels") or [])

        from footballmind_grading import find_fixture
        match_id = find_fixture(cur, home_id, away_id, comp_code=comp)

        _save_prediction(cur, session_id, match_id, home_id, away_id,
                         lam_h, lam_a, out, knockout, confidence, reasoning)
    conn.commit()

    return {
        "prediction":    label,
        "confidence":    round(confidence, 3),
        "home_win_prob": round(out["home_win_prob"], 3),
        "draw_prob":     round(out["draw_prob"], 3),
        "away_win_prob": round(out["away_win_prob"], 3),
        "progression":   out.get("progression"),
        "is_knockout":   knockout,
        "reasoning":     reasoning,
        "key_factors":   key_factors,
        "home_form":     home_form,
        "away_form":     away_form,
        "h2h":           h2h,
        # expose raw numbers so /api/analyze can pass them to Claude
        "home_elo":      round(home_elo),
        "away_elo":      round(away_elo),
        "home_xg":       round(lam_h, 2),
        "away_xg":       round(lam_a, 2),
        "home_xg_base":  round(lam_h_base, 2),
        "away_xg_base":  round(lam_a_base, 2),
        "neutral":       neutral,
        "comp":          eff_comp,
        "stage":         eff_stage,
        "stakes":        stakes,
        "stakes_adjustment": stakes_adj,
        "calibration_gap": cal_gap,
    }


# The MCP tool wrapper is registered in server.py; test _predict_match directly.
