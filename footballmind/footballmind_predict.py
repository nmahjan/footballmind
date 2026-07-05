"""
FootballMind -- match outcome + knockout progression from a goals model.

Core idea: do NOT classify W/D/L directly. Predict expected goals for each
side (lambda_home, lambda_away); from those two numbers derive everything:

  - the full scoreline probability matrix (Poisson)
  - P(home win) / P(draw) / P(away win)   -> league & group-stage matches
  - P(home advances)                      -> knockout matches, where a draw in
                                             regulation is resolved by extra
                                             time + penalties (the draw mass is
                                             redistributed, not discarded).

One model, two behaviours, switched on the match stage.
"""

import numpy as np
from scipy.stats import poisson


def score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 10) -> np.ndarray:
    """Joint probability of every scoreline up to max_goals per side.
    matrix[i, j] = P(home scores i, away scores j)."""
    home = poisson.pmf(np.arange(max_goals + 1), lambda_home)
    away = poisson.pmf(np.arange(max_goals + 1), lambda_away)
    return np.outer(home, away)


def outcome_probs(matrix: np.ndarray) -> dict:
    """W/D/L from the score matrix. Use for league & group-stage games."""
    return {
        "home_win": float(np.tril(matrix, -1).sum()),  # i > j
        "draw":     float(np.trace(matrix)),           # i == j
        "away_win": float(np.triu(matrix,  1).sum()),  # j > i
    }


def progression_probs(matrix: np.ndarray, et_edge: float = 0.0) -> dict:
    """P(each side advances) in a single-leg knockout.

    Regulation win  -> that side advances outright.
    Regulation draw -> resolved in ET + penalties, modelled as ~a coin flip
                       nudged toward the stronger side. et_edge in [-0.5, 0.5];
                       0.0 = 50/50. Derive it from the Elo / strength gap.
    """
    o = outcome_probs(matrix)
    p_home_given_draw = 0.5 + et_edge
    home_adv = o["home_win"] + o["draw"] * p_home_given_draw
    return {"home_advance": home_adv, "away_advance": 1.0 - home_adv}


def predict(lambda_home: float, lambda_away: float,
            stage: str, et_edge: float = 0.0) -> dict:
    """Single entry point for the MCP predict_match tool."""
    m = score_matrix(lambda_home, lambda_away)
    o = outcome_probs(m)
    result = {
        "expected_home_goals": float(lambda_home),
        "expected_away_goals": float(lambda_away),
        "home_win_prob": o["home_win"],
        "draw_prob":     o["draw"],
        "away_win_prob": o["away_win"],
    }
    if stage not in ("regular_season", "group"):       # any knockout round
        result["progression"] = progression_probs(m, et_edge)
    return result


# ----------------------------------------------------------------------
# Where lambda_home / lambda_away come from
# ----------------------------------------------------------------------
# Convert an Elo difference into expected goals. Elo is competition-agnostic,
# so club Elo and international Elo are SEPARATE ladders -- which is correct,
# and is what makes this work for the World Cup where PL-trained, league-
# position features would not.
#
#   diff = (home_elo - away_elo) + home_field            # ~0 at neutral WC venues
#   expected_supremacy = diff / 400.0                     # goal-difference proxy
#   base = 1.35                                            # avg goals per team
#   lambda_home = base * (10 ** (+expected_supremacy / 4))
#   lambda_away = base * (10 ** (-expected_supremacy / 4))
#
# et_edge for knockouts can map the same gap to a small advantage, e.g.
#   et_edge = max(-0.15, min(0.15, diff / 2000.0))
#
# A Dixon-Coles / Poisson regression (fitted attack & defence ratings per team)
# is the more rigorous alternative once you have enough match history per
# competition; it produces lambda_home / lambda_away the same way and drops
# straight into predict().

if __name__ == "__main__":
    # Quick check: even strengths, knockout round
    print(predict(1.4, 1.1, stage="quarter_final", et_edge=0.05))
