-- Link predictions to teams for grading when match_id was not set at insert time.
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS home_team_id INTEGER REFERENCES teams(id);
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS away_team_id INTEGER REFERENCES teams(id);

CREATE INDEX IF NOT EXISTS idx_predictions_ungraded
    ON predictions (match_id)
    WHERE was_correct IS NULL;
