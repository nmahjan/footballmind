-- Club/national captain flag for lineup weighting (API no longer exposes captain).
ALTER TABLE player_affiliations
    ADD COLUMN IF NOT EXISTS is_captain BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_affiliations_captain
    ON player_affiliations (team_id)
    WHERE is_captain = TRUE AND end_date IS NULL;
