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
) -> None:
    """Upsert the latest run for a named job (matchday, wikipedia, sync, …)."""
    payload = json.dumps(summary or {})
    with conn.cursor() as cur:
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
