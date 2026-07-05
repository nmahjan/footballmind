"""Record and query scheduled sync job outcomes for the admin health panel."""

from __future__ import annotations

import json
from typing import Any


def record_sync_run(
    conn,
    job_name: str,
    *,
    status: str,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upsert the latest run for a named job (matchday, wikipedia, sync, …)."""
    summary = dict(summary or {})
    with conn.cursor() as cur:
        cur.execute(
            "SELECT summary FROM sync_job_runs WHERE job_name = %s",
            (job_name,),
        )
        prev = cur.fetchone()
        repeat = _repeat_skips(prev[0] if prev else {}, summary)
        if repeat:
            summary["repeat_skips"] = repeat
            summary["alert"] = (
                f"Skipped in 2 consecutive runs: {', '.join(repeat)}"
            )
        payload = json.dumps(summary)
        cur.execute(
            "INSERT INTO sync_job_runs (job_name, status, summary, finished_at) "
            "VALUES (%s, %s, %s::jsonb, now()) "
            "ON CONFLICT (job_name) DO UPDATE SET "
            "  status = EXCLUDED.status, "
            "  summary = EXCLUDED.summary, "
            "  finished_at = EXCLUDED.finished_at",
            (job_name, status, payload),
        )
    conn.commit()
    return summary


def _collect_skips(block: dict[str, Any]) -> set[str]:
    skips: set[str] = set()
    if not isinstance(block, dict):
        return skips
    for key in ("skipped_teams", "skipped_clubs"):
        for name in block.get(key) or []:
            if name:
                skips.add(str(name))
    return skips


def _repeat_skips(prev_summary: dict[str, Any], new_summary: dict[str, Any]) -> list[str]:
    """Clubs/teams skipped in both the previous and current run."""
    prev = set()
    new = set()
    for block in (prev_summary or {}).values():
        if isinstance(block, dict):
            prev |= _collect_skips(block)
    for block in (new_summary or {}).values():
        if isinstance(block, dict):
            new |= _collect_skips(block)
    return sorted(prev & new)


def get_sync_health(conn) -> dict[str, Any]:
    """Latest job runs plus coarse data freshness signals."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT job_name, status, summary, finished_at "
            "FROM sync_job_runs ORDER BY finished_at DESC NULLS LAST",
        )
        jobs = [
            {
                "job": row[0],
                "status": row[1],
                "summary": row[2] or {},
                "finished_at": row[3].isoformat() if row[3] else None,
            }
            for row in cur.fetchall()
        ]
        cur.execute(
            "SELECT max(m.match_date) FROM matches m "
            "WHERE m.home_goals IS NOT NULL",
        )
        last_result = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM players WHERE line_role IS NOT NULL",
        )
        players_with_roles = cur.fetchone()[0]
    return {
        "jobs": jobs,
        "last_result_at": last_result.isoformat() if last_result else None,
        "players_with_roles": players_with_roles,
    }
