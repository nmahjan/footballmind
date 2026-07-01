"""Wikipedia WC squad parsing (offline fixture)."""

from footballmind_wikipedia import (
    _normalize_wiki_title,
    _store_wiki_provider,
    extract_first_squad_block,
    is_wikipedia_dob_name,
    map_fifa_squad_position,
    parse_fs_player_lines,
    parse_wc_squads_html,
)

# Legacy all-<td> rows (still supported).
SAMPLE = """
<html><body><div class="mw-parser-output">
<h3>Spain</h3>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Player</th><th>Date of birth</th><th>Caps</th><th>Goals</th><th>Club</th></tr>
<tr><td>19</td><td>4 FW</td><td><a href="/wiki/Lamine_Yamal">Lamine Yamal</a></td><td>2007</td><td>25</td><td>6</td><td>Barcelona</td></tr>
<tr><td>16</td><td>3 MF</td><td>Rodri(captain)</td><td>1996</td><td>62</td><td>4</td><td>Manchester City</td></tr>
</table>
</div></body></html>
"""

# Live Wikipedia format: player name in <th scope="row">, DOB in following <td>.
SAMPLE_LIVE = """
<html><body><div class="mw-parser-output">
<h3>France</h3>
<table class="wikitable">
<tr><th>No.</th><th>Pos.</th><th>Player</th><th>Date of birth (age)</th><th>Caps</th><th>Goals</th><th>Club</th></tr>
<tr class="nat-fs-player">
<td>1</td><td>1GK</td>
<th scope="row"><a href="/wiki/Brice_Samba">Brice Samba</a></th>
<td><span class="bday">1994-04-25</span>April 25, 1994 (aged 32)</td>
<td>4</td><td>0</td><td>Rennes</td>
</tr>
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
    assert len(squads) == 1
    spain = squads[0]
    assert spain["team"] == "Spain"
    yamal = next(p for p in spain["players"] if "Yamal" in p["name"])
    assert yamal["name"] == "Lamine Yamal"
    assert yamal["wiki_title"] == "Lamine Yamal"
    assert yamal["line_role"] == "ST"
    assert yamal["caps"] == 25
    rodri = next(p for p in spain["players"] if p["name"] == "Rodri")
    assert rodri["line_role"] == "CM"


def test_parse_wc_squads_html_live_th_player_column():
    squads = parse_wc_squads_html(SAMPLE_LIVE)
    assert len(squads) == 1
    fr = squads[0]["players"][0]
    assert fr["name"] == "Brice Samba"
    assert fr["wiki_title"] == "Brice Samba"
    assert fr["line_role"] == "GK"
    assert fr["caps"] == 4
    assert not is_wikipedia_dob_name(fr["name"])


def test_is_wikipedia_dob_name():
    assert is_wikipedia_dob_name("(1999-12-27)December 27, 1999 (aged 26)")
    assert not is_wikipedia_dob_name("Lamine Yamal")


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


def test_normalize_wiki_title_decodes_percent_encoding():
    raw = "Ladislav Krej%C4%8D%C3%AD (footballer, born 1999)"
    assert _normalize_wiki_title(raw) == "Ladislav Krejčí (footballer, born 1999)"


def test_store_wiki_provider_skips_conflicting_player():
    class _Cur:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql.strip(), params))
            if "SELECT entity_id" in sql:
                self._fetch = [(99,)]
            else:
                self._fetch = []

        def fetchone(self):
            return getattr(self, "_fetch", [None])[0]

    cur = _Cur()
    _store_wiki_provider(cur, 42, "Ladislav Krejčí (footballer, born 1999)")
    inserts = [c for c in cur.calls if c[0].startswith("INSERT")]
    assert inserts == []
