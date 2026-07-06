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
    from footballmind_sofifa import _is_cloudflare_challenge, _read_http_page
    from io import BytesIO

    assert _is_cloudflare_challenge("<html>Performing security verification</html>")
    assert not _is_cloudflare_challenge(FIXTURE.read_text())
    assert _is_cloudflare_challenge(
        _read_http_page(BytesIO(b"<html>Performing security verification</html>"))
    )


def test_parse_sofifa_teams_and_players_html():
    from footballmind_sofifa import _parse_sofifa_players_html, _parse_sofifa_teams_html

    teams_html = """
    <html><body><table><tbody><tr>
      <td></td><td><a href="/team/11/arsenal/">Arsenal</a></td>
    </tr></tbody></table></body></html>
    """
    teams = _parse_sofifa_teams_html(teams_html, "ENG-Premier League")
    assert teams == [{"team_id": 11, "team": "Arsenal", "league": "ENG-Premier League"}]

    squad_html = """
    <html><body><article><table><tr>
      <td></td><td><a href="/player/231443/lamine-yamal/" data-tippy-content="Bukayo Saka">Saka</a></td>
    </tr></table></article></body></html>
    """
    players = _parse_sofifa_players_html(
        squad_html, team_name="Arsenal", league_key="ENG-Premier League",
    )
    assert players[0]["player_id"] == 231443
    assert players[0]["player"] == "Bukayo Saka"


def test_parse_modern_sofifa_layout():
    from footballmind_sofifa import parse_player_profile_html

    modern = """
    <html><body>
    <div class="profile"><h1>Martin Ødegaard</h1></div>
    <p>25y.o. (Dec 17, 1998) 178cm 5'10" 68kg 150lbs</p>
    <div class="col"><em title="89">89</em><div class="sub">Overall rating</div></div>
    <div class="col"><em title="90">90</em><div class="sub">Potential</div></div>
    <p><label>Preferred foot</label> Left</p>
    <p>5 <label>Skill moves</label></p>
    <p>2 <label>Weak foot</label></p>
    <p>Position CAM Attacking Midfielder</p>
    </body></html>
    """
    attrs = parse_player_profile_html(modern, sofifa_id=222665)
    assert attrs["overall_rating"] == 89
    assert attrs["potential"] == 90
    assert attrs["height_cm"] == 178
    assert attrs["weight_kg"] == 68
    assert attrs["preferred_foot"] == "Left"
    assert attrs["skill_moves"] == 5
    assert attrs["weak_foot"] == 2
    assert attrs["primary_position"] == "CAM"
    assert attrs["line_role"] == "CAM"


def test_sofifa_name_matching():
    from footballmind_sofifa import _score_sofifa_db_name

    assert _score_sofifa_db_name("David Raya Martin", "David Raya") >= 95
    assert _score_sofifa_db_name("Martin Ødegaard", "Martin Ødegaard") == 100
    assert _score_sofifa_db_name("Benjamin White", "Ben White") >= 88
    assert _score_sofifa_db_name("Gabriel Teodoro Martinelli Silva", "Martinelli") >= 82
    assert _score_sofifa_db_name("David Raya Martin", "Martin Ødegaard") < 82


def test_parse_cached_odegaard_if_present():
    from pathlib import Path
    from footballmind_sofifa import parse_player_profile_html

    path = Path.home() / "soccerdata/data/SoFIFA/player_222665_250001.html"
    if not path.is_file():
        return
    attrs = parse_player_profile_html(path.read_text(encoding="utf-8", errors="replace"), sofifa_id=222665)
    assert attrs["overall_rating"] is not None
    assert attrs["height_cm"] is not None


def test_fetch_sofifa_page_uses_reader_get_body():
    """Regression: must not read driver.page_source when get() returns cached HTML."""
    from pathlib import Path
    from footballmind_sofifa import _fetch_sofifa_page, _parse_sofifa_teams_html

    cache = Path.home() / "soccerdata/data/SoFIFA/teams_13_250001.html"
    if not cache.is_file():
        return

    class _Reader:
        headless = False
        data_dir = cache.parent
        _driver = type("_D", (), {"page_source": "<html>wrong homepage</html>"})()

        def get(self, url, filepath, no_cache=False):
            return cache.open("rb")

    page = _fetch_sofifa_page(
        _Reader(),
        "https://sofifa.com/teams?lg=13&r=250001&set=true",
        cache,
        headless=True,
        label="test",
        cloudflare_wait_sec=1,
    )
    assert len(_parse_sofifa_teams_html(page, "ENG-Premier League")) >= 18


def test_build_sofifa_reader_respects_visible_mode(monkeypatch):
    """soccerdata SoFIFA drops headless=; we re-init the driver with the flag."""
    import sys
    import types

    from footballmind_sofifa import DEFAULT_SOFIFA_VERSION_R, _build_sofifa_reader

    seen: list[bool] = []

    class FakeSoFIFA:
        def __init__(self, leagues, versions, no_store, headless):  # noqa: ARG002
            # Simulate soccerdata bug: accepts headless= but keeps self.headless True.
            self.headless = True
            self._driver = type("_D", (), {"quit": lambda self: None})()

        def _init_webdriver(self):
            seen.append(self.headless)

            class _Driver:
                def quit(self):
                    return None

            return _Driver()

    fake_sd = types.ModuleType("soccerdata")
    fake_sd.SoFIFA = FakeSoFIFA
    monkeypatch.setitem(sys.modules, "soccerdata", fake_sd)
    monkeypatch.setattr("footballmind_sofifa._patch_sofifa_versions", lambda _vid: None)

    reader = _build_sofifa_reader(
        leagues=["ENG-Premier League"],
        version_id=DEFAULT_SOFIFA_VERSION_R,
        headless=False,
    )
    assert reader.headless is False
    assert seen[-1] is False
