"""
FootballMind -- prediction linkage + grading.

find_fixture: at predict time, link a prediction to the actual upcoming match
              between those teams (same orientation) so it can be graded later.
grade_predictions: after results sync in, fill actual goals and was_correct for
              any linked prediction whose match has now been played.

Grading scores the regulation (90') home/draw/away outcome -- the same target
the backtest uses -- so dashboard accuracy and backtest RPS stay consistent.
"""


def find_fixture(cur, home_id, away_id):
    """Nearest unplayed match with this exact home/away orientation, or None.
    Orientation must match because the stored probabilities are home/away
    specific -- linking a flipped fixture would grade the wrong side."""
    cur.execute(
        "SELECT id FROM matches "
        "WHERE home_team_id = %s AND away_team_id = %s AND home_goals IS NULL "
        "ORDER BY match_date ASC LIMIT 1", (home_id, away_id))
    row = cur.fetchone()
    return row[0] if row else None


def grade_predictions(conn):
    """Grade every linked, played, not-yet-graded prediction. Returns the count."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.home_win_prob, p.draw_prob, p.away_win_prob, "
            "       m.home_goals, m.away_goals "
            "FROM predictions p JOIN matches m ON m.id = p.match_id "
            "WHERE p.was_correct IS NULL AND m.home_goals IS NOT NULL")
        rows = cur.fetchall()
        for pid, hw, dw, aw, hg, ag in rows:
            probs = [hw or 0.0, dw or 0.0, aw or 0.0]
            predicted = probs.index(max(probs))                 # 0 home, 1 draw, 2 away
            actual = 0 if hg > ag else (1 if hg == ag else 2)
            cur.execute(
                "UPDATE predictions SET actual_home_goals = %s, "
                " actual_away_goals = %s, was_correct = %s WHERE id = %s",
                (hg, ag, predicted == actual, pid))
    conn.commit()
    return len(rows)
