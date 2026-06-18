-- Per-match box stats (saves, goals conceded) from ESPN / API-Football when available.
CREATE TABLE IF NOT EXISTS match_player_box_stats (
    match_id         INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id        INTEGER NOT NULL REFERENCES players(id),
    saves            INTEGER,
    goals_conceded   INTEGER,
    synced_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_mpbs_player
    ON match_player_box_stats (player_id);
