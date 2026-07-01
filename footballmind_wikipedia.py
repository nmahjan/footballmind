"""
FootballMind — Wikipedia squad enrichment (no API key, no height).

Two sources:
  • WC national squads — HTML tables on e.g. 2026_FIFA_World_Cup_squads
  • Club squads — wikitext {{fs player}} templates (Premier League first)

Creates missing national-team players (Saudi, MLS, lower leagues, etc.) when
they are not already in the DB from football-data.org league syncs.
"""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import date
from typing import Any
from urllib.parse import unquote

import requests
from lxml import html

from footballmind_roles import LINE_ROLES, resolve_player_line_role

WIKI_API = "https://en.wikipedia.org/w/api.php"
DEFAULT_WC_SQUADS_PAGE = "2026_FIFA_World_Cup_squads"
USER_AGENT = (
    "FootballMind/1.0 "
    "(https://github.com/nmahjan/footballmind; football squad enrichment)"
)

# Wikipedia section titles → football-data.org team names in our DB
WIKI_TEAM_TO_DB: dict[str, str] = {
    "Czech Republic": "Czechia",
    "Cape Verde": "Cape Verde Islands",
    "DR Congo": "Congo DR",
    "Democratic Republic of the Congo": "Congo DR",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "United States": "United States",
    "South Korea": "South Korea",
    "Ivory Coast": "Ivory Coast",
    "Curaçao": "Curaçao",
}

# Wikipedia page title → football-data.org club name in our DB
PREMIER_LEAGUE_WIKI_TO_DB: dict[str, str] = {
    "Arsenal F.C.": "Arsenal FC",
    "Aston Villa F.C.": "Aston Villa FC",
    "Bournemouth A.F.C.": "AFC Bournemouth",
    "Brentford F.C.": "Brentford FC",
    "Brighton & Hove Albion F.C.": "Brighton & Hove Albion FC",
    "Burnley F.C.": "Burnley FC",
    "Chelsea F.C.": "Chelsea FC",
    "Crystal Palace F.C.": "Crystal Palace FC",
    "Everton F.C.": "Everton FC",
    "Fulham F.C.": "Fulham FC",
    "Leeds United F.C.": "Leeds United FC",
    "Liverpool F.C.": "Liverpool FC",
    "Manchester City F.C.": "Manchester City FC",
    "Manchester United F.C.": "Manchester United FC",
    "Newcastle United F.C.": "Newcastle United FC",
    "Nottingham Forest F.C.": "Nottingham Forest FC",
    "Sunderland A.F.C.": "Sunderland AFC",
    "Tottenham Hotspur F.C.": "Tottenham Hotspur FC",
    "West Ham United F.C.": "West Ham United FC",
    "Wolverhampton Wanderers F.C.": "Wolverhampton Wanderers FC",
}

LEAGUE_CLUB_WIKI_PAGES: dict[str, dict[str, str]] = {
    "PL": PREMIER_LEAGUE_WIKI_TO_DB,
}

# FIFA squad list position codes (Wikipedia mirrors FIFA)
_FIFA_POS_MAP: dict[str, str] = {
    "GK": "GK",
    "DF": "CB",
    "MF": "CM",
    "FW": "ST",
}

_COARSE_POS: dict[str, str] = {
    "GK": "GK",
    "DF": "DEF",
    "MF": "MID",
    "FW": "FWD",
}

