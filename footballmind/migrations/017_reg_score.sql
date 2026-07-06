-- Regulation (90') score for display when a knockout goes to penalties.
ALTER TABLE matches ADD COLUMN IF NOT EXISTS reg_home_goals INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS reg_away_goals INTEGER;
