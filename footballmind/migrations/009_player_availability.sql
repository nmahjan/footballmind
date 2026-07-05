-- Manual injury/doubt flags (suspensions derived from match_events at runtime).
CREATE TABLE player_availability (
    player_id   INTEGER NOT NULL REFERENCES players(id),
    team_id     INTEGER NOT NULL REFERENCES teams(id),
    comp_code   TEXT NOT NULL DEFAULT 'WC',
    status      TEXT NOT NULL CHECK (status IN ('injured', 'doubtful', 'suspended')),
    reason      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, team_id, comp_code)
);

CREATE INDEX IF NOT EXISTS idx_player_availability_team
    ON player_availability (team_id, comp_code);
