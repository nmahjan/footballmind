"""Fixture list preview enrichment (no DB)."""

from unittest.mock import MagicMock, patch

from footballmind_services import _fixture_team_resolved, enrich_fixtures_with_previews


def test_fixture_team_resolved_rejects_tbd():
    assert not _fixture_team_resolved("TBD")
    assert not _fixture_team_resolved("TBD (A)")
    assert _fixture_team_resolved("Spain")


def test_enrich_skips_tbd_and_attaches_preview():
    conn = MagicMock()
    fixtures = [
        {"home": "TBD", "away": "France", "stage": "semi_final"},
        {"home": "Spain", "away": "Germany", "stage": "group"},
    ]
    fake = {
        "prediction": "Spain",
        "confidence": 0.54,
        "home_win_prob": 0.54,
        "draw_prob": 0.24,
        "away_win_prob": 0.22,
        "is_knockout": False,
    }
    with patch("footballmind_mcp_predict._predict_match", return_value=fake) as mock_pred:
        enrich_fixtures_with_previews(conn, fixtures, "WC")
        mock_pred.assert_called_once()
    assert "preview" not in fixtures[0]
    assert fixtures[1]["preview"]["prediction"] == "Spain"
