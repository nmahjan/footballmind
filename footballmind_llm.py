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

MODEL = os.environ.get("FOOTBALLMIND_LLM_MODEL", "anthropic/claude-sonnet-4-5")
MAX_TOOL_ROUNDS = 4

SYSTEM = (
    "You are FootballMind, a football (soccer) intelligence assistant covering "
    "the Premier League, Champions League, and World Cup. Use the tools for any "
    "prediction or standings question; never invent probabilities or tables. "
    "Be concise: 1-3 sentences unless the user asks for detail. If a question "
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
]


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _run_tool(conn, name, args, session_id):
    from footballmind_mcp_predict import _predict_match
    from footballmind_app import _standings
    if name == "predict_match":
        return _predict_match(conn, args["home_team"], args["away_team"], None,
                              args.get("stage", "regular_season"),
                              session_id=session_id)
    if name == "get_standings":
        return _standings(conn, args.get("comp", "PL"), args.get("season"))
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
