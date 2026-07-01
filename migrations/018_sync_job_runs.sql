-- Latest outcome per scheduled sync job (for /api/sync-health).
CREATE TABLE IF NOT EXISTS sync_job_runs (
    job_name    TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    summary     JSONB NOT NULL DEFAULT '{}',
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
