"""
FootballMind -- MCP server entrypoint.

Exposes the prediction stack as MCP tools (stdio transport). Register this
with any MCP client, e.g. in Cursor / Claude Desktop:

    {"command": "/path/to/.venv/bin/python", "args": ["/path/to/server.py"]}

The tool wrappers stay thin on purpose: all logic lives in plain functions
(_predict_match) that are unit-testable without an MCP client.
"""

from mcp.server.fastmcp import FastMCP

from footballmind_db import get_connection
from footballmind_mcp_predict import _predict_match

mcp = FastMCP("footballmind")


@mcp.tool()
def predict_match(home_team: str, away_team: str, match_date: str | None = None,
                  stage: str = "regular_season",
                  session_id: str | None = None) -> dict:
    """Predict a football match between two teams (both clubs, or both
    national sides). Returns W/D/L probabilities, expected goals, confidence,
    and -- for knockout stages -- the probability of each side advancing.
    stage is one of: regular_season, group, round_of_32, round_of_16,
    quarter_final, semi_final, third_place, final."""
    with get_connection() as conn:
        return _predict_match(conn, home_team, away_team, match_date,
                              stage, session_id)


if __name__ == "__main__":
    mcp.run()
