"""
FootballMind — EA FC / SoFIFA player attributes.

SoFIFA player profile pages include physical and meta fields that soccerdata's
read_player_ratings() does not export (height, weight, preferred/weak foot).
We parse those from the same HTML and store them for squad views, compare, and
lineup depth when real comp stats are sparse.

Sync requires the optional `soccerdata` package and a Chrome/Selenium runtime
(SoFIFA is Cloudflare-protected — plain HTTP requests fail). Run locally or in
CI with browser support:

    pip install soccerdata
    python footballmind_jobs.py sync-sofifa
    python footballmind_jobs.py sync-sofifa --teams Spain,Argentina
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from lxml import html

from footballmind_enrich import _store_provider_id

DEFAULT_SOFIFA_CACHE = Path.home() / "soccerdata" / "data" / "SoFIFA"
DEFAULT_SOFIFA_VERSION_R = int(os.environ.get("SOFIFA_VERSION_R", "250001"))

SOFIFA_CLUB_LEAGUES = (
    "ENG-Premier League",
    "ESP-La Liga",
    "GER-Bundesliga",
    "ITA-Serie A",
    "FRA-Ligue 1",
)

# SoFIFA `lg=` query ids — avoids /api/league JSON (often Cloudflare-blocked for bots).
SOFIFA_LEAGUE_LG: dict[str, int] = {
    "ENG-Premier League": 13,
    "ESP-La Liga": 53,
    "GER-Bundesliga": 19,
    "ITA-Serie A": 31,
    "FRA-Ligue 1": 16,
}

# soccerdata / SoFIFA short names -> football-data.org team names in our DB
SOFIFA_TEAM_ALIASES: dict[str, str] = {
    "Man City": "Manchester City FC",
    "Man Utd": "Manchester United FC",
    "Spurs": "Tottenham Hotspur FC",
    "Nott'm Forest": "Nottingham Forest FC",
    "West Ham": "West Ham United FC",
    "Wolves": "Wolverhampton Wanderers FC",
    "Newcastle": "Newcastle United FC",
    "Brighton": "Brighton & Hove Albion FC",
    "Bournemouth": "AFC Bournemouth",
    "Inter": "FC Internazionale Milano",
    "AC Milan": "AC Milan",
    "Bayern München": "FC Bayern München",
    "Bayern Munich": "FC Bayern München",
    "PSG": "Paris Saint-Germain FC",
    "Real Madrid": "Real Madrid CF",
    "Barcelona": "FC Barcelona",
    "Atlético Madrid": "Club Atlético de Madrid",
    "Athletic Club": "Athletic Club",
}

# SoFIFA display names that differ from football-data.org / our DB
SOFIFA_PLAYER_ALIASES: dict[str, str] = {
    "Benjamin White": "Ben White",
    "David Raya Martin": "David Raya",
    "Gabriel dos S. Magalhães": "Gabriel Magalhães",
    "Gabriel Teodoro Martinelli Silva": "Martinelli",
    "Gabriel Fernando de Jesus": "Gabriel Jesus",
    "Jurriën Timber": "Jurrien Timber",
    "Luiz Frello Filho Jorge": "Jorginho",
    "Fábio Daniel Ferreira Vieira": "Fabio Vieira",
}

_NAME_PARTICLES = frozenset({
    "de", "da", "dos", "das", "do", "del", "d", "s", "di", "du", "la", "le",
    "van", "von", "der", "den", "filho", "junior", "jr", "ii", "iii", "teodoro",
})


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("ø", "o"), ("Ø", "o"), ("æ", "ae"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _star_count(node) -> int | None:
    if node is None:
        return None
    filled = node.xpath(".//span[contains(@class,'icon-star-s')]")
    if filled:
        return len(filled)
    text = "".join(node.itertext()).strip()
    m = re.search(r"(\d)", text)
    return int(m.group(1)) if m else None


def _label_value(tree, label: str) -> str | None:
    """Read label/value blocks on SoFIFA profile pages (legacy + 2025 layout)."""
    label_low = label.lower()
    for node in tree.xpath("//p"):
        blob = " ".join(node.itertext()).strip()
        blob_low = blob.lower()
        if label_low not in blob_low:
            continue
        m = re.search(rf"{re.escape(label)}\s+(.+)", blob, re.I)
        if m:
            val = m.group(1).strip()
            if val and label_low not in val.lower():
                return val
        spans = node.xpath("./span")
        if spans:
            val = "".join(spans[0].itertext()).strip()
            if val and label_low not in val.lower():
                return val or None
    return None


def _rating_from_col(tree, label: str) -> int | None:
    """Read OVR/potential from `<div class="col"><em>89</em><div class="sub">Overall rating</div>`."""
    label_low = label.lower()
    for col in tree.xpath("//div[contains(@class,'col')]"):
        sub_nodes = col.xpath(".//div[contains(@class,'sub')]")
        if not sub_nodes:
            continue
        if label_low not in (sub_nodes[0].text_content() or "").lower():
            continue
        for em in col.xpath(".//em"):
            text = (em.text or "").strip()
            if text.isdigit():
                return int(text)
    return None


def _rating_value(tree, label: str) -> int | None:
    col_val = _rating_from_col(tree, label)
    if col_val is not None:
        return col_val
    for node in tree.xpath(f"//p[contains(., '{label}')]//em"):
        try:
            return int(node.text.strip())
        except (TypeError, ValueError, AttributeError):
            continue
    raw = _label_value(tree, label)
    if raw and raw.isdigit():
        return int(raw)
    return None


def _bio_height_weight(tree) -> tuple[int | None, int | None]:
    """Parse `178cm ... 68kg` from the age/height bio line on modern SoFIFA pages."""
    for node in tree.xpath("//p"):
        text = node.text_content() or ""
        if "cm" not in text or "kg" not in text:
            continue
        hm = re.search(r"(\d{3})\s*cm", text)
        wm = re.search(r"(\d{2,3})\s*kg", text)
        if hm or wm:
            return (
                int(hm.group(1)) if hm else None,
                int(wm.group(1)) if wm else None,
            )
    return None, None


def _label_leading_int(tree, label: str) -> int | None:
    """Skill moves / weak foot as a leading digit before SVG stars (2025 layout)."""
    for node in tree.xpath(f"//p[contains(., '{label}')]"):
        text = (node.text_content() or "").strip()
        m = re.match(r"^(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def _parse_sofifa_primary_position(tree) -> str | None:
    for node in tree.xpath("//p[contains(., 'Position')]"):
        text = (node.text_content() or "").strip()
        m = re.search(r"Position\s+([A-Za-z]+)", text, re.I)
        if m:
            return m.group(1).upper()
    return None


def parse_player_profile_html(page_html: str, *, sofifa_id: int | None = None) -> dict[str, Any]:
    """Extract EA FC bio + headline ratings from a SoFIFA player profile page."""
    tree = html.fromstring(page_html)
    name_node = tree.xpath("//div[contains(@class,'profile')]/h1")
    name = None
    if name_node:
        name = name_node[0].xpath("string(./text()[1])").strip()
        if not name:
            name = name_node[0].xpath("string(./br/following-sibling::text()[1])").strip()
        if not name:
            name = name_node[0].text_content().strip().split("\n")[0].strip()

    height_cm, weight_kg = _bio_height_weight(tree)
    height_raw = _label_value(tree, "Height")
    weight_raw = _label_value(tree, "Weight")
    if height_raw and height_cm is None:
        m = re.search(r"(\d{3})", height_raw)
        if m:
            height_cm = int(m.group(1))
    if weight_raw and weight_kg is None:
        m = re.search(r"(\d{2,3})", weight_raw)
        if m:
            weight_kg = int(m.group(1))

    pref = _label_value(tree, "Preferred foot")
    if pref:
        foot_m = re.search(r"(Left|Right)", pref, re.I)
        pref = foot_m.group(1).capitalize() if foot_m else pref.split()[0].capitalize()
        if pref not in ("Left", "Right"):
            pref = None

    weak_foot = _label_leading_int(tree, "Weak foot")
    if weak_foot is None:
        for node in tree.xpath("//p[contains(., 'Weak foot')]"):
            weak_foot = _star_count(node)
            break

    skill_moves = _label_leading_int(tree, "Skill moves")
    if skill_moves is None:
        for node in tree.xpath("//p[contains(., 'Skill moves')]"):
            skill_moves = _star_count(node)
            break

    primary_position = _parse_sofifa_primary_position(tree)
    from footballmind_roles import map_sofifa_position

    line_role = map_sofifa_position(primary_position)

    return {
        "sofifa_id": sofifa_id,
        "name": name,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "preferred_foot": pref,
        "weak_foot": weak_foot,
        "overall_rating": _rating_value(tree, "Overall rating"),
        "potential": _rating_value(tree, "Potential"),
        "skill_moves": skill_moves,
        "work_rate": _label_value(tree, "Work rate"),
        "primary_position": primary_position,
        "line_role": line_role,
    }


def _resolve_team_id(cur, sofifa_team: str) -> int | None:
    from footballmind_mcp_predict import _resolve_team

    candidates = [sofifa_team, SOFIFA_TEAM_ALIASES.get(sofifa_team, "")]
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            team_id, _ = _resolve_team(cur, name)
            return team_id
        except ValueError:
            continue
    # Fuzzy: last word (e.g. "Arsenal" from context)
    token = sofifa_team.strip().split()[-1]
    if token and token not in seen:
        try:
            team_id, _ = _resolve_team(cur, token)
            return team_id
        except ValueError:
            pass
    return None


def _sofifa_tokens(name: str) -> list[str]:
    tokens: list[str] = []
    for raw in name.split():
        if re.fullmatch(r"[A-Za-z]\.", raw):
            continue
        t = _norm(raw)
        if not t or t in _NAME_PARTICLES:
            continue
        tokens.append(t)
    return tokens


def _token_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if a and b and a[0] == b[0] and min(len(a), len(b)) >= 3:
        return a.startswith(b[:3]) or b.startswith(a[:3])
    return False


def _tokens_subsequence(db_tokens: list[str], sofifa_tokens: list[str]) -> bool:
    it = iter(sofifa_tokens)
    for db_t in db_tokens:
        for sf_t in it:
            if _token_match(db_t, sf_t):
                break
        else:
            return False
    return True


def _score_sofifa_pre(sof_norm: str, sof_t: list[str], db_name: str) -> int:
    """Score a DB name against a SoFIFA name whose norm/tokens are precomputed.
    The SoFIFA side is constant across a squad scan, so hoisting its normalization
    out of the per-row loop turns an O(n) re-normalize into O(1)."""
    db_norm = _norm(db_name)
    if sof_norm == db_norm:
        return 100
    db_t = _sofifa_tokens(db_name)
    if not sof_t or not db_t:
        return 0
    if _tokens_subsequence(db_t, sof_t):
        return 95
    if _token_match(db_t[0], sof_t[0]) and _token_match(db_t[-1], sof_t[-1]):
        return 88
    if db_t[0] in sof_t and db_t[-1] in sof_t:
        return 85
    if len(db_t) == 1 and db_t[0] in sof_t:
        return 82
    if db_norm in sof_norm or sof_norm in db_norm:
        return 75
    return 0


def _score_sofifa_db_name(sofifa_name: str, db_name: str) -> int:
    return _score_sofifa_pre(_norm(sofifa_name), _sofifa_tokens(sofifa_name), db_name)


def _resolve_sofifa_player_on_team(
    cur,
    team_id: int,
    sofifa_name: str,
    sofifa_id: int | None = None,
    squad: list | None = None,
) -> int | None:
    """Match SoFIFA roster names to our squad (handles extra middle names / mononyms).

    ``squad`` (list of (player_id, name)) may be supplied by the caller so the same
    team's roster is fetched once and reused across all its players, instead of one
    squad SELECT per roster row."""
    if sofifa_id is not None:
        cur.execute(
            "SELECT entity_id FROM provider_external_ids "
            "WHERE entity_type = 'player' AND provider = 'sofifa' AND external_id = %s",
            (str(sofifa_id),))
        row = cur.fetchone()
        if row:
            cur.execute(
                "SELECT 1 FROM player_affiliations "
                "WHERE player_id = %s AND team_id = %s AND end_date IS NULL",
                (row[0], team_id))
            if cur.fetchone():
                return row[0]

    alias = SOFIFA_PLAYER_ALIASES.get(sofifa_name.strip())
    if alias:
        from footballmind_services import _resolve_player_on_team as svc_resolve

        found = svc_resolve(cur, alias, team_id)
        if found:
            return found[0]

    from footballmind_services import _resolve_player_on_team as svc_resolve

    found = svc_resolve(cur, sofifa_name.strip(), team_id)
    if found:
        return found[0]

    if squad is None:
        cur.execute(
            "SELECT p.id, p.name FROM players p "
            "JOIN player_affiliations pa ON pa.player_id = p.id "
            "WHERE pa.team_id = %s AND pa.end_date IS NULL",
            (team_id,))
        squad = cur.fetchall()

    sof_norm = _norm(sofifa_name)
    sof_t = _sofifa_tokens(sofifa_name)
    best_id: int | None = None
    best_score = 0
    best_name = ""
    for pid, db_name in squad:
        score = _score_sofifa_pre(sof_norm, sof_t, db_name)
        if score > best_score or (score == best_score and score > 0 and len(db_name) < len(best_name)):
            best_score = score
            best_id = pid
            best_name = db_name

    if best_score >= 82:
        return best_id
    return None


def _resolve_player_on_team(cur, team_id: int, *names: str) -> int | None:
    from footballmind_services import _resolve_player_on_team

    for name in names:
        if not name:
            continue
        found = _resolve_player_on_team(cur, name.strip(), team_id)
        if found:
            return found[0]
        if " " in name.strip():
            last = name.strip().split()[-1]
            found = _resolve_player_on_team(cur, last, team_id)
            if found:
                return found[0]
    return None


def _upsert_attributes(cur, player_id: int, attrs: dict[str, Any],
                       fifa_edition: str | None) -> None:
    cur.execute(
        "INSERT INTO player_eafc_attributes "
        "(player_id, sofifa_id, height_cm, weight_kg, preferred_foot, weak_foot, "
        " overall_rating, potential, skill_moves, work_rate, primary_position, "
        " fifa_edition, synced_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
        "ON CONFLICT (player_id) DO UPDATE SET "
        "  sofifa_id = COALESCE(EXCLUDED.sofifa_id, player_eafc_attributes.sofifa_id), "
        "  height_cm = COALESCE(EXCLUDED.height_cm, player_eafc_attributes.height_cm), "
        "  weight_kg = COALESCE(EXCLUDED.weight_kg, player_eafc_attributes.weight_kg), "
        "  preferred_foot = COALESCE(EXCLUDED.preferred_foot, player_eafc_attributes.preferred_foot), "
        "  weak_foot = COALESCE(EXCLUDED.weak_foot, player_eafc_attributes.weak_foot), "
        "  overall_rating = COALESCE(EXCLUDED.overall_rating, player_eafc_attributes.overall_rating), "
        "  potential = COALESCE(EXCLUDED.potential, player_eafc_attributes.potential), "
        "  skill_moves = COALESCE(EXCLUDED.skill_moves, player_eafc_attributes.skill_moves), "
        "  work_rate = COALESCE(EXCLUDED.work_rate, player_eafc_attributes.work_rate), "
        "  primary_position = COALESCE(EXCLUDED.primary_position, player_eafc_attributes.primary_position), "
        "  fifa_edition = COALESCE(EXCLUDED.fifa_edition, player_eafc_attributes.fifa_edition), "
        "  synced_at = now()",
        (
            player_id,
            attrs.get("sofifa_id"),
            attrs.get("height_cm"),
            attrs.get("weight_kg"),
            attrs.get("preferred_foot"),
            attrs.get("weak_foot"),
            attrs.get("overall_rating"),
            attrs.get("potential"),
            attrs.get("skill_moves"),
            attrs.get("work_rate"),
            attrs.get("primary_position"),
            fifa_edition,
        ),
    )
    if attrs.get("line_role"):
        cur.execute(
            "UPDATE players SET line_role = %s WHERE id = %s",
            (attrs["line_role"], player_id),
        )
    if attrs.get("sofifa_id"):
        _store_provider_id(cur, "player", player_id, "sofifa", str(attrs["sofifa_id"]))


def get_eafc_attributes(conn, player_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT height_cm, weight_kg, preferred_foot, weak_foot, "
            "       overall_rating, potential, skill_moves, work_rate, "
            "       primary_position, fifa_edition, synced_at "
            "FROM player_eafc_attributes WHERE player_id = %s",
            (player_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    (height_cm, weight_kg, pref, weak, ovr, pot, skills, work, primary_pos, edition, synced) = row
    return {
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "preferred_foot": pref,
        "weak_foot": weak,
        "overall_rating": ovr,
        "potential": pot,
        "skill_moves": skills,
        "work_rate": work,
        "primary_position": primary_pos,
        "fifa_edition": edition,
        "synced_at": synced.isoformat() if synced else None,
        "source": "sofifa",
    }


def get_eafc_attributes_bulk(conn, player_ids: list[int]) -> dict[int, dict]:
    if not player_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT player_id, height_cm, weight_kg, preferred_foot, weak_foot, "
            "       overall_rating, potential, skill_moves, work_rate, "
            "       primary_position, fifa_edition "
            "FROM player_eafc_attributes WHERE player_id = ANY(%s)",
            (player_ids,),
        )
        out: dict[int, dict] = {}
        for (pid, h, w, pref, weak, ovr, pot, skills, work, primary_pos, edition) in cur.fetchall():
            out[pid] = {
                "height_cm": h,
                "weight_kg": w,
                "preferred_foot": pref,
                "weak_foot": weak,
                "overall_rating": ovr,
                "potential": pot,
                "skill_moves": skills,
                "work_rate": work,
                "primary_position": primary_pos,
                "fifa_edition": edition,
                "source": "sofifa",
            }
        return out


def _read_http_page(raw) -> str:
    if isinstance(raw, str):
        return raw
    if hasattr(raw, "read"):
        data = raw.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)
    return str(raw or "")


def _is_cloudflare_challenge(page_html: str) -> bool:
    low = (page_html or "").lower()
    if not low.strip():
        return True
    # Real SoFIFA profile/team pages are large and include these markers.
    if len(low) > 8000 and ("sofifa" in low or "overall rating" in low or "data-col=" in low):
        return False
    markers = (
        "performing security verification",
        "challenge-platform",
        "cf-turnstile",
        "turnstile-response",
        "verify you are human",
        "checking your browser",
        "just a moment",
        "attention required! | cloudflare",
        "enable javascript and cookies",
    )
    return any(m in low for m in markers)


def _driver_html(reader) -> str:
    driver = getattr(reader, "_driver", None)
    if driver is None:
        return ""
    try:
        return driver.page_source or ""
    except Exception:
        return ""


def _wait_cloudflare_after_nav(
    reader,
    *,
    label: str,
    timeout_sec: int = 600,
) -> str:
    """Poll the current browser tab — do not reload (reload resets the checkbox)."""
    import time

    deadline = time.time() + timeout_sec
    page = _driver_html(reader)
    if not _is_cloudflare_challenge(page):
        return page
    mins = max(1, timeout_sec // 60)
    print(
        f"[sync-sofifa] Cloudflare on {label} — click the checkbox in the Chrome window. "
        f"Waiting up to {mins} min (do not close the window)…",
        flush=True,
    )
    last_reminder = time.time()
    while time.time() < deadline:
        time.sleep(2)
        page = _driver_html(reader)
        if not _is_cloudflare_challenge(page):
            print("[sync-sofifa] Cloudflare passed — continuing", flush=True)
            return page
        if time.time() - last_reminder >= 30:
            print("[sync-sofifa] still waiting for Cloudflare…", flush=True)
            last_reminder = time.time()
    return _driver_html(reader)


def _hold_browser_until_enter(reader, *, reason: str) -> None:
    print(f"[sync-sofifa] {reason}", flush=True)
    print("[sync-sofifa] Chrome will stay open — press Enter here when done…", flush=True)
    try:
        input()
    except EOFError:
        import time
        time.sleep(60)
    driver = getattr(reader, "_driver", None)
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass


def _team_name_matches(requested: str, sofifa_name: str) -> bool:
    if _norm(requested) == _norm(sofifa_name):
        return True
    for short, long_name in SOFIFA_TEAM_ALIASES.items():
        req = _norm(requested)
        if req in (_norm(short), _norm(long_name)) and _norm(sofifa_name) == _norm(short):
            return True
    req = _norm(requested)
    sof = _norm(sofifa_name)
    if len(req) >= 4 and (req in sof or sof in req):
        return True
    return False


def _team_matches_filter(sofifa_team: str, requested: list[str] | None) -> bool:
    if not requested:
        return True
    return any(_team_name_matches(name, sofifa_team) for name in requested)


def _parse_sofifa_teams_html(page_html: str, league_key: str) -> list[dict[str, Any]]:
    tree = html.fromstring(page_html)
    pat_team = re.compile(r"/team/(\d+)/[\w-]+/")
    teams: list[dict[str, Any]] = []
    for node in tree.xpath("//table/tbody/tr"):
        links = node.xpath(".//td[2]//a")
        if not links:
            continue
        team_link = links[0]
        href = team_link.get("href") or ""
        m = pat_team.search(href)
        if not m:
            continue
        name = (team_link.text or "").strip()
        if not name:
            continue
        teams.append({
            "team_id": int(m.group(1)),
            "team": name,
            "league": league_key,
        })
    return teams


def _parse_sofifa_players_html(page_html: str, *, team_name: str, league_key: str) -> list[dict[str, Any]]:
    tree = html.fromstring(page_html)
    pat_player = re.compile(r"/player/(\d+)/[\w-]+/")
    tables = tree.xpath("//article/table")
    if not tables:
        return []
    players: list[dict[str, Any]] = []
    for node in tables[0].xpath(".//td[2]/a[contains(@href,'/player/')]"):
        href = node.get("href") or ""
        m = pat_player.search(href)
        if not m:
            continue
        player_name = (node.get("data-tippy-content") or node.text_content() or "").strip()
        if not player_name:
            continue
        players.append({
            "player_id": int(m.group(1)),
            "player": player_name,
            "team": team_name,
            "league": league_key,
        })
    return players


def _fetch_sofifa_page(
    reader,
    url: str,
    filepath: Path,
    *,
    headless: bool,
    label: str,
    cloudflare_wait_sec: int,
    no_cache: bool = False,
) -> str:
    """Load a SoFIFA page. Always read ``reader.get`` output — not ``page_source``.

    After warmup the Selenium tab may still be on sofifa.com while ``get()`` serves
    a cached teams/profile file without navigating; using ``page_source`` then
    parses the wrong HTML and returns zero teams.
    """
    raw = reader.get(url, filepath, no_cache=no_cache)
    page = _read_http_page(raw)
    if (not page or len(page) < 500) and getattr(reader, "_driver", None):
        page = _driver_html(reader) or page
    if not headless and _is_cloudflare_challenge(page) and getattr(reader, "_driver", None):
        # Cached file may be a challenge page — wait on the live browser tab.
        reader.get(url, filepath, no_cache=True)
        page = _wait_cloudflare_after_nav(
            reader, label=label, timeout_sec=cloudflare_wait_sec,
        )
        live = _driver_html(reader)
        if live and not _is_cloudflare_challenge(live):
            page = live
    return page


def _read_sofifa_roster_html(
    reader,
    *,
    leagues: list[str],
    teams: list[str] | None,
    version_id: int,
    headless: bool,
    cloudflare_wait_sec: int,
):
    """Load squads via HTML team pages (soccerdata read_players uses blocked /api/league)."""
    import pandas as pd

    rows: list[dict[str, Any]] = []
    wanted = {_norm(t) for t in teams} if teams else set()
    found_teams: set[str] = set()

    for league_key in leagues:
        lg_id = SOFIFA_LEAGUE_LG.get(league_key)
        if lg_id is None:
            print(f"[sync-sofifa] skip unknown league {league_key!r}", flush=True)
            continue
        teams_url = f"https://sofifa.com/teams?lg={lg_id}&r={version_id}&set=true"
        teams_path = reader.data_dir / f"teams_{lg_id}_{version_id}.html"
        print(f"[sync-sofifa] loading {league_key} team list…", flush=True)
        teams_page = _fetch_sofifa_page(
            reader,
            teams_url,
            teams_path,
            headless=headless,
            label=f"{league_key} teams",
            cloudflare_wait_sec=cloudflare_wait_sec,
        )
        if _is_cloudflare_challenge(teams_page):
            raise RuntimeError(f"Cloudflare blocked team list for {league_key}")
        league_teams = _parse_sofifa_teams_html(teams_page, league_key)
        if not league_teams:
            print(f"[sync-sofifa] retrying {league_key} team list (live fetch)…", flush=True)
            teams_page = _fetch_sofifa_page(
                reader,
                teams_url,
                teams_path,
                headless=headless,
                label=f"{league_key} teams",
                cloudflare_wait_sec=cloudflare_wait_sec,
                no_cache=True,
            )
            league_teams = _parse_sofifa_teams_html(teams_page, league_key)
        if not league_teams:
            raise RuntimeError(f"No teams parsed for {league_key} (page layout may have changed)")

        for team_row in league_teams:
            team_name = team_row["team"]
            if not _team_matches_filter(team_name, teams):
                continue
            team_id = team_row["team_id"]
            squad_url = f"https://sofifa.com/team/{team_id}/?r={version_id}&set=true"
            squad_path = reader.data_dir / f"players_{team_id}_{version_id}.html"
            print(f"[sync-sofifa] loading squad {team_name}…", flush=True)
            squad_page = _fetch_sofifa_page(
                reader,
                squad_url,
                squad_path,
                headless=headless,
                label=team_name,
                cloudflare_wait_sec=min(cloudflare_wait_sec, 180),
            )
            if _is_cloudflare_challenge(squad_page):
                print(f"[sync-sofifa] skip {team_name} (Cloudflare)", flush=True)
                continue
            rows.extend(
                _parse_sofifa_players_html(
                    squad_page, team_name=team_name, league_key=league_key,
                )
            )
            if wanted:
                for req in teams or []:
                    if _team_name_matches(req, team_name):
                        found_teams.add(_norm(req))
        if wanted and found_teams >= wanted:
            print(f"[sync-sofifa] found all requested teams — skipping remaining leagues", flush=True)
            break

    if not rows:
        return pd.DataFrame(columns=["player", "team", "league"])
    print(f"[sync-sofifa] parsed {len(rows)} players from SoFIFA squads", flush=True)
    df = pd.DataFrame(rows).drop_duplicates(subset=["player_id"])
    return df.set_index("player_id")


def _patch_sofifa_versions(version_id: int) -> None:
    """Bypass broken SoFIFA version dropdown scrape with a pinned release id."""
    import pandas as pd
    import soccerdata.sofifa as sf_mod

    def pinned_versions(self, max_age=1):  # noqa: ARG001
        return pd.DataFrame([{
            "fifa_edition": "EA FC",
            "update": "pinned",
            "version_id": version_id,
        }]).set_index("version_id")

    sf_mod.SoFIFA.read_versions = pinned_versions  # type: ignore[method-assign]


def _build_sofifa_reader(
    *,
    leagues: list[str],
    version_id: int | None,
    headless: bool,
):
    """Build soccerdata SoFIFA reader.

    soccerdata<=1.8.x accepts ``headless=`` on SoFIFA but never forwards it to
    BaseSeleniumReader, so ``--visible`` would still run headless. Re-init the
    driver after correcting ``reader.headless``.
    """
    import soccerdata as sd

    vid = version_id or DEFAULT_SOFIFA_VERSION_R
    _patch_sofifa_versions(vid)
    reader = sd.SoFIFA(
        leagues=leagues,
        versions=vid,
        no_store=headless,
        headless=headless,
    )
    if reader.headless != headless:
        reader.headless = headless
        if getattr(reader, "_driver", None) is not None:
            reader._driver.quit()
        reader._driver = reader._init_webdriver()
    return reader


def _persist_eafc_attributes(player_id: int, attrs: dict[str, Any],
                             fifa_edition: str) -> None:
    """Write one row on a fresh connection (Neon pooler drops idle SSL during long scrapes)."""
    from footballmind_db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            _upsert_attributes(cur, player_id, attrs, fifa_edition)
        conn.commit()


def _resolve_player_by_name(cur, name: str) -> int | None:
    if not name:
        return None
    cur.execute(
        "SELECT p.id FROM players p "
        "WHERE p.name ILIKE %s OR p.name ILIKE %s "
        "ORDER BY CASE WHEN LOWER(p.name) = LOWER(%s) THEN 0 ELSE 1 END, p.name "
        "LIMIT 1",
        (name.strip(), f"%{name.strip().split()[-1]}%", name.strip()))
    row = cur.fetchone()
    return row[0] if row else None


def db_club_team_names(conn) -> list[str]:
    """All club names in our DB — used to filter SoFIFA squads for --all-clubs."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name FROM teams WHERE type = 'club' ORDER BY name",
        )
        return [row[0] for row in cur.fetchall()]


