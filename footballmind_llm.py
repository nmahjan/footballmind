"""
FootballMind -- LLM gateway for free-form chat.

The rule-based parser in footballmind_app.py stays as the fast path; anything
it can't classify lands here. Claude (via LiteLLM) answers with access to the
same tools the MCP server exposes, executed in-process against the caller's
DB connection.

Requires ANTHROPIC_API_KEY. is_configured() lets the app degrade gracefully
to the canned help reply when no key is set.
"""

import os
import json

MODEL = os.environ.get("FOOTBALLMIND_LLM_MODEL", "anthropic/claude-sonnet-4-6")
MAX_TOOL_ROUNDS = 4

SYSTEM = (
    "You are FootballMind, a football (soccer) intelligence assistant covering "
    "the Premier League, Champions League, and World Cup. Use the tools for any "
    "prediction, standings, squad, or player question; never invent probabilities, "
    "tables, or player facts. When discussing players, use search_players or "
    "get_team_squad for real squad data, then explain their role and why the "
    "team works tactically based on team rating and squad composition. "
    "Be concise: 1-3 sentences unless the user asks for detail (player/team "
    "questions may use a few short paragraphs). If using structure, put each "
    "heading on its own line; avoid long horizontal rules. If a question "
    "is outside football, say so briefly."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "predict_match",
            "description": "Predict a match between two teams (both clubs or both "
                           "national sides). Returns W/D/L probabilities, expected "
                           "goals, confidence, and knockout progression if relevant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "home_team": {"type": "string"},
                    "away_team": {"type": "string"},
                    "stage": {"type": "string",
                              "enum": ["regular_season", "group", "round_of_32",
                                       "round_of_16", "quarter_final", "semi_final",
                                       "third_place", "final"],
                              "default": "regular_season"},
                },
                "required": ["home_team", "away_team"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_standings",
            "description": "Current league table computed from results. "
                           "comp is a competition code: PL, CL, or WC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comp": {"type": "string", "default": "PL"},
                    "season": {"type": "string",
                               "description": "e.g. '2025/26'; omit for all"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_players",
            "description": "Find players by name (partial match). Returns squad "
                           "position, team, age, and team rating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Player name or fragment"},
                    "comp": {"type": "string",
                             "description": "Optional comp filter: WC, PL, CL, etc."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_squad",
            "description": "Full squad for a team with positions grouped. Use to "
                           "explain how a team is built or who plays where.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "comp": {"type": "string",
                             "description": "Optional comp: WC, PL, CL, etc."},
                },
                "required": ["team"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_standout_players",
            "description": "Notable players from strongest teams in a competition. "
                           "position filter: FWD, MID, DEF, GK.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comp": {"type": "string", "default": "WC"},
                    "position": {"type": "string"},
                    "limit": {"type": "integer", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_scorers",
            "description": "Competition top scorers with goals, assists, appearances.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comp": {"type": "string", "default": "PL"},
                    "limit": {"type": "integer", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_formations",
            "description": "Recent formations used by a team (when lineup data exists).",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "comp": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["team"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_match_lineup",
            "description": "Lineups and formations from the most recent finished "
                           "meeting between two teams.",
            "parameters": {
                "type": "object",
                "properties": {
                    "home": {"type": "string"},
                    "away": {"type": "string"},
                    "comp": {"type": "string"},
                },
                "required": ["home", "away"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_predicted_lineup",
            "description": "Predict the most likely starting XI for a team. "
                           "Adjusts for red-card suspensions and injury flags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "comp": {"type": "string", "default": "WC"},
                },
                "required": ["team"],
            },
        },
    },
]


ANALYZE_MODEL = os.environ.get("FOOTBALLMIND_ANALYZE_MODEL",
                               "anthropic/claude-haiku-4-5-20251001")  # cheaper for on-demand


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def analyze_match(home: str, away: str, prediction: dict) -> str:
    """Generate a broadcast-style 3–4 sentence match analysis using Claude.

    Uses claude-haiku for cost efficiency (roughly $0.0003 per call).
    The prediction dict must include home_elo, away_elo, home_xg, away_xg,
    home_form, away_form, h2h, home_win_prob, draw_prob, away_win_prob.
    """
    import litellm

    def form_str(f):
        return " ".join(f) if f else "unknown"

    h2h = prediction.get("h2h") or {}
    h2h_line = (f"{h2h.get('home_wins', 0)}W "
                f"{h2h.get('draws', 0)}D "
                f"{h2h.get('away_wins', 0)}L for {home} "
                f"in last {h2h.get('played', 0)} meetings"
                if h2h.get("played") else "no historical data")

    venue = "neutral venue" if prediction.get("neutral") else f"{home}'s home ground"

    prompt = (
        f"You are a sharp football analyst writing for a match preview. "
        f"Write exactly 3–4 sentences in broadcast style explaining why "
        f"**{prediction['prediction']}** is the expected outcome for "
        f"**{home} vs {away}**. Use the stats below — be specific but punchy. "
        f"Do NOT repeat the numbers verbatim; weave them into the narrative.\n\n"
        f"Stats:\n"
        f"- Elo ratings: {home} {prediction.get('home_elo', '?')} / "
        f"{away} {prediction.get('away_elo', '?')}\n"
        f"- Expected goals: {home} {prediction.get('home_xg', '?')} – "
        f"{away} {prediction.get('away_xg', '?')}\n"
        f"- Win probabilities: {home} {round(prediction['home_win_prob']*100)}% · "
        f"Draw {round(prediction['draw_prob']*100)}% · "
        f"{away} {round(prediction['away_win_prob']*100)}%\n"
        f"- {home} last 5: {form_str(prediction.get('home_form'))}\n"
        f"- {away} last 5: {form_str(prediction.get('away_form'))}\n"
        f"- Head to head: {h2h_line}\n"
        f"- Venue: {venue}\n"
    )

    resp = litellm.completion(
        model=ANALYZE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
    )
    return (resp.choices[0].message.content or "").strip()


def _run_tool(conn, name, args, session_id):
    from footballmind_mcp_predict import _predict_match
    from footballmind_services import (
        get_standings,
        get_standouts,
        get_team_formations,
        get_team_squad,
        get_match_lineup,
        get_top_scorers,
        search_players,
    )
    if name == "predict_match":
        return _predict_match(conn, args["home_team"], args["away_team"], None,
                              args.get("stage", "regular_season"),
                              session_id=session_id)
    if name == "get_standings":
        return get_standings(conn, args.get("comp", "PL"), args.get("season"))
    if name == "search_players":
        return search_players(conn, args["query"], args.get("comp"))
    if name == "get_team_squad":
        return get_team_squad(conn, args["team"], args.get("comp"))
    if name == "list_standout_players":
        return get_standouts(conn, args.get("comp", "WC"),
                             args.get("position"), args.get("limit", 15))
    if name == "get_top_scorers":
        return get_top_scorers(conn, args.get("comp", "PL"), args.get("limit", 15))
    if name == "get_team_formations":
        try:
            return get_team_formations(conn, args["team"], args.get("comp"),
                                       args.get("limit", 5))
        except ValueError as e:
            return {"error": str(e)}
    if name == "get_match_lineup":
        result = get_match_lineup(conn, args["home"], args["away"], args.get("comp"))
        return result or {"error": "No finished match with lineup data found"}
    if name == "get_predicted_lineup":
        from footballmind_lineup import get_predicted_lineup
        try:
            result = get_predicted_lineup(conn, args["team"], args.get("comp", "WC"))
        except ValueError as e:
            return {"error": str(e)}
        return result
    return {"error": f"unknown tool {name}"}


def answer(conn, message, session_id=None):
    """Free-form question -> (reply_text, last_prediction_or_None)."""
    import litellm

    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": message}]
    prediction = None

    for _ in range(MAX_TOOL_ROUNDS):
        resp = litellm.completion(model=MODEL, messages=messages, tools=TOOLS,
                                  max_tokens=700)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip(), prediction

        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            try:
                result = _run_tool(conn, call.function.name, args, session_id)
                if call.function.name == "predict_match":
                    prediction = result
            except ValueError as e:           # e.g. unknown team -> let Claude rephrase
                result = {"error": str(e)}
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result)})

    return ("I couldn't finish answering that -- try rephrasing, or ask for a "
            "specific match prediction or the standings."), prediction
