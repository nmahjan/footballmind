"""Wikipedia WC squad parsing (offline fixture)."""

from footballmind_wikipedia import (
    extract_first_squad_block,
    map_fifa_squad_position,
    parse_fs_player_lines,
    parse_wc_squads_html,
)

# Mirrors live Wikipedia: content nested in div.mw-parser-output, plain h3 (no mw-headline).
SAMPLE = """
<html><body><div class="mw-parser-output">
<h3>Spain</h3>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Player</th><th>Date of birth</th><th>Caps</th><th>Goals</th><th>Club</th></tr>
<tr><td>19</td><td>4 FW</td><td><a href="/wiki/Lamine_Yamal">Lamine Yamal</a></td><td>2007</td><td>25</td><td>6</td><td>Barcelona</td></tr>
<tr><td>16</td><td>3 MF</td><td>Rodri(captain)</td><td>1996</td><td>62</td><td>4</td><td>Manchester City</td></tr>
</table>
<h3>Cape Verde</h3>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Player</th><th>Date of birth</th><th>Caps</th><th>Goals</th><th>Club</th></tr>
<tr><td>10</td><td>4 FW</td><td>Unknown Player</td><td>1990</td><td>1</td><td>0</td><td>Club</td></tr>
</table>
</div></body></html>
"""


def test_map_fifa_squad_position():
    assert map_fifa_squad_position("1 GK") == "GK"
    assert map_fifa_squad_position("2 DF") == "CB"
    assert map_fifa_squad_position("3 MF") == "CM"
    assert map_fifa_squad_position("4 FW") == "ST"


def test_parse_wc_squads_html():
    squads = parse_wc_squads_html(SAMPLE)
    assert len(squads) == 2
    spain = next(s for s in squads if s["team"] == "Spain")
    yamal = next(p for p in spain["players"] if "Yamal" in p["name"])
    assert yamal["name"] == "Lamine Yamal"
    assert yamal["wiki_title"] == "Lamine Yamal"
    assert yamal["line_role"] == "ST"
    assert yamal["caps"] == 25
    rodri = next(p for p in spain["players"] if p["name"] == "Rodri")
    assert rodri["line_role"] == "CM"


CLUB_WIKITEXT = """
=== First-team squad ===
{{Fs start}}
{{fs player|no=1|nat=ESP|pos=GK|name=[[Jordan Pickford]]}}
{{fs player|no=9|nat=SWE|pos=FW|name=[[Viktor Gyökeres]]}}
{{Fs end}}
=== Academy ===
{{Fs start}}
{{fs player|no=99|pos=FW|name=[[Youth Only]]}}
{{Fs end}}
"""


def test_extract_first_squad_block():
    block = extract_first_squad_block(CLUB_WIKITEXT)
    assert "Youth Only" not in block
    players = parse_fs_player_lines(block)
    assert len(players) == 2
    assert players[0]["name"] == "Jordan Pickford"
    assert players[0]["line_role"] == "GK"
    assert players[1]["name"] == "Viktor Gyökeres"
    assert players[1]["line_role"] == "ST"