def sync_sofifa_from_cache(
    conn,
    cache_dir: Path | str | None = None,
    *,
    max_files: int | None = None,
) -> dict[str, int | str]:
    """Import player profiles from cached SoFIFA HTML (offline / post-manual browse)."""
    cache_dir = Path(cache_dir or DEFAULT_SOFIFA_CACHE)
    if not cache_dir.is_dir():
        return {"error": f"cache dir not found: {cache_dir}", "synced": 0}

    files = sorted(cache_dir.glob("player_*_*.html"))
    if max_files:
        files = files[:max_files]
    if not files:
        return {"error": f"no player_*.html files in {cache_dir}", "synced": 0}

    synced = skipped = 0
    from footballmind_db import get_connection

    for path in files:
        m = re.match(r"player_(\d+)_(\d+)\.html$", path.name)
        if not m:
            skipped += 1
            continue
        sofifa_id = int(m.group(1))
        page = path.read_text(encoding="utf-8", errors="replace")
        if _is_cloudflare_challenge(page):
            skipped += 1
            continue
        attrs = parse_player_profile_html(page, sofifa_id=sofifa_id)
        player_id = None
        player_name = attrs.get("name")
        if player_name:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    player_id = _resolve_player_by_name(cur, player_name)
        if not player_id:
            skipped += 1
            continue
        if not any(attrs.get(k) for k in ("height_cm", "overall_rating", "preferred_foot")):
            skipped += 1
            continue
        _persist_eafc_attributes(player_id, attrs, "cached")
        synced += 1

    return {"checked": len(files), "synced": synced, "skipped": skipped, "cache_dir": str(cache_dir)}


