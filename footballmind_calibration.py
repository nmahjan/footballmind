"""Confidence calibration helpers for live predictions."""

from __future__ import annotations

_CALIBRATION_BINS = [
    (0.34, 0.55, "34–55%"),
    (0.55, 0.65, "55–65%"),
    (0.65, 0.75, "65–75%"),
    (0.75, 0.85, "75–85%"),
    (0.85, 1.001, "85%+"),
]


def _graded_confidence_rows(conn) -> list[tuple[float, bool]]:
    from footballmind_grading import grade_predictions

    grade_predictions(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (p.match_id) "
            "       GREATEST(COALESCE(p.home_win_prob, 0), "
            "                COALESCE(p.draw_prob, 0), "
            "                COALESCE(p.away_win_prob, 0)) AS conf, "
            "       p.was_correct "
            "FROM predictions p "
            "WHERE p.was_correct IS NOT NULL AND p.match_id IS NOT NULL "
            "ORDER BY p.match_id, p.created_at DESC",
        )
        return [(float(r[0]), bool(r[1])) for r in cur.fetchall() if r[0] is not None]


def adjust_confidence_from_calibration(conn, confidence: float) -> tuple[float, float | None]:
    """Nudge confidence halfway toward the bin's historical actual win rate.

    Returns (adjusted_confidence, gap) where gap is actual - expected in the
    matching bin, or None when insufficient graded data.
    """
    if confidence is None:
        return confidence, None
    rows = _graded_confidence_rows(conn)
    if not rows:
        return confidence, None

    buckets = [
        {"min": lo, "max": hi, "count": 0, "correct": 0, "conf_sum": 0.0}
        for lo, hi, _ in _CALIBRATION_BINS
    ]
    for conf, was_correct in rows:
        for b in buckets:
            if b["min"] <= conf < b["max"]:
                b["count"] += 1
                b["conf_sum"] += conf
                if was_correct:
                    b["correct"] += 1
                break

    for b in buckets:
        if b["min"] <= confidence < b["max"] and b["count"] >= 3:
            expected = b["conf_sum"] / b["count"]
            actual = b["correct"] / b["count"]
            gap = actual - expected
            adjusted = max(0.34, min(0.99, confidence + gap * 0.5))
            return round(adjusted, 3), round(gap, 3)
    return confidence, None