# Common FIFA 3-letter codes on Wikipedia squad templates
FIFA_NAT_NAMES: dict[str, str] = {
    "ENG": "England",
    "ESP": "Spain",
    "FRA": "France",
    "GER": "Germany",
    "ITA": "Italy",
    "POR": "Portugal",
    "NED": "Netherlands",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "USA": "United States",
    "MEX": "Mexico",
    "JPN": "Japan",
    "KOR": "South Korea",
    "SAU": "Saudi Arabia",
    "QAT": "Qatar",
    "UAE": "United Arab Emirates",
    "SCO": "Scotland",
    "WAL": "Wales",
    "NIR": "Northern Ireland",
    "IRL": "Republic of Ireland",
    "CIV": "Ivory Coast",
    "CMR": "Cameroon",
    "SEN": "Senegal",
    "MAR": "Morocco",
    "EGY": "Egypt",
    "NGA": "Nigeria",
    "GHA": "Ghana",
    "RSA": "South Africa",
    "AUS": "Australia",
    "NZL": "New Zealand",
    "CAN": "Canada",
    "COL": "Colombia",
    "URU": "Uruguay",
    "CHI": "Chile",
    "PER": "Peru",
    "ECU": "Ecuador",
    "PAR": "Paraguay",
    "VEN": "Venezuela",
    "BEL": "Belgium",
    "SUI": "Switzerland",
    "AUT": "Austria",
    "POL": "Poland",
    "CZE": "Czechia",
    "SVK": "Slovakia",
    "HUN": "Hungary",
    "ROU": "Romania",
    "SRB": "Serbia",
    "CRO": "Croatia",
    "UKR": "Ukraine",
    "TUR": "Turkey",
    "GRE": "Greece",
    "DEN": "Denmark",
    "SWE": "Sweden",
    "NOR": "Norway",
    "FIN": "Finland",
    "ISL": "Iceland",
    "RUS": "Russia",
    "CHN": "China",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "UZB": "Uzbekistan",
    "IDN": "Indonesia",
    "THA": "Thailand",
    "VIE": "Vietnam",
    "ALG": "Algeria",
    "TUN": "Tunisia",
    "MLI": "Mali",
    "BFA": "Burkina Faso",
    "CPV": "Cape Verde",
    "COD": "Congo DR",
    "ZAF": "South Africa",
}


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def map_fifa_squad_position(raw: str | None) -> str | None:
    """Map Wikipedia/FIFA squad cell like '2 DF' or '4 FW' to line_role."""
    if not raw:
        return None
    text = raw.strip().upper()
    m = re.search(r"(GK|DF|MF|FW)", text)
    if not m:
        return None
    role = _FIFA_POS_MAP.get(m.group(1))
    return role if role in LINE_ROLES else None


def _coarse_position(pos_code: str | None) -> str | None:
    if not pos_code:
        return None
    return _COARSE_POS.get(pos_code.strip().upper())


def _country_from_fifa(code: str | None) -> str | None:
    if not code:
        return None
    return FIFA_NAT_NAMES.get(code.strip().upper(), code.strip().upper())


def is_wikipedia_dob_name(name: str | None) -> bool:
    """True when a squad row was misparsed and DOB text landed in the name field."""
    if not name:
        return False
    text = name.strip()
    return bool(re.match(r"^\(\d{4}-\d{2}-\d{2}\)", text)) or " (aged " in text


