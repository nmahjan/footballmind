-- EA FC / SoFIFA player attributes (height, weak foot, overall, etc.)
-- Populated by footballmind_sofifa.py sync (optional job — requires soccerdata + Chrome).

CREATE TABLE IF NOT EXISTS player_eafc_attributes (
    player_id       INTEGER PRIMARY KEY REFERENCES players(id),
    sofifa_id       INTEGER,
    height_cm       SMALLINT,
    weight_kg       SMALLINT,
    preferred_foot  TEXT,
    weak_foot       SMALLINT CHECK (weak_foot IS NULL OR weak_foot BETWEEN 1 AND 5),
    overall_rating  SMALLINT,
    potential       SMALLINT,
    skill_moves     SMALLINT CHECK (skill_moves IS NULL OR skill_moves BETWEEN 1 AND 5),
    work_rate       TEXT,
    fifa_edition    TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_player_eafc_sofifa_id
    ON player_eafc_attributes (sofifa_id);
