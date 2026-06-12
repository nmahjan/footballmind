-- One open (ungraded) prediction per session per fixture.
-- Re-asking "Predict Mexico vs USA" updates the existing row instead of inserting again.

-- Drop older duplicate open rows (keep newest per session + fixture).
DELETE FROM predictions p1
USING predictions p2
WHERE p1.id < p2.id
  AND p1.session_id IS NOT DISTINCT FROM p2.session_id
  AND p1.match_id = p2.match_id
  AND p1.match_id IS NOT NULL
  AND p1.was_correct IS NULL
  AND p2.was_correct IS NULL;

DELETE FROM predictions p1
USING predictions p2
WHERE p1.id < p2.id
  AND p1.session_id IS NOT DISTINCT FROM p2.session_id
  AND p1.home_team_id = p2.home_team_id
  AND p1.away_team_id = p2.away_team_id
  AND p1.match_id IS NULL
  AND p2.match_id IS NULL
  AND p1.home_team_id IS NOT NULL
  AND p1.away_team_id IS NOT NULL
  AND p1.was_correct IS NULL
  AND p2.was_correct IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_session_match_open
    ON predictions (session_id, match_id)
    WHERE was_correct IS NULL AND match_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_session_teams_open
    ON predictions (session_id, home_team_id, away_team_id)
    WHERE was_correct IS NULL AND match_id IS NULL
      AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL;
