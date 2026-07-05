"""
FootballMind -- the ratings layer (Elo).

Elo gives every team one comparable number that moves after each match. Because
clubs only face clubs and nations only face nations, club and international
ratings stay on separate ladders automatically -- which is why this works for
the World Cup where league-position features do not.

This module:
  - computes Elo updates (importance- and margin-weighted)
  - applies a played match to team_ratings / rating_history
  - converts a rating gap into the lambda_home / lambda_away the model needs
"""

BASE_GOALS = 1.35          # avg goals per side at parity
HFA_ELO    = 65            # home-field advantage in Elo points (0 at neutral venues)

# K-factor base by match importance. Clubs: a flat league value is fine.
IMPORTANCE = {
    "friendly":    10,
    "league":      20,     # domestic league default
    "qualifier":   25,
    "continental": 40,     # Euro / Copa America
    "world_cup":   60,
}


def expected_score(rating_a: float, rating_b: float) -> float:
    """Elo win expectancy of A vs B (a draw counts as half to each)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _goal_diff_multiplier(goal_diff: int) -> float:
    """Bigger margins move ratings more."""
    g = abs(goal_diff)
    if g <= 1:
        return 1.0
    if g == 2:
        return 1.5
    return (11 + g) / 8.0


def update_elo(home: float, away: float, home_goals: int, away_goals: int,
               importance: str = "league", neutral: bool = False) -> tuple:
    """Return (new_home_rating, new_away_rating) after one played match.
    Total rating is conserved: whatever one side gains, the other loses."""
    home_field = 0.0 if neutral else HFA_ELO
    e_home = expected_score(home + home_field, away)

    if home_goals > away_goals:
        s_home = 1.0
    elif home_goals == away_goals:
        s_home = 0.5
    else:
        s_home = 0.0

    k = IMPORTANCE.get(importance, 20) * _goal_diff_multiplier(home_goals - away_goals)
    delta = k * (s_home - e_home)
    return home + delta, away - delta


def ratings_to_lambdas(home_elo: float, away_elo: float,
                       neutral: bool = False) -> tuple:
    """Map a rating gap to expected goals per side (this feeds the model).
    The /4 exponent is the one knob to calibrate against real scorelines."""
    home_field = 0.0 if neutral else HFA_ELO
    supremacy = ((home_elo + home_field) - away_elo) / 400.0
    lambda_home = BASE_GOALS * (10 ** (+supremacy / 4))
    lambda_away = BASE_GOALS * (10 ** (-supremacy / 4))
    return lambda_home, lambda_away


def apply_match_result(conn, match_id: int, importance: str = "league") -> None:
    """Read a played match, move both teams' ratings, log the change.
    Call this once per match after the result is known."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT home_team_id, away_team_id, home_goals, away_goals, "
            "       match_date, stage FROM matches WHERE id = %s", (match_id,))
        row = cur.fetchone()
        if row is None or row[2] is None:
            return                                  # not found, or not played yet
        home_id, away_id, hg, ag, match_date, stage = row
        neutral = stage != "regular_season"         # tournament venues are neutral*

        cur.execute("SELECT rating FROM team_ratings WHERE team_id = %s", (home_id,))
        home_before = (cur.fetchone() or (1500.0,))[0]
        cur.execute("SELECT rating FROM team_ratings WHERE team_id = %s", (away_id,))
        away_before = (cur.fetchone() or (1500.0,))[0]

        home_after, away_after = update_elo(
            home_before, away_before, hg, ag, importance, neutral)

        for tid, before, after in ((home_id, home_before, home_after),
                                   (away_id, away_before, away_after)):
            cur.execute(
                "INSERT INTO team_ratings (team_id, rating, updated_at) "
                "VALUES (%s, %s, now()) "
                "ON CONFLICT (team_id) DO UPDATE "
                "  SET rating = EXCLUDED.rating, updated_at = now()",
                (tid, after))
            cur.execute(
                "INSERT INTO rating_history "
                "(team_id, match_id, rating_before, rating_after, as_of) "
                "VALUES (%s, %s, %s, %s, %s)",
                (tid, match_id, before, after, match_date))
    conn.commit()

# * Simplification: treats all World Cup matches as neutral. The three host
#   nations (USA / Canada / Mexico) actually get a real home edge -- add a
#   host-team check here if you want to model it.
