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
    """Read `<p>Label <span>value</span></p>` blocks on SoFIFA profile pages."""
    label_low = label.lower()
    for node in tree.xpath("//p"):
        blob = " ".join(node.itertext()).strip().lower()
        if label_low not in blob:
            continue
        spans = node.xpath("./span")
        if spans:
            val = "".join(spans[0].itertext()).strip()
            if val and label_low not in val.lower():
                return val or None
    return None


def _rating_value(tree, label: str) -> int | None:
    for node in tree.xpath(f"//p[contains(., '{label}')]//em"):
        try:
            return int(node.text.strip())
        except (TypeError, ValueError, AttributeError):
            continue
    raw = _label_value(tree, label)
    if raw and raw.isdigit():
        return int(raw)
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

    height_raw = _label_value(tree, "Height")
    weight_raw = _label_value(tree, "Weight")
    height_cm = None
    weight_kg = None
    if height_raw:
        m = re.search(r"(\d{3})", height_raw)
        if m:
            height_cm = int(m.group(1))
    if weight_raw:
        m = re.search(r"(\d{2,3})", weight_raw)
        if m:
            weight_kg = int(m.group(1))

    pref = _label_value(tree, "Preferred foot")
    if pref:
        pref = pref.split()[0].capitalize()
        if pref not in ("Left", "Right"):
            pref = None

    weak_node = None
    for node in tree.xpath("//p[contains(., 'Weak foot')]"):
        weak_node = node
        break
    weak_foot = _star_count(weak_node)

    skill_node = None
    for node in tree.xpath("//p[contains(., 'Skill moves')]"):
        skill_node = node
        break
    skill_moves = _star_count(skill_node)

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
        " overall_rating, potential, skill_moves, work_rate, fifa_edition, synced_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
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
            fifa_edition,
        ),
    )
    if attrs.get("sofifa_id"):
        _store_provider_id(cur, "player", player_id, "sofifa", str(attrs["sofifa_id"]))


def get_eafc_attributes(conn, player_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT height_cm, weight_kg, preferred_foot, weak_foot, "
            "       overall_rating, potential, skill_moves, work_rate, "
            "       fifa_edition, synced_at "
            "FROM player_eafc_attributes WHERE player_id = %s",
            (player_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    (height_cm, weight_kg, pref, weak, ovr, pot, skills, work, edition, synced) = row
    return {
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "preferred_foot": pref,
        "weak_foot": weak,
        "overall_rating": ovr,
        "potential": pot,
        "skill_moves": skills,
        "work_rate": work,
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
            "       overall_rating, potential, skill_moves, work_rate, fifa_edition "
            "FROM player_eafc_attributes WHERE player_id = ANY(%s)",
            (player_ids,),
        )
        out: dict[int, dict] = {}
        for (pid, h, w, pref, weak, ovr, pot, skills, work, edition) in cur.fetchall():
            out[pid] = {
                "height_cm": h,
                "weight_kg": w,
                "preferred_foot": pref,
                "weak_foot": weak,
                "overall_rating": ovr,
                "potential": pot,
                "skill_moves": skills,
                "work_rate": work,
                "fifa_edition": edition,
                "source": "sofifa",
            }
        return out


def _is_cloudflare_challenge(page_html: str) -> bool:
    low = (page_html or "").lower()
    return "performing security verification" in low or "challenge-platform" in low


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
    import soccerdata as sd

    vid = version_id or DEFAULT_SOFIFA_VERSION_R
    _patch_sofifa_versions(vid)
    return sd.SoFIFA(
        leagues=leagues,
        versions=vid,
        no_store=True,
        headless=headless,
    )


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
    with conn.cursor() as cur:
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


def _fetch_profile_html(reader, sofifa_id: int, version_id: int) -> str:
    url = f"https://sofifa.com/player/{sofifa_id}/?r={version_id}&set=true"
    filepath = reader.data_dir / f"player_{sofifa_id}_{version_id}.html"
    return reader.get(url, filepath)


def sync_sofifa_attributes(
    conn,
    *,
    leagues: list[str] | None = None,
    teams: list[str] | None = None,
    version_id: int | None = None,
    max_players: int | None = None,
    headless: bool = True,
) -> dict[str, int | str]:
    """Pull SoFIFA profiles for club/national squads and upsert player_eafc_attributes."""
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

    try:
        roster = reader.read_players(team=teams)
    except Exception as e:
        return {"error": f"read_players failed: {e}", "synced": 0}

    if roster.empty:
        return {"checked": 0, "synced": 0, "skipped": 0, "fifa_edition": fifa_edition}

    synced = skipped = checked = 0
    seen_players: set[int] = set()
    work: list[tuple[int, int]] = []

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
            player_id = _resolve_player_on_team(cur, team_id, str(player_name))
            if not player_id:
                skipped += 1
                continue
            work.append((player_id, int(sofifa_id)))

    for player_id, sofifa_id in work:
        if max_players and synced >= max_players:
            break
        checked += 1
        try:
            page = _fetch_profile_html(reader, sofifa_id, vid)
            if _is_cloudflare_challenge(page):
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
        except Exception:
            skipped += 1

    out = {
        "checked": checked,
        "synced": synced,
        "skipped": skipped,
        "fifa_edition": fifa_edition,
    }
    if synced == 0 and checked > 0:
        out["hint"] = (
            "Cloudflare likely blocked Selenium — open sofifa.com in Chrome, "
            "pass the check, then retry with --visible or --import-cache"
        )
    return out
