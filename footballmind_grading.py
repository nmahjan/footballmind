"""
FootballMind -- prediction linkage + grading.

find_fixture: at predict time, link a prediction to the actual upcoming match
              between those teams (same orientation) so it can be graded later.
grade_predictions: after results sync in, fill actual goals and was_correct for
              any linked prediction whose match has now been played.

Grading scores the regulation (90') home/draw/away outcome -- the same target
the backtest uses -- so dashboard accuracy and backtest RPS stay consistent.
"""


def find_fixture(
    cur,
    home_id,
    away_id,
    *,
    edition_id: int | None = None,
    comp_code: str | None = None,
):
    """Best matching fixture for this home/away orientation.

    Prefers the next unplayed match, then the nearest kickoff in the same
    competition (including finished games) so predictions still link after
    scores sync.
    """
    params: list = [home_id, away_id]
    sql = (
        "SELECT m.id FROM matches m "
        "JOIN competition_editions e ON e.id = m.edition_id "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE m.home_team_id = %s AND m.away_team_id = %s "
    )
    if edition_id is not None:
        sql += "AND m.edition_id = %s "
        params.append(edition_id)
    elif comp_code:
        sql += "AND c.code = %s "
        params.append(comp_code)
    sql += (
        "ORDER BY "
        "  CASE WHEN m.home_goals IS NULL AND m.away_goals IS NULL THEN 0 ELSE 1 END, "
        "  CASE WHEN m.match_date >= now() - interval '6 hours' THEN 0 ELSE 1 END, "
        "  ABS(extract(epoch FROM (m.match_date - now()))) "
        "LIMIT 1"
    )
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def grade_predictions(conn):
    """Grade linked predictions from match scores.

    Re-grades when football-data.org later corrects a score so stale
    actual_home_goals / actual_away_goals do not leak into the UI.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.home_win_prob, p.draw_prob, p.away_win_prob, "
            "       m.home_goals, m.away_goals, m.stage, "
            "       m.advancing_team_id, m.home_team_id, "
            "       m.went_to_pens, m.home_pens, m.away_pens, m.away_team_id "
            "FROM predictions p JOIN matches m ON m.id = p.match_id "
            "WHERE m.home_goals IS NOT NULL "
            "  AND (p.was_correct IS NULL "
            "       OR p.actual_home_goals IS DISTINCT FROM m.home_goals "
            "       OR p.actual_away_goals IS DISTINCT FROM m.away_goals)")
        rows = cur.fetchall()
        knockout = {
            "round_of_32", "round_of_16", "quarter_final", "semi_final", "final",
        }
        for (pid, hw, dw, aw, hg, ag, stage, adv_id, home_tid,
             went_to_pens, home_pens, away_pens, away_tid) in rows:
            probs = [hw or 0.0, dw or 0.0, aw or 0.0]
            predicted = probs.index(max(probs))                 # 0 home, 1 draw, 2 away
            if stage in knockout and adv_id:
                actual = 0 if adv_id == home_tid else 2
            elif (stage in knockout and went_to_pens
                  and home_pens is not None and away_pens is not None
                  and home_pens != away_pens):
                actual = 0 if home_pens > away_pens else 2
            else:
                actual = 0 if hg > ag else (1 if hg == ag else 2)
            cur.execute(
                "UPDATE predictions SET actual_home_goals = %s, "
                " actual_away_goals = %s, was_correct = %s WHERE id = %s",
                (hg, ag, predicted == actual, pid))
    conn.commit()
    return len(rows)


def _bulk_link_predictions_by_teams(conn, comp_code: str | None = None) -> int:
    """Fast SQL pass: link orphan predictions to the closest matching fixture."""
    params: list = []
    comp_filter = ""
    if comp_code:
        comp_filter = "AND c.code = %s "
        params.append(comp_code)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE predictions p SET match_id = sub.match_id "
            "FROM ("
            "  SELECT DISTINCT ON (p2.id) p2.id AS pid, m.id AS match_id "
            "  FROM predictions p2 "
            "  JOIN matches m ON m.home_team_id = p2.home_team_id "
            "                AND m.away_team_id = p2.away_team_id "
            "  JOIN competition_editions e ON e.id = m.edition_id "
            "  JOIN competitions c ON c.id = e.competition_id "
            "  WHERE p2.match_id IS NULL "
            "    AND p2.home_team_id IS NOT NULL "
            "    AND p2.away_team_id IS NOT NULL "
            "    AND abs(extract(epoch FROM (m.match_date - p2.created_at))) "
            "        < 86400 * 21 "
            f"  {comp_filter}"
            "  ORDER BY p2.id, "
            "    abs(extract(epoch FROM (m.match_date - p2.created_at)))"
            ") sub "
            "WHERE p.id = sub.pid",
            params,
        )
        n = cur.rowcount
    conn.commit()
    return n


def link_orphan_predictions(conn, *, comp_code: str | None = None):
    """Attach match_id (and team ids) to predictions saved before linkage existed."""
    from footballmind_mcp_predict import _resolve_team

    linked = _bulk_link_predictions_by_teams(conn, comp_code)

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
                    "ORDER BY abs(extract(epoch FROM (timestamp - %s::timestamptz))) "
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

            match_id = find_fixture(
                cur, home_id, away_id, comp_code=comp_code,
            )
            if not match_id:
                continue
            cur.execute(
                "UPDATE predictions SET match_id = %s WHERE id = %s",
                (match_id, pid),
            )
            linked += 1

    conn.commit()
    return linked


def backfill_finished_predictions(
    conn,
    comp_code: str = "WC",
    *,
    limit: int = 40,
) -> int:
    """Create model predictions for recent finished matches missing one."""
    from footballmind_mcp_predict import _predict_match

    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, th.name, ta.name, m.match_date::text, "
            "       COALESCE(m.stage, 'group') "
            "FROM matches m "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "WHERE c.code = %s "
            "  AND m.home_goals IS NOT NULL "
            "  AND m.away_goals IS NOT NULL "
            "  AND m.match_date >= (CURRENT_DATE - INTERVAL '14 days') "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM predictions p WHERE p.match_id = m.id"
            "  ) "
            "ORDER BY m.match_date DESC "
            "LIMIT %s",
            (comp_code, limit),
        )
        rows = cur.fetchall()

    created = 0
    for match_id, home, away, match_date, stage in rows:
        try:
            _predict_match(
                conn, home, away,
                match_date=match_date,
                stage=stage,
                comp=comp_code,
                session_id=None,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM predictions WHERE match_id = %s LIMIT 1",
                    (match_id,),
                )
                if cur.fetchone():
                    created += 1
                else:
                    cur.execute(
                        "UPDATE predictions SET match_id = %s "
                        "WHERE id = ("
                        "  SELECT p.id FROM predictions p "
                        "  JOIN teams th ON th.id = p.home_team_id "
                        "  JOIN teams ta ON ta.id = p.away_team_id "
                        "  WHERE p.match_id IS NULL AND th.name = %s AND ta.name = %s "
                        "  ORDER BY p.created_at DESC LIMIT 1"
                        ")",
                        (match_id, home, away),
                    )
                    if cur.rowcount:
                        created += 1
                conn.commit()
        except Exception:
            conn.rollback()
            continue

    grade_predictions(conn)
    return created


def ensure_result_predictions(
    conn,
    comp_code: str = "WC",
    *,
    backfill_limit: int = 40,
) -> dict[str, int]:
    """Link orphan predictions and backfill model picks for finished matches."""
    linked = link_orphan_predictions(conn, comp_code=comp_code)
    created = backfill_finished_predictions(conn, comp_code, limit=backfill_limit)
    return {"linked": linked, "backfilled": created}
