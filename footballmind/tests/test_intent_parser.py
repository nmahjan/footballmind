"""Unit tests for chat intent parsing (pure logic, no DB)."""

import pytest

from footballmind_app import (
    _comp_switch_compare,
    _extract_venue,
    _is_followup,
    _last_compare_from_history,
    _parse_player_compare,
    _resolve_prediction_venue,
    parse_intent,
)
from footballmind_services import parse_comp_from_text


# ---------------------------------------------------------------------------
# parse_intent
# ---------------------------------------------------------------------------
class TestParseIntent:
    def test_standings_table(self):
        assert parse_intent("Show me the PL table") == {"type": "standings"}

    def test_standings_league_position(self):
        assert parse_intent("What's Liverpool's league position?") == {"type": "standings"}

    def test_predict_vs(self):
        r = parse_intent("Predict Mexico vs USA")
        assert r["type"] == "predict"
        assert r["home"] == "Mexico"
        assert r["away"] == "USA"
        assert r["venue"] is None

    def test_predict_who_will_win(self):
        r = parse_intent("Who will win England vs France?")
        assert r["type"] == "predict"
        assert r["home"] == "England"
        assert r["away"] == "France"

    def test_predict_with_venue(self):
        r = parse_intent("Predict Mexico vs USA in Mexico City")
        assert r["type"] == "predict"
        assert r["home"] == "Mexico"
        assert r["away"] == "USA"
        assert r["venue"] == "Mexico City"

    def test_predict_knockout_stage(self):
        r = parse_intent("Predict Netherlands vs Morocco in the round of 32")
        assert r["type"] == "predict"
        assert r["stage"] == "round_of_32"

    def test_bracket_intent(self):
        assert parse_intent("Show World Cup knockout bracket") == {"type": "bracket"}

    def test_compare_players(self):
        r = parse_intent("Compare Messi vs Ronaldo")
        assert r == {"type": "compare", "player_a": "Messi", "player_b": "Ronaldo"}

    def test_compare_teams_with_compare_keyword(self):
        r = parse_intent("Compare Arsenal vs Chelsea")
        assert r["type"] == "compare"
        assert r["player_a"] == "Arsenal"
        assert r["player_b"] == "Chelsea"

    def test_unknown(self):
        assert parse_intent("What's the weather in London?") == {"type": "unknown"}


# ---------------------------------------------------------------------------
# _parse_player_compare
# ---------------------------------------------------------------------------
class TestParsePlayerCompare:
    def test_compare_vs(self):
        assert _parse_player_compare("Compare Messi vs Ronaldo") == ("Messi", "Ronaldo")

    def test_who_is_better(self):
        assert _parse_player_compare("Who is better, Haaland or Mbappe") == (
            "Haaland", "Mbappe")

    def test_player_or(self):
        assert _parse_player_compare("Messi or Ronaldo") == ("Messi", "Ronaldo")

    def test_rejects_passing_followup_with_or(self):
        assert _parse_player_compare(
            "What about their passing, is it a good completion rate or is it something else?"
        ) is None

    def test_rejects_predict_queries(self):
        assert _parse_player_compare("Predict Mexico vs USA") is None

    def test_rejects_unrelated(self):
        assert _parse_player_compare("Top scorers in the Premier League") is None


# ---------------------------------------------------------------------------
# _is_followup
# ---------------------------------------------------------------------------
class TestIsFollowup:
    _hist = [{"query": "Predict Mexico vs USA", "response": "..."}]

    def test_no_history(self):
        assert _is_followup("explain", []) is False

    def test_short_ack(self):
        assert _is_followup("why?", self._hist) is True
        assert _is_followup("more", self._hist) is True
        assert _is_followup("explain", self._hist) is True

    def test_phrase_followup(self):
        assert _is_followup("Tell me more", self._hist) is True
        assert _is_followup("Break that down", self._hist) is True
        assert _is_followup("Expand on that", self._hist) is True

    def test_new_query_not_followup(self):
        assert _is_followup("Predict England vs France", self._hist) is False


# ---------------------------------------------------------------------------
# Competition switch follow-ups
# ---------------------------------------------------------------------------
class TestCompSwitch:
    _hist = [
        {"role": "user", "content": "Compare Messi vs Ronaldo"},
        {"role": "assistant", "content": "..."},
    ]

    def test_parse_la_liga(self):
        assert parse_comp_from_text("what about in la liga") == "PD"

    def test_comp_switch_after_compare(self):
        assert _comp_switch_compare("what about in la liga", self._hist) == "PD"

    def test_no_switch_without_history(self):
        assert _comp_switch_compare("what about in la liga", []) is None

    def test_last_compare_from_history(self):
        assert _last_compare_from_history(self._hist) == ("Messi", "Ronaldo")


# ---------------------------------------------------------------------------
# Venue parsing
# ---------------------------------------------------------------------------
class TestVenueParsing:
    def test_extract_venue(self):
        base, venue = _extract_venue("Predict Mexico vs USA in Mexico City")
        assert "Mexico" in base and "USA" in base
        assert venue == "Mexico City"

    def test_no_venue(self):
        base, venue = _extract_venue("Predict Mexico vs USA")
        assert venue is None

    def test_host_city_sets_home(self):
        home, away, neutral, label = _resolve_prediction_venue(
            "Mexico", "USA", "Mexico City", None,
            "Predict Mexico vs USA in Mexico City")
        assert home == "Mexico"
        assert away == "USA"
        assert neutral is False
        assert label == "Mexico City"

    def test_explicit_neutral_from_ui(self):
        home, away, neutral, label = _resolve_prediction_venue(
            "Mexico", "USA", None, True, "Predict Mexico vs USA")
        assert neutral is True
        assert label is None

    def test_neutral_phrase_in_message(self):
        home, away, neutral, label = _resolve_prediction_venue(
            "Mexico", "USA", None, None,
            "Predict Mexico vs USA at a neutral venue")
        assert neutral is True

    def test_flip_when_second_team_hosts(self):
        home, away, neutral, label = _resolve_prediction_venue(
            "USA", "Mexico", "Mexico City", None,
            "Predict USA vs Mexico in Mexico City")
        assert home == "Mexico"
        assert away == "USA"
        assert neutral is False
