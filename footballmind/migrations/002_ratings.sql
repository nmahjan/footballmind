-- FootballMind -- team strength ratings (Elo). Run after footballmind_schema.sql.
-- Because clubs only play clubs and nations only play nations, club and
-- international ratings never mix -- the "separate ladders" property is free.

CREATE TABLE team_ratings (
    team_id    INTEGER PRIMARY KEY REFERENCES teams(id),
    rating     REAL NOT NULL DEFAULT 1500,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Append-only log -> point-in-time ratings for honest backtesting:
-- look up a team's rating AS OF a match date, with no lookahead leakage.
CREATE TABLE rating_history (
    id            BIGSERIAL PRIMARY KEY,
    team_id       INTEGER NOT NULL REFERENCES teams(id),
    match_id      INTEGER REFERENCES matches(id),
    rating_before REAL NOT NULL,
    rating_after  REAL NOT NULL,
    as_of         TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_rating_history_team ON rating_history(team_id, as_of);
