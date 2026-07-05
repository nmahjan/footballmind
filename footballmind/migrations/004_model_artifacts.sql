-- Deployed model storage (written by footballmind_production.train_and_store,
-- read by footballmind_production.load_hybrid). The artifact is plain JSONB --
-- no pickle, inspectable in the database.

CREATE TABLE model_artifacts (
    name             TEXT PRIMARY KEY,      -- 'production_club' / 'production_international'
    artifact         JSONB NOT NULL,
    half_life_days   INTEGER,
    full_credibility INTEGER,
    backtest_rps     REAL,
    trained_at       TIMESTAMPTZ DEFAULT now()
);
