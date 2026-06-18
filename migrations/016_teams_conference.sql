-- MLS (and other comps) store conference for playoff zone logic.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS conference TEXT;

CREATE INDEX IF NOT EXISTS idx_teams_conference
    ON teams (conference)
    WHERE conference IS NOT NULL;
