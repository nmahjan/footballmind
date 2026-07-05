-- FootballMind schema (PostgreSQL)
-- Supports club + international football in one model, dual player
-- affiliations (a player belongs to a club AND a country at the same time),
-- and knockout-aware matches (group stage + extra time + penalties).

CREATE EXTENSION IF NOT EXISTS btree_gist;  -- required for the no-overlap constraint below

-- ----------------------------------------------------------------------
-- Reference enums
-- ----------------------------------------------------------------------
CREATE TYPE team_type   AS ENUM ('club', 'national');
CREATE TYPE comp_type   AS ENUM ('domestic_league', 'continental_club', 'international');
CREATE TYPE affil_kind  AS ENUM ('club', 'national');
CREATE TYPE match_stage AS ENUM (
    'regular_season', 'group', 'round_of_32', 'round_of_16',
    'quarter_final', 'semi_final', 'third_place', 'final'
);

-- ----------------------------------------------------------------------
-- Countries
-- ----------------------------------------------------------------------
CREATE TABLE countries (
    id        SERIAL PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    fifa_code CHAR(3) UNIQUE              -- e.g. 'EGY', 'ENG'
);

-- ----------------------------------------------------------------------
-- Teams: BOTH clubs and national sides live here
-- ----------------------------------------------------------------------
CREATE TABLE teams (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    type        team_type NOT NULL,
    country_id  INTEGER REFERENCES countries(id),  -- club's base country, or the nation itself
    external_id TEXT,                               -- football-data.org id, for syncing
    UNIQUE (name, type)
);

-- ----------------------------------------------------------------------
-- Players
-- ----------------------------------------------------------------------
CREATE TABLE players (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    birth_date  DATE,
    nationality INTEGER REFERENCES countries(id),
    external_id TEXT
);

-- ----------------------------------------------------------------------
-- Player affiliations: the dual / temporal link
-- One row per stint. A player normally has ONE open 'club' row and ONE
-- open 'national' row simultaneously -> that is the dual affiliation.
-- ----------------------------------------------------------------------
CREATE TABLE player_affiliations (
    id         SERIAL PRIMARY KEY,
    player_id  INTEGER NOT NULL REFERENCES players(id),
    team_id    INTEGER NOT NULL REFERENCES teams(id),
    kind       affil_kind NOT NULL,        -- 'club' or 'national'
    start_date DATE NOT NULL,
    end_date   DATE,                        -- NULL = current
    CONSTRAINT valid_period CHECK (end_date IS NULL OR end_date >= start_date)
);

-- Prevent two overlapping stints OF THE SAME KIND for one player.
-- A 'club' stint and a 'national' stint CAN overlap (different kind) -- which
-- is exactly the dual affiliation we want. daterange treats a NULL end as
-- unbounded, so open (current) stints are handled correctly.
ALTER TABLE player_affiliations
    ADD CONSTRAINT no_overlapping_same_kind
    EXCLUDE USING gist (
        player_id WITH =,
        kind      WITH =,
        daterange(start_date, end_date) WITH &&
    );

-- Handy view: each player's current club and current nation
CREATE VIEW current_affiliations AS
SELECT pa.player_id, pa.kind, t.id AS team_id, t.name AS team_name, t.type
FROM   player_affiliations pa
JOIN   teams t ON t.id = pa.team_id
WHERE  pa.end_date IS NULL;

-- ----------------------------------------------------------------------
-- Competitions and their editions (seasons / tournaments)
-- ----------------------------------------------------------------------
CREATE TABLE competitions (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,                    -- 'Premier League', 'FIFA World Cup'
    code TEXT UNIQUE,                      -- 'PL', 'WC', 'CL'
    type comp_type NOT NULL
);

CREATE TABLE competition_editions (
    id             SERIAL PRIMARY KEY,
    competition_id INTEGER NOT NULL REFERENCES competitions(id),
    season         TEXT NOT NULL,          -- '2025/26', '2026'
    start_date     DATE,
    end_date       DATE,
    UNIQUE (competition_id, season)
);

-- ----------------------------------------------------------------------
-- Matches (knockout-aware)
-- ----------------------------------------------------------------------
CREATE TABLE matches (
    id                SERIAL PRIMARY KEY,
    edition_id        INTEGER NOT NULL REFERENCES competition_editions(id),
    stage             match_stage NOT NULL DEFAULT 'regular_season',
    match_date        TIMESTAMPTZ,
    home_team_id      INTEGER NOT NULL REFERENCES teams(id),
    away_team_id      INTEGER NOT NULL REFERENCES teams(id),

    -- regulation (90') result, present once played
    home_goals        INTEGER,
    away_goals        INTEGER,

    -- knockout-only resolution
    went_to_et        BOOLEAN NOT NULL DEFAULT FALSE,
    went_to_pens      BOOLEAN NOT NULL DEFAULT FALSE,
    home_pens         INTEGER,
    away_pens         INTEGER,
    advancing_team_id INTEGER REFERENCES teams(id),   -- who progressed (knockout only)

    external_id       TEXT,
    CONSTRAINT teams_differ CHECK (home_team_id <> away_team_id)
);

CREATE INDEX idx_matches_edition ON matches(edition_id);
CREATE INDEX idx_matches_date    ON matches(match_date);

-- ----------------------------------------------------------------------
-- App tables (ported from the SQLite spec; predictions extended for
-- knockout progression -- see the model in footballmind_predict.py)
-- ----------------------------------------------------------------------
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    last_active TIMESTAMPTZ DEFAULT now(),
    query_count INTEGER DEFAULT 0
);

CREATE TABLE queries (
    id                 BIGSERIAL PRIMARY KEY,
    session_id         TEXT REFERENCES sessions(id),
    query              TEXT,
    response           TEXT,
    query_type         TEXT,               -- 'stats' | 'prediction' | 'search' | 'forecast'
    entities_mentioned JSONB,              -- teams / players referenced (Postgres JSONB)
    timestamp          TIMESTAMPTZ DEFAULT now(),
    response_time_ms   INTEGER
);

CREATE TABLE predictions (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          TEXT REFERENCES sessions(id),
    match_id            INTEGER REFERENCES matches(id),

    -- 90-minute outcome distribution (always populated)
    expected_home_goals REAL,
    expected_away_goals REAL,
    home_win_prob       REAL,
    draw_prob           REAL,
    away_win_prob       REAL,

    -- progression (knockout matches only): P(home advances)
    home_advance_prob   REAL,

    confidence          REAL,
    reasoning           TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),

    -- graded after the match is played
    actual_home_goals   INTEGER,
    actual_away_goals   INTEGER,
    was_correct         BOOLEAN
);

CREATE TABLE live_cache (
    key        TEXT PRIMARY KEY,
    data       JSONB,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);
