-- Finer tactical role for lineup placement (ST, WING, LB, CDM, …).
-- Populated from SoFIFA sync, manual overrides, and confirmed match lineups.

ALTER TABLE players ADD COLUMN IF NOT EXISTS line_role TEXT;

ALTER TABLE player_eafc_attributes ADD COLUMN IF NOT EXISTS primary_position TEXT;

CREATE INDEX IF NOT EXISTS idx_players_line_role ON players (line_role)
    WHERE line_role IS NOT NULL;
