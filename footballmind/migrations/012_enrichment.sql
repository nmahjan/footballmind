-- Multi-source enrichment: provider IDs, match ratings, xG, availability source.

CREATE TABLE IF NOT EXISTS provider_external_ids (
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('player', 'team', 'match')),
    entity_id    INTEGER NOT NULL,
    provider     TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    PRIMARY KEY (provider, external_id),
    UNIQUE (entity_type, entity_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_provider_ids_entity
    ON provider_external_ids (entity_type, entity_id);

CREATE TABLE IF NOT EXISTS match_player_ratings (
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id   INTEGER NOT NULL REFERENCES players(id),
    rating      NUMERIC(4, 2),
    minutes     SMALLINT,
    source      TEXT NOT NULL,
    synced_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (match_id, player_id, source)
);

CREATE INDEX IF NOT EXISTS idx_match_player_ratings_player
    ON match_player_ratings (player_id, synced_at DESC);

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS home_xg NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS away_xg NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS xg_source TEXT;

ALTER TABLE player_availability
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';