def _warmup_sofifa_browser(reader, *, headless: bool, timeout_sec: int = 600) -> bool:
    """In visible mode, load sofifa.com and wait for the user to pass Cloudflare."""
    if headless:
        return True
    url = "https://sofifa.com/"
    print(
        "[sync-sofifa] Opening sofifa.com in Chrome — complete Cloudflare when prompted…",
        flush=True,
    )
    reader.get(url, reader.data_dir / "_warmup.html", no_cache=True)
    page = _wait_cloudflare_after_nav(reader, label="sofifa.com", timeout_sec=timeout_sec)
    if _is_cloudflare_challenge(page):
        print("[sync-sofifa] timed out waiting for Cloudflare on sofifa.com", flush=True)
        return False
    print("[sync-sofifa] SoFIFA session ready", flush=True)
    return True


def _fetch_profile_html(
    reader,
    sofifa_id: int,
    version_id: int,
    *,
    headless: bool = True,
    player_name: str | None = None,
    cloudflare_wait_sec: int = 120,
) -> str:
    url = f"https://sofifa.com/player/{sofifa_id}/?r={version_id}&set=true"
    filepath = reader.data_dir / f"player_{sofifa_id}_{version_id}.html"
    label = player_name or str(sofifa_id)
    return _fetch_sofifa_page(
        reader,
        url,
        filepath,
        headless=headless,
        label=label,
        cloudflare_wait_sec=cloudflare_wait_sec,
    )


