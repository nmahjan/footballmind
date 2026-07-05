-- Partial unique indexes required by the sync job's idempotent upserts
-- (footballmind_sync.py uses ON CONFLICT (external_id) WHERE external_id IS NOT NULL).

CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_external
    ON matches(external_id) WHERE external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_players_external
    ON players(external_id) WHERE external_id IS NOT NULL;
