-- Knockout bracket ordering from football-data.org matchday field.
ALTER TABLE matches ADD COLUMN IF NOT EXISTS matchday INTEGER;