def _build_sofifa_work_queue(
    roster,
    ttl_days: int | None = 90,
) -> tuple[list[tuple[int, int, str]], int, int]:
    """Match SoFIFA roster rows to DB players on a short-lived connection.

    Each team's squad is fetched once and reused across its roster rows (was one
    squad SELECT per player). Players whose player_eafc_attributes were synced within
    ``ttl_days`` and already carry a rating are dropped -- fetching a SoFIFA profile
    is the most expensive step in the pipeline (one Selenium page load each) and EA FC
    attributes change at most once per edition, so re-fetching fresh rows is pure
    waste. Returns (work, skipped_unmatched, skipped_fresh)."""
    from footballmind_db import get_connection

    work: list[tuple[int, int, str]] = []
    skipped = 0
    skipped_fresh = 0
    seen_players: set[int] = set()
    squad_cache: dict[int, list] = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            for sofifa_id, row in roster.iterrows():
                if sofifa_id in seen_players:
                    continue
                seen_players.add(int(sofifa_id))
                team_name = row.get("team") or ""
                player_name = row.get("player") or ""
                team_id = _resolve_team_id(cur, str(team_name))
                if not team_id:
                    skipped += 1
                    continue
                squad = squad_cache.get(team_id)
                if squad is None:
                    cur.execute(
                        "SELECT p.id, p.name FROM players p "
                        "JOIN player_affiliations pa ON pa.player_id = p.id "
                        "WHERE pa.team_id = %s AND pa.end_date IS NULL",
                        (team_id,))
                    squad = cur.fetchall()
                    squad_cache[team_id] = squad
                player_id = _resolve_sofifa_player_on_team(
                    cur, team_id, str(player_name), int(sofifa_id), squad=squad,
                )
                if not player_id:
                    skipped += 1
                    continue
                work.append((player_id, int(sofifa_id), str(player_name)))

            if ttl_days and work:
                player_ids = [w[0] for w in work]
                cur.execute(
                    "SELECT player_id FROM player_eafc_attributes "
                    "WHERE player_id = ANY(%s) AND overall_rating IS NOT NULL "
                    "  AND synced_at > now() - make_interval(days => %s)",
                    (player_ids, ttl_days))
                fresh = {r[0] for r in cur.fetchall()}
                if fresh:
                    work = [w for w in work if w[0] not in fresh]
                    skipped_fresh = len(fresh)
    return work, skipped, skipped_fresh


