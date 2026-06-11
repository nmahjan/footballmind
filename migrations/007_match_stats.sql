-- Player competition stats (from /competitions/{code}/scorers sync).
CREATE TABLE player_edition_stats (
    player_id    INTEGER NOT NULL REFERENCES players(id),
    edition_id   INTEGER NOT NULL REFERENCES competition_editions(id),
    team_id      INTEGER REFERENCES teams(id),
    goals        INTEGER NOT NULL DEFAULT 0,
    assists      INTEGER NOT NULL DEFAULT 0,
    appearances  INTEGER NOT NULL DEFAULT 0,
    penalties    INTEGER NOT NULL DEFAULT 0,
    synced_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, edition_id)
);

CREATE INDEX IF NOT EXISTS idx_pes_edition_goals
    ON player_edition_stats (edition_id, goals DESC);

-- Per-match events (goals, cards) when match detail API provides them.
CREATE TYPE match_event_type AS ENUM (
    'GOAL', 'OWN_GOAL', 'PENALTY', 'YELLOW_CARD', 'RED_CARD', 'SUBSTITUTION'
);

CREATE TABLE match_events (
    id               SERIAL PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id          INTEGER REFERENCES teams(id),
    player_id        INTEGER REFERENCES players(id),
    assist_player_id INTEGER REFERENCES players(id),
    event_type       match_event_type NOT NULL,
    minute           INTEGER,
    detail           TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_match_events_dedup
    ON match_events (match_id, event_type, COALESCE(player_id, 0), COALESCE(minute, -1));

-- Formations + lineups (populated when API tier returns lineup data).
CREATE TABLE match_team_lineups (
    match_id   INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id    INTEGER NOT NULL REFERENCES teams(id),
    formation  TEXT,
    PRIMARY KEY (match_id, team_id)
);

CREATE TABLE match_lineup_players (
    match_id      INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id       INTEGER NOT NULL REFERENCES teams(id),
    player_id     INTEGER NOT NULL REFERENCES players(id),
    role          TEXT NOT NULL DEFAULT 'starter',
    shirt_number  SMALLINT,
    position      TEXT,
    PRIMARY KEY (match_id, team_id, player_id)
);

ALTER TABLE matches ADD COLUMN IF NOT EXISTS details_synced BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_matches_details_pending
    ON matches (match_date DESC)
    WHERE home_goals IS NOT NULL AND details_synced = FALSE;
