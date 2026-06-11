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


def link_orphan_predictions(conn):
    """Attach match_id (and team ids) to predictions saved before linkage existed."""
    from footballmind_mcp_predict import _resolve_team

    linked = 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.session_id, p.created_at, p.home_team_id, p.away_team_id "
            "FROM predictions p "
            "WHERE p.match_id IS NULL AND p.was_correct IS NULL")
        rows = cur.fetchall()

        for pid, sid, created_at, home_id, away_id in rows:
            if not home_id or not away_id:
                cur.execute(
                    "SELECT entities_mentioned FROM queries "
                    "WHERE session_id = %s AND query_type = 'predict' "
                    "  AND entities_mentioned ? 'home' "
                    "ORDER BY abs(extract(epoch from (timestamp - %s::timestamptz))) "
                    "LIMIT 1",
                    (sid, created_at))
                ent_row = cur.fetchone()
                if not ent_row:
                    continue
                ent = ent_row[0]
                try:
                    home_id, _ = _resolve_team(cur, ent["home"])
                    away_id, _ = _resolve_team(cur, ent["away"])
                except ValueError:
                    continue
                cur.execute(
                    "UPDATE predictions SET home_team_id = %s, away_team_id = %s "
                    "WHERE id = %s",
                    (home_id, away_id, pid))

            cur.execute(
                "SELECT id FROM matches "
                "WHERE home_team_id = %s AND away_team_id = %s "
                "ORDER BY abs(extract(epoch from (match_date - %s::timestamptz))) "
                "LIMIT 1",
                (home_id, away_id, created_at))
            match_row = cur.fetchone()
            if not match_row:
                continue
            cur.execute("UPDATE predictions SET match_id = %s WHERE id = %s",
                        (match_row[0], pid))
            linked += 1

    conn.commit()
    return linked