def _clean_player_name(raw: str) -> str:
    text = re.sub(r"\(captain\)", "", raw, flags=re.I)
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _map_wc_squad_columns(header: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    for i, raw in enumerate(header):
        h = raw.lower().strip()
        if h.startswith("no") or h == "#":
            cols["no"] = i
        elif "pos" in h:
            cols["pos"] = i
        elif "player" in h:
            cols["player"] = i
        elif "birth" in h or "date of birth" in h:
            cols["dob"] = i
        elif "cap" in h:
            cols["caps"] = i
        elif "goal" in h:
            cols["goals"] = i
        elif "club" in h:
            cols["club"] = i
    return cols


def _normalize_wiki_title(title: str | None) -> str | None:
    if not title:
        return None
    return unquote(title.replace("_", " ")).strip() or None


def _player_name_from_cell(cell) -> tuple[str, str | None]:
    """Return (display name, Wikipedia page title if linked)."""
    link = cell.xpath(".//a[starts-with(@href, '/wiki/') and not(contains(@href, ':'))]")
    if link:
        href = link[0].get("href") or ""
        title = _normalize_wiki_title(href.split("/wiki/", 1)[-1])
        name = link[0].text_content().strip() or title
        return _clean_player_name(name), title
    return _clean_player_name(cell.text_content()), None


def fetch_wikipedia_html(page_title: str) -> str:
    r = requests.get(
        WIKI_API,
        params={
            "action": "parse",
            "page": page_title,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(payload["error"].get("info") or "Wikipedia API error")
    return payload["parse"]["text"]


def fetch_wikitext(page_title: str) -> str:
    """Fetch raw wikitext for a Wikipedia page."""
    r = requests.get(
        WIKI_API,
        params={
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(payload["error"].get("info") or "Wikipedia API error")
    return payload["parse"]["wikitext"]["*"]


def extract_first_squad_block(wikitext: str) -> str:
    """
    Return only the first {{fs start}}…{{fs end}} block (first-team squad).
    Avoids academy / loan lists that appear later on the same page.
    """
    start_match = re.search(
        r"\{\{\s*(?:fs start|football squad start)\b", wikitext, re.IGNORECASE
    )
    if start_match:
        tail = wikitext[start_match.start():]
        end_match = re.search(
            r"\{\{\s*(?:fs end|football squad end)\b", tail, re.IGNORECASE
        )
        if end_match:
            return tail[: end_match.end()]

    headings = [
        r"===?\s*Current squad\s*===?",
        r"===?\s*First-team squad\s*===?",
        r"===?\s*Squad\s*===?",
    ]
    for pattern in headings:
        match = re.search(pattern, wikitext, re.IGNORECASE)
        if not match:
            continue
        rest = wikitext[match.end():]
        next_heading = re.search(r"\n===[^=]", rest)
        section = rest[: next_heading.start()] if next_heading else rest
        inner_start = re.search(
            r"\{\{\s*(?:fs start|football squad start)\b", section, re.IGNORECASE
        )
        if inner_start:
            inner_tail = section[inner_start.start():]
            inner_end = re.search(
                r"\{\{\s*(?:fs end|football squad end)\b", inner_tail, re.IGNORECASE
            )
            if inner_end:
                return inner_tail[: inner_end.end()]
        if "{{fs player" in section.lower():
            return section
    return ""


def parse_fs_player_lines(section_text: str) -> list[dict[str, Any]]:
    """
    Parse {{fs player|...}} / {{Football squad player|...}} template lines.
    Returns pos_code, line_role, coarse position, shirt number, name, nat code.
    """
    players: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\{\{\s*(?:fs player|football squad player)\s*\|(.*?)\}\}",
        re.DOTALL | re.IGNORECASE,
    )
    for block in pattern.findall(section_text):
        fields: dict[str, str] = {}
        for part in block.split("|"):
            if "=" in part:
                key, _, val = part.partition("=")
                fields[key.strip().lower()] = val.strip()

        name_raw = fields.get("name", "")
        name_match = re.search(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", name_raw)
        name = name_match.group(1) if name_match else name_raw.strip()
        if not name:
            continue

        pos_code = fields.get("pos", "").upper()
        shirt_raw = re.sub(r"[^\d]", "", fields.get("no", "") or "")
        shirt = int(shirt_raw) if shirt_raw else None

        players.append({
            "name": name,
            "wiki_title": None,
            "pos_code": pos_code,
            "line_role": map_fifa_squad_position(pos_code),
            "position": _coarse_position(pos_code),
            "shirt_number": shirt,
            "nationality_code": fields.get("nat", "").upper() or None,
            "caps": None,
            "goals": None,
            "club": None,
        })
    return players


_SKIP_SECTIONS = frozenset({
    "Player representation by club",
    "Player representation by league system",
    "Player representation by club confederation",
    "Average age of squads",
    "Coach representation by country",
    "Most common names",
    "Age",
})


def parse_wc_squads_html(page_html: str) -> list[dict[str, Any]]:
    """Parse squad tables grouped by national team from a WC squads page."""
    tree = html.fromstring(page_html)
    squads: list[dict[str, Any]] = []
    current_team: str | None = None

    for elem in tree.iter("h3", "table"):
        if elem.tag == "h3":
            headline = elem.xpath("string(.//span[@class='mw-headline'])").strip()
            if not headline:
                headline = elem.text_content().strip()
            if headline and headline not in _SKIP_SECTIONS:
                current_team = headline
            continue
        if not current_team or current_team in _SKIP_SECTIONS:
            continue
        classes = elem.get("class") or ""
        if "wikitable" not in classes:
            continue

        rows = elem.xpath(".//tr")
        if len(rows) < 2:
            continue
        header = [c.text_content().strip() for c in rows[0].xpath("th|td")]
        header_text = " ".join(h.lower() for h in header)
        if "player" not in header_text or "pos" not in header_text:
            continue
        cols = _map_wc_squad_columns(header)

        def _cell_text(cells, key: str, default: int) -> str:
            idx = cols.get(key, default)
            if idx >= len(cells):
                return ""
            return cells[idx].text_content().strip()

        players: list[dict[str, Any]] = []
        for row in rows[1:]:
            # Live Wikipedia uses <th scope="row"> for the player name column.
            cells = row.xpath("./td|./th")
            if len(cells) < 4:
                continue
            try:
                player_idx = cols.get("player", 2)
                name, wiki_title = _player_name_from_cell(cells[player_idx])
                pos_raw = _cell_text(cells, "pos", 1)
                caps = int(re.sub(r"[^\d]", "", _cell_text(cells, "caps", 4) or "0") or 0)
                goals = int(re.sub(r"[^\d]", "", _cell_text(cells, "goals", 5) or "0") or 0)
                club = _cell_text(cells, "club", 6) or None
                shirt = int(re.sub(r"[^\d]", "", _cell_text(cells, "no", 0) or "0") or 0)
            except (ValueError, IndexError):
                continue
            if not name or is_wikipedia_dob_name(name):
                continue
            pos_code = None
            m = re.search(r"\b(GK|DF|MF|FW)\b", (pos_raw or "").upper())
            if m:
                pos_code = m.group(1)
            players.append({
                "name": name,
                "wiki_title": wiki_title,
                "pos_code": pos_code,
                "position_raw": pos_raw,
                "line_role": map_fifa_squad_position(pos_raw),
                "position": _coarse_position(pos_code),
                "shirt_number": shirt or None,
                "caps": caps,
                "goals": goals,
                "club": club,
                "nationality_code": None,
            })
        if players:
            squads.append({"team": current_team, "players": players})
            current_team = None
    return squads


def _resolve_db_team(cur, wiki_team: str) -> str | None:
    db_name = WIKI_TEAM_TO_DB.get(wiki_team, wiki_team)
    from footballmind_mcp_predict import _resolve_team

    try:
        _resolve_team(cur, db_name)
        return db_name
    except ValueError:
        return None


def _resolve_player_on_team(cur, team_id: int, name: str) -> int | None:
    from footballmind_services import _resolve_player_on_team

    found = _resolve_player_on_team(cur, name, team_id)
    return found[0] if found else None


def _resolve_wikipedia_player_on_team(
    cur,
    team_id: int,
    name: str,
    shirt_number: int | None,
    stats: dict[str, Any],
) -> int | None:
    """Match by name; repair rows where an old parse stored DOB text as the name."""
    pid = _resolve_player_on_team(cur, team_id, name)
    if pid:
        return pid

    if shirt_number:
        cur.execute(
            "SELECT p.id FROM players p "
            "JOIN player_affiliations pa ON pa.player_id = p.id "
            "WHERE pa.team_id = %s AND pa.end_date IS NULL AND pa.kind = 'national' "
            "  AND pa.shirt_number = %s "
            "  AND (p.name ~ '^\\([0-9]{4}-[0-9]{2}-[0-9]{2}\\)' "
            "       OR p.name LIKE '%%(aged %%') "
            "LIMIT 1",
            (team_id, shirt_number),
        )
        row = cur.fetchone()
        if row:
            pid = row[0]
            cur.execute("UPDATE players SET name = %s WHERE id = %s", (name, pid))
            stats["repaired_names"] = stats.get("repaired_names", 0) + 1
            return pid
    return None


def _ensure_affiliation(
    cur,
    player_id: int,
    team_id: int,
    kind: str,
    shirt_number: int | None = None,
) -> None:
    today = date.today()
    cur.execute(
        "SELECT id, team_id FROM player_affiliations "
        "WHERE player_id = %s AND kind = %s AND end_date IS NULL",
        (player_id, kind),
    )
    open_row = cur.fetchone()
    if open_row and open_row[1] == team_id:
        if shirt_number:
            cur.execute(
                "UPDATE player_affiliations SET shirt_number = %s "
                "WHERE id = %s AND (shirt_number IS NULL OR shirt_number <> %s)",
                (shirt_number, open_row[0], shirt_number),
            )
        return
    if open_row:
        cur.execute(
            "UPDATE player_affiliations SET end_date = %s WHERE id = %s",
            (today, open_row[0]),
        )
    cur.execute(
        "INSERT INTO player_affiliations "
        "(player_id, team_id, kind, start_date, shirt_number) "
        "VALUES (%s, %s, %s, %s, %s)",
        (player_id, team_id, kind, today, shirt_number),
    )


def _store_wiki_provider(cur, player_id: int, wiki_title: str | None) -> None:
    title = _normalize_wiki_title(wiki_title)
    if not title:
        return
    cur.execute(
        "SELECT entity_id FROM provider_external_ids "
        "WHERE provider = 'wikipedia' AND external_id = %s",
        (title,),
    )
    row = cur.fetchone()
    if row and row[0] != player_id:
        return
    cur.execute(
        "INSERT INTO provider_external_ids "
        "(entity_type, entity_id, provider, external_id) "
        "VALUES ('player', %s, 'wikipedia', %s) "
        "ON CONFLICT (entity_type, entity_id, provider) DO UPDATE SET "
        "  external_id = EXCLUDED.external_id",
        (player_id, title),
    )


def _nationality_id_for_team(cur, team_id: int) -> int | None:
    cur.execute("SELECT country_id FROM teams WHERE id = %s", (team_id,))
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def _find_or_create_player(
    cur,
    *,
    name: str,
    team_id: int,
    kind: str,
    nationality_id: int | None,
    position: str | None,
    line_role: str | None,
    create_missing: bool,
    stats: dict[str, Any],
    shirt_number: int | None = None,
) -> int | None:
    if is_wikipedia_dob_name(name):
        return None

    pid = _resolve_wikipedia_player_on_team(cur, team_id, name, shirt_number, stats)
    if pid:
        return pid

    cur.execute(
        "SELECT id FROM players WHERE lower(trim(name)) = lower(trim(%s)) "
        "ORDER BY id",
        (name,),
    )
    rows = cur.fetchall()
    if len(rows) == 1:
        return rows[0][0]

    if not create_missing:
        return None

    from footballmind_sync import upsert_country

    if nationality_id is None:
        nat_name = None
    else:
        cur.execute("SELECT name FROM countries WHERE id = %s", (nationality_id,))
        nat_row = cur.fetchone()
        nat_name = nat_row[0] if nat_row else None

    if nat_name:
        nationality_id = upsert_country(cur, nat_name)

    cur.execute(
        "INSERT INTO players (name, nationality, position, line_role) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (name, nationality_id, position, line_role),
    )
    pid = cur.fetchone()[0]
    stats["created"] = stats.get("created", 0) + 1
    return pid


def _apply_wikipedia_player(
    cur,
    *,
    team_id: int,
    kind: str,
    p: dict[str, Any],
    stats: dict[str, Any],
    create_missing: bool,
    nationality_id: int | None = None,
    edition_id: int | None = None,
) -> None:
    pid = _find_or_create_player(
        cur,
        name=p["name"],
        team_id=team_id,
        kind=kind,
        nationality_id=nationality_id,
        position=p.get("position"),
        line_role=p.get("line_role"),
        create_missing=create_missing,
        stats=stats,
        shirt_number=p.get("shirt_number"),
    )
    if not pid:
        stats["missing"] = stats.get("missing", 0) + 1
        missing_names = stats.setdefault("missing_names", [])
        if len(missing_names) < 25:
            missing_names.append(p["name"])
        return

    stats["matched"] = stats.get("matched", 0) + 1
    _ensure_affiliation(cur, pid, team_id, kind, p.get("shirt_number"))
    _store_wiki_provider(cur, pid, p.get("wiki_title"))

    cur.execute(
        "SELECT line_role, position FROM players WHERE id = %s",
        (pid,),
    )
    row = cur.fetchone()
    stored_role, db_pos = row if row else (None, None)
    line_role = resolve_player_line_role(
        name=p["name"],
        db_line_role=stored_role or p.get("line_role"),
        db_position=db_pos or p.get("position"),
        goals=p.get("goals") or 0,
    )
    if line_role and line_role in LINE_ROLES:
        cur.execute(
            "UPDATE players SET line_role = %s, "
            "  position = COALESCE(position, %s) "
            "WHERE id = %s AND (line_role IS NULL OR position IS NULL)",
            (line_role, p.get("position"), pid),
        )
        if cur.rowcount:
            stats["updated_roles"] = stats.get("updated_roles", 0) + 1

    if p.get("shirt_number"):
        cur.execute(
            "UPDATE player_affiliations SET shirt_number = %s "
            "WHERE player_id = %s AND team_id = %s AND end_date IS NULL "
            "  AND (shirt_number IS NULL OR shirt_number <> %s)",
            (p["shirt_number"], pid, team_id, p["shirt_number"]),
        )
        if cur.rowcount:
            stats["updated_shirts"] = stats.get("updated_shirts", 0) + 1

    caps = p.get("caps")
    goals = p.get("goals")
    if edition_id is not None and (caps or goals):
        cur.execute(
            "INSERT INTO player_edition_stats "
            "(player_id, edition_id, team_id, goals, appearances) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (player_id, edition_id) DO UPDATE SET "
            "  goals = EXCLUDED.goals, "
            "  appearances = EXCLUDED.appearances, "
            "  team_id = COALESCE(EXCLUDED.team_id, player_edition_stats.team_id)",
            (pid, edition_id, team_id, goals or 0, caps or 0),
        )


def _wc_edition_id(cur) -> int | None:
    cur.execute(
        "SELECT e.id FROM competition_editions e "
        "JOIN competitions c ON c.id = e.competition_id "
        "WHERE c.code = 'WC' AND e.season IN ('2026', '2026/2027') "
        "ORDER BY e.id DESC LIMIT 1",
    )
    row = cur.fetchone()
    return row[0] if row else None


def sync_wikipedia_wc_squads(
    conn,
    *,
    page_title: str = DEFAULT_WC_SQUADS_PAGE,
    html: str | None = None,
    create_missing: bool = True,
) -> dict[str, Any]:
    """Sync WC squads from Wikipedia; optionally create players not in DB yet."""
    if html is None:
        html = fetch_wikipedia_html(page_title)
    squads = parse_wc_squads_html(html)

    stats: dict[str, Any] = {
        "page": page_title,
        "teams": 0,
        "players": 0,
        "matched": 0,
        "created": 0,
        "updated_roles": 0,
        "updated_shirts": 0,
        "repaired_names": 0,
        "missing": 0,
        "missing_names": [],
        "skipped_teams": [],
    }

    from footballmind_mcp_predict import _resolve_team

    with conn.cursor() as cur:
        edition_id = _wc_edition_id(cur)
        for squad in squads:
            db_team = _resolve_db_team(cur, squad["team"])
            if not db_team:
                stats["skipped_teams"].append(squad["team"])
                continue
            try:
                team_id, _ = _resolve_team(cur, db_team)
            except ValueError:
                stats["skipped_teams"].append(squad["team"])
                continue
            stats["teams"] += 1
            nat_id = _nationality_id_for_team(cur, team_id)

            for p in squad["players"]:
                stats["players"] += 1
                _apply_wikipedia_player(
                    cur,
                    team_id=team_id,
                    kind="national",
                    p=p,
                    stats=stats,
                    create_missing=create_missing,
                    nationality_id=nat_id,
                    edition_id=edition_id,
                )

    conn.commit()
    return stats


def sync_wikipedia_club_squads(
    conn,
    *,
    leagues: list[str] | None = None,
    delay_s: float = 0.5,
) -> dict[str, Any]:
    """Sync current club squads from Wikipedia wikitext (PL first)."""
    from footballmind_mcp_predict import _resolve_team
    from footballmind_sync import upsert_country

    league_map = LEAGUE_CLUB_WIKI_PAGES
    if leagues:
        league_map = {k: v for k, v in league_map.items() if k in leagues}

    stats: dict[str, Any] = {
        "leagues": list(league_map.keys()),
        "clubs": 0,
        "players": 0,
        "matched": 0,
        "created": 0,
        "updated_roles": 0,
        "updated_shirts": 0,
        "missing": 0,
        "skipped_clubs": [],
        "errors": [],
    }

    with conn.cursor() as cur:
        for _league_code, clubs in league_map.items():
            for wiki_title, db_name in clubs.items():
                try:
                    wikitext = fetch_wikitext(wiki_title)
                    section = extract_first_squad_block(wikitext)
                    if not section:
                        stats["skipped_clubs"].append(wiki_title)
                        continue
                    players = parse_fs_player_lines(section)
                    if not players:
                        stats["skipped_clubs"].append(wiki_title)
                        continue
                    try:
                        team_id, _ = _resolve_team(cur, db_name)
                    except ValueError:
                        stats["skipped_clubs"].append(db_name)
                        continue

                    stats["clubs"] += 1
                    for p in players:
                        stats["players"] += 1
                        nat_id = None
                        if p.get("nationality_code"):
                            nat_name = _country_from_fifa(p["nationality_code"])
                            nat_id = upsert_country(cur, nat_name, p["nationality_code"])
                        _apply_wikipedia_player(
                            cur,
                            team_id=team_id,
                            kind="club",
                            p=p,
                            stats=stats,
                            create_missing=True,
                            nationality_id=nat_id,
                        )
                    time.sleep(delay_s)
                except Exception as exc:
                    stats["errors"].append(f"{wiki_title}: {exc}")

    conn.commit()
    return stats


def sync_wikipedia_all(
    conn,
    *,
    wc: bool = True,
    clubs: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run WC national + club Wikipedia squad sync."""
    out: dict[str, Any] = {}
    if wc:
        out["wc"] = sync_wikipedia_wc_squads(conn, **kwargs)
    if clubs:
        out["clubs"] = sync_wikipedia_club_squads(conn)
    return out
