-- Player position (from squad sync) and shirt number on affiliations.
ALTER TABLE players ADD COLUMN IF NOT EXISTS position TEXT;
ALTER TABLE player_affiliations ADD COLUMN IF NOT EXISTS shirt_number SMALLINT;

CREATE INDEX IF NOT EXISTS idx_players_name_lower ON players (LOWER(name));