def sync_sofifa_attributes(
    conn=None,
    *,
    leagues: list[str] | None = None,
    teams: list[str] | None = None,
    version_id: int | None = None,
    max_players: int | None = None,
    headless: bool = True,
    cloudflare_wait_sec: int = 600,
    ttl_days: int | None = 90,
) -> dict[str, int | str]:
    """Pull SoFIFA profiles for club/national squads and upsert player_eafc_attributes.

    ``conn`` is ignored (kept for call-site compatibility). DB access uses short-lived
    connections so Neon does not kill idle transactions during long Chrome scrapes.
    """
    try:
        import soccerdata  # noqa: F401
    except ImportError:
        return {"error": "soccerdata not installed — pip install -r requirements-sofifa.txt", "synced": 0}

    leagues = leagues or list(SOFIFA_CLUB_LEAGUES)
    try:
        reader = _build_sofifa_reader(
            leagues=leagues,
            version_id=version_id,
            headless=headless,
        )
    except Exception as e:
        return {
            "error": f"SoFIFA init failed (Chrome/Cloudflare?): {e}",
            "synced": 0,
            "hint": "Try: sync-sofifa --visible, or pass Cloudflare in Chrome then --import-cache",
        }

    version_row = reader.versions.iloc[-1]
    vid = int(version_row.name)
    fifa_edition = str(version_row.get("fifa_edition") or "")

    if not _warmup_sofifa_browser(reader, headless=headless, timeout_sec=cloudflare_wait_sec):
        if not headless:
            _hold_browser_until_enter(
                reader,
                reason="Cloudflare was not cleared in the Selenium Chrome window.",
            )
        return {
            "checked": 0,
            "synced": 0,
            "skipped": 0,
            "fifa_edition": fifa_edition,
            "hint": (
                "Cloudflare was not cleared in the Selenium Chrome window. "
                "Use --visible, complete the check there (not your normal browser), then retry."
            ),
        }

    try:
        roster = _read_sofifa_roster_html(
            reader,
            leagues=leagues,
            teams=teams,
            version_id=vid,
            headless=headless,
            cloudflare_wait_sec=cloudflare_wait_sec,
        )
    except Exception as e:
        if not headless:
            _hold_browser_until_enter(reader, reason=f"roster load failed: {e}")
        return {"error": f"roster load failed: {e}", "synced": 0}

    if roster.empty:
        return {"checked": 0, "synced": 0, "skipped": 0, "fifa_edition": fifa_edition}

    work, skipped, skipped_fresh = _build_sofifa_work_queue(roster, ttl_days=ttl_days)

    print(
        f"[sync-sofifa] roster={len(roster)} db_matched={len(work)} "
        f"(skipped {skipped} unmatched names, {skipped_fresh} already-fresh "
        f"within {ttl_days}d)",
        flush=True,
    )

    synced = checked = 0
    cloudflare_hits = 0

    for player_id, sofifa_id, player_name in work:
        if max_players and synced >= max_players:
            break
        checked += 1
        try:
            page = _fetch_profile_html(
                reader,
                sofifa_id,
                vid,
                headless=headless,
                player_name=player_name,
                cloudflare_wait_sec=min(cloudflare_wait_sec, 180),
            )
            if _is_cloudflare_challenge(page):
                cloudflare_hits += 1
                skipped += 1
                continue
            attrs = parse_player_profile_html(page, sofifa_id=sofifa_id)
        except Exception:
            skipped += 1
            continue
        if not any(attrs.get(k) for k in ("height_cm", "overall_rating", "preferred_foot")):
            skipped += 1
            continue
        try:
            _persist_eafc_attributes(player_id, attrs, fifa_edition)
            synced += 1
            print(f"[sync-sofifa] synced {player_name} (OVR {attrs.get('overall_rating')})", flush=True)
        except Exception:
            skipped += 1

    out = {
        "checked": checked,
        "synced": synced,
        "skipped": skipped,
        "fifa_edition": fifa_edition,
    }
    if not headless and synced > 0:
        out["cache_dir"] = str(reader.data_dir)
    if synced == 0 and checked > 0:
        if cloudflare_hits == checked:
            out["hint"] = (
                "Every profile page hit Cloudflare. Run with --visible, complete the check "
                "in the automated Chrome window (not a normal browser tab), then retry. "
                "Successful runs cache HTML under ~/soccerdata/data/SoFIFA/ for --import-cache."
            )
        else:
            out["hint"] = (
                "No profiles parsed — check team name matching or try --teams Arsenal "
                "with --visible after passing Cloudflare."
            )
    if not headless and synced == 0:
        _hold_browser_until_enter(
            reader,
            reason="No players synced — finish Cloudflare in Chrome if needed, then retry.",
        )
    return out
