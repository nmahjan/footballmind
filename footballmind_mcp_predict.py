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


def _resolve_team(cur, name: str):
    """Look up a team by name; returns (id, type) or raises.

    Tries in order:
      1. Exact case-insensitive match   ("Arsenal FC")
      2. Starts-with match              ("Arsenal" -> "Arsenal FC")
      3. Contains match                 ("city"    -> "Manchester City FC")
    If multiple rows match steps 2/3 the shortest name wins (most specific).
    """
    term = name.strip()
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


def _current_rating(cur, team_id: int) -> float:
    cur.execute("SELECT rating FROM team_ratings WHERE team_id = %s", (team_id,))
    row = cur.fetchone()
    return row[0] if row else 1500.0


def _predict_match(conn, home_team, away_team, match_date,
                   stage="regular_season", session_id=None):
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
        neutral = stage != "regular_season"

        # Use the deployed Dixon-Coles/Elo hybrid if one exists; otherwise fall
        # back to pure Elo so the tool still works on a fresh database.
        if model is None:
            lam_h, lam_a = ratings_to_lambdas(home_elo, away_elo, neutral)
        else:
            lam_h, lam_a = model.expected_goals(home_id, away_id, neutral)
        et_edge = max(-0.15, min(0.15, (home_elo - away_elo) / 2000.0))

        out = predict(lam_h, lam_a, stage=stage, et_edge=et_edge)

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

        reasoning = (f"{home_team} rated {home_elo:.0f} vs {away_team} {away_elo:.0f}"
                     f"{'' if neutral else ' (+home edge)'}; "
                     f"expected goals {lam_h:.2f}-{lam_a:.2f}.")
        key_factors = [
            f"Rating gap: {home_elo - away_elo:+.0f}",
            "Neutral venue" if neutral else "Home advantage applied",
            f"xG: {lam_h:.2f} - {lam_a:.2f}",
        ]

        cur.execute(
            "INSERT INTO predictions (session_id, expected_home_goals, "
            " expected_away_goals, home_win_prob, draw_prob, away_win_prob, "
            " home_advance_prob, confidence, reasoning) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (session_id, lam_h, lam_a, out["home_win_prob"], out["draw_prob"],
             out["away_win_prob"],
             out["progression"]["home_advance"] if knockout else None,
             confidence, reasoning))
    conn.commit()

    return {
        "prediction":    label,
        "confidence":    round(confidence, 3),
        "home_win_prob": round(out["home_win_prob"], 3),
        "draw_prob":     round(out["draw_prob"], 3),
        "away_win_prob": round(out["away_win_prob"], 3),
        "progression":   out.get("progression"),
        "reasoning":     reasoning,
        "key_factors":   key_factors,
    }


# The MCP tool wrapper is registered in server.py; test _predict_match directly.
