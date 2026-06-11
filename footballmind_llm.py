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


ANALYZE_MODEL = os.environ.get("FOOTBALLMIND_ANALYZE_MODEL",
                               "anthropic/claude-haiku-3-5")  # cheaper for on-demand


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
