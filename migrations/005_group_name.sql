-- Migration 005: add group_name to matches for tournament group stage tracking
ALTER TABLE matches ADD COLUMN IF NOT EXISTS group_name TEXT;
