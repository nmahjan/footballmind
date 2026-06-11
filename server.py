"""
FootballMind MCP server — local (stdio) and remote (streamable-http).

Local Cursor registration (~/.cursor/mcp.json):
    "footballmind": {
      "command": ".../.venv/bin/python",
      "args": [".../server.py"],
      "env": { "DATABASE_URL": "..." }
    }

Remote (Render / streamable-http):
    "footballmind-remote": {
      "type": "http",
      "url": "https://YOUR-RENDER-URL.onrender.com/mcp",
      "headers": { "Authorization": "Bearer YOUR_MCP_API_KEY" }
    }

Run locally:
    python server.py                          # stdio (default)
    python server.py --transport streamable-http --port 8001
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from footballmind_db import get_connection
from footballmind_mcp_predict import _predict_match
from footballmind_services import (
    get_bracket,
    get_fixtures,
    get_groups,
    get_match_lineup as fetch_match_lineup,
    get_player_profile as lookup_player,
    get_rankings,
    get_standings,
    get_standouts,
    get_team_formations as fetch_team_formations,
    get_team_squad as fetch_team_squad,
    get_top_scorers as fetch_top_scorers,
    search_players as find_players,
)

load_dotenv()

mcp = FastMCP(
    "footballmind",
    instructions=(
        "FootballMind: match predictions, league tables, fixtures, tournament "
        "brackets, and national team rankings. Competition codes: PL, PD, BL1, "
        "SA, FL1, CL, DED, WC."
    ),
)


@mcp.tool()
def predict_match(
    home_team: str,
    away_team: str,
    match_date: str | None = None,
    stage: str = "regular_season",
    neutral: bool | None = None,
    session_id: str | None = None,
) -> dict:
    """Predict W/D/L probabilities and expected goals for a football match.
    stage: regular_season, group, round_of_16, quarter_final, semi_final, final.
    Set neutral=True for World Cup / neutral-venue games."""
    with get_connection() as conn:
        return _predict_match(
            conn, home_team, away_team, match_date, stage,
            session_id=session_id, neutral=neutral,
        )


@mcp.tool()
def get_league_standings(comp: str = "PL", season: str | None = None) -> list:
    """League table from recorded results. comp: PL, PD, BL1, SA, FL1, CL, DED."""
    with get_connection() as conn:
        return get_standings(conn, comp, season)


@mcp.tool()
def list_fixtures(comp: str = "WC", limit: int = 16) -> list:
    """Upcoming fixtures for a competition (includes live flag when in progress)."""
    with get_connection() as conn:
        return get_fixtures(conn, comp, limit)


@mcp.tool()
def get_tournament_groups(comp: str = "WC") -> dict:
    """Group-stage standings for a tournament. Returns {group_letter: [teams]}."""
    with get_connection() as conn:
        return get_groups(conn, comp)


@mcp.tool()
def get_tournament_bracket(comp: str = "WC") -> list:
    """Knockout bracket rounds (Final first). comp: WC or CL."""
    with get_connection() as conn:
        return get_bracket(conn, comp)


@mcp.tool()
def get_power_rankings(comp: str = "WC", limit: int = 48) -> list:
    """National team Elo power rankings for teams in a competition."""
    with get_connection() as conn:
        return get_rankings(conn, comp, limit)


@mcp.tool()
def list_standout_players(
    comp: str = "WC",
    position: str | None = None,
    limit: int = 20,
) -> list:
    """Notable squad players from top-rated teams. position: FWD, MID, DEF, GK."""
    with get_connection() as conn:
        return get_standouts(conn, comp, position, limit)


@mcp.tool()
def search_players(
    query: str,
    comp: str | None = None,
    limit: int = 15,
) -> list:
    """Find players by name. comp optional: WC, PL, CL, etc."""
    with get_connection() as conn:
        return find_players(conn, query, comp, limit)


@mcp.tool()
def get_team_squad(team: str, comp: str | None = None) -> dict:
    """Full squad for a team with positions. Use for tactical / roster questions."""
    with get_connection() as conn:
        return fetch_team_squad(conn, team, comp)


@mcp.tool()
def get_player_profile(name: str, comp: str | None = None) -> dict:
    """Look up a single player by name (includes goals/assists when synced)."""
    with get_connection() as conn:
        profile = lookup_player(conn, name, comp)
        if profile is None:
            return {"error": f"No player found matching {name!r}"}
        return profile


@mcp.tool()
def get_top_scorers(comp: str = "PL", limit: int = 20) -> list:
    """Competition top scorers with goals, assists, and appearances."""
    with get_connection() as conn:
        return fetch_top_scorers(conn, comp, limit)


@mcp.tool()
def get_team_formations(team: str, comp: str | None = None, limit: int = 5) -> list:
    """Recent formations for a team (when match lineup data is available)."""
    with get_connection() as conn:
        return fetch_team_formations(conn, team, comp, limit)


@mcp.tool()
def get_match_lineup(home: str, away: str, comp: str | None = None) -> dict:
    """Lineups from the latest finished meeting between two teams."""
    with get_connection() as conn:
        result = fetch_match_lineup(conn, home, away, comp)
        if result is None:
            return {"error": f"No finished match found for {home} vs {away}"}
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="FootballMind MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8001")))
    args = parser.parse_args()

    if args.transport != "stdio":
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
