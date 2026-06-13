"""SoFIFA / EA FC profile HTML parsing (no network)."""

from pathlib import Path

from footballmind_sofifa import parse_player_profile_html

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sofifa_player_profile.html"


def test_parse_height_weight_and_feet():
    html = FIXTURE.read_text()
    attrs = parse_player_profile_html(html, sofifa_id=231443)
    assert attrs["name"] == "Lamine Yamal"
    assert attrs["height_cm"] == 180
    assert attrs["weight_kg"] == 72
    assert attrs["preferred_foot"] == "Left"
    assert attrs["weak_foot"] == 3
    assert attrs["skill_moves"] == 3
    assert attrs["overall_rating"] == 89
    assert attrs["potential"] == 95
    assert attrs["work_rate"] == "High/Low"


def test_cloudflare_challenge_detected():
    from footballmind_sofifa import _is_cloudflare_challenge
    assert _is_cloudflare_challenge("<html>Performing security verification</html>")
    assert not _is_cloudflare_challenge(FIXTURE.read_text())
