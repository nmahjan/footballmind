"""
FootballMind -- Flask serving layer.

The HTTP API the React frontend calls. Endpoints:
  POST /api/chat         natural-language entry (session-tracked)
  POST /api/predict      structured prediction (home, away, stage)
  GET  /api/predictions  recent predictions + accuracy summary
  GET  /api/standings    league table computed from results
  GET  /api/history      a session's query log
  GET  /api/health       liveness probe (also a warm-up ping target)

Every request is tied to a session (id + IP) and logged to the queries table.

Env: DATABASE_URL, FRONTEND_ORIGIN (the GitHub Pages URL, for CORS).
Run locally:   flask --app footballmind_app run
Run on Render: gunicorn footballmind_app:app
"""

import os
import re
import json
import time

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded

from footballmind_lineup import get_predicted_lineup
from footballmind_mcp_predict import _predict_match, _TEAM_ALIASES
from footballmind_services import (
    compare_players,
    get_bracket,
    get_fixtures,
    get_recent_match_results,
    get_groups,
    get_match_lineup,
    get_player_profile,
    get_prediction_history,
    get_prediction_results,
    get_prediction_summary,
    get_prediction_calibration,
    get_rankings,
    get_standings,
    get_standouts,
    get_team_formations,
    get_team_squad,
    get_teams_in_comp,
    get_top_scorers,
    search_players,
    _form_score,
    list_availability_flags,
    set_availability_flag,
    clear_availability_flag,
    COMP_LABELS,
    SUPPORTED_COMP_CODES,
    parse_comp_from_text,
)

app = Flask(__name__)
CORS(app, origins=os.environ.get("FRONTEND_ORIGIN", "*"))


# ----------------------------------------------------------------------
# Connection + session plumbing
# ----------------------------------------------------------------------
def get_conn():
    from footballmind_db import get_connection  # lazy so pure-logic imports don't need psycopg
    if "conn" not in g:
        g.conn = get_connection()
    return g.conn


@app.teardown_appcontext
def _close(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")     # Render sits behind a proxy
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "")


# Protects LLM cost on /api/chat. In-memory storage is fine for the single
# Render instance (counters reset on restart, acceptable). Read endpoints are
# explicitly exempted below.
limiter = Limiter(client_ip, app=app, default_limits=["200 per day"],
                  storage_uri="memory://", headers_enabled=True)


def _human_retry(secs: int | None) -> str | None:
    if secs is None or secs <= 0:
        return None
    if secs >= 3600:
        h = (secs + 1799) // 3600
        return f"{h} hour{'s' if h != 1 else ''}"
    if secs >= 60:
        m = (secs + 59) // 60
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{secs} second{'s' if secs != 1 else ''}"


def _rate_limit_message(retry_secs: int | None) -> str:
    path = request.path or ""
    if path.endswith("/chat"):
        base = "You've hit the chat limit (20 requests per hour per IP)."
    elif path.endswith("/analyze"):
        base = "You've hit the deep analysis limit (10 requests per hour per IP)."
    else:
        base = "You've hit a rate limit on this endpoint."
    human = _human_retry(retry_secs)
    if human:
        return f"{base} Try again in about {human}."
    return f"{base} Please wait a bit and try again."


@app.errorhandler(RateLimitExceeded)
def _rate_limited(e):
    retry_secs = None
    try:
        cl = limiter.current_limit
        if cl:
            retry_secs = max(0, int(cl.reset_at - time.time()))
    except Exception:
        pass
    message = _rate_limit_message(retry_secs)
    resp = jsonify({
        "error": "rate_limit_exceeded",
        "message": message,
        "retry_after_seconds": retry_secs,
        "limit": getattr(e, "description", None),
    })
    resp.status_code = 429
    if retry_secs:
        resp.headers["Retry-After"] = str(retry_secs)
    return resp


def touch_session(conn, session_id, ip):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (id, ip_address) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET last_active = now(), "
            "  query_count = sessions.query_count + 1", (session_id, ip))
    conn.commit()


def log_query(conn, session_id, query, response, qtype, entities, ms):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO queries (session_id, query, response, query_type, "
            " entities_mentioned, response_time_ms) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
            (session_id, query, response, qtype, json.dumps(entities), ms))
    conn.commit()


def _load_chat_history(conn, session_id: str, limit: int = 6) -> list[dict]:
    """Recent turns from the queries log (oldest first)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT query, response FROM queries "
            "WHERE session_id = %s ORDER BY timestamp DESC LIMIT %s",
            (session_id, limit))
        rows = cur.fetchall()
    turns = []
    for query, response in reversed(rows):
        if query:
            turns.append({"role": "user", "content": query})
        if response:
            turns.append({"role": "assistant", "content": response})
    return turns


def _normalize_history(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for turn in raw[-12:]:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


_VALID_COMPS = SUPPORTED_COMP_CODES
_COMP_LABELS = COMP_LABELS


def _resolve_chat_comp(data, default: str = "WC") -> str:
    raw = str(data.get("comp") or default).strip().upper()
    return raw if raw in _VALID_COMPS else default


def _admin_key() -> str | None:
    return os.environ.get("FOOTBALLMIND_ADMIN_KEY") or os.environ.get("MCP_API_KEY") or None


def _require_admin():
    key = _admin_key()
    if not key:
        return jsonify({"error": "Admin API not configured on server"}), 503
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else auth
    header_key = request.headers.get("X-Admin-Key", "")
    if token != key and header_key != key:
        return jsonify({"error": "Unauthorized"}), 401
    return None


_FOLLOWUP = re.compile(
    r"^\s*(?:"
    r"explain(?:\s+(?:that|this|more|why|how))?|"
    r"why(?:\s+(?:is\s+that|though|not|him|her|them))?|"
    r"how\s+so|tell\s+me\s+more|go\s+on|elaborate|"
    r"what\s+do\s+you\s+mean|can\s+you\s+explain|more\s+detail|"
    r"break\s+(?:that|it)\s+down|expand(?:\s+on\s+that)?|"
    r"what\s+about|and\s+\w+|continue"
    r")\s*[\?\.!]*$",
    re.I)


def _is_followup(message: str, history: list[dict]) -> bool:
    if not history:
        return False
    text = message.strip()
    if _FOLLOWUP.match(text):
        return True
    words = text.lower().split()
    return len(words) <= 3 and text.lower().rstrip("?.!") in {
        "explain", "why", "how", "more", "continue", "elaborate",
    }


def _last_compare_from_history(history: list[dict]) -> tuple[str, str] | None:
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        players = _parse_player_compare(turn.get("content") or "")
        if players:
            return players
    return None


def _comp_switch_compare(message: str, history: list[dict]) -> str | None:
    """Competition named in a follow-up after a player compare, e.g. 'what about La Liga'."""
    if not history or not _last_compare_from_history(history):
        return None
    comp = parse_comp_from_text(message)
    if not comp:
        return None
    low = message.lower()
    if any(p in low for p in (
        "what about", "how about", "and in", "in the", "for the", " for ",
        "switch", "instead",
    )):
        return comp
    # short follow-up that is mostly just a competition name
    if len(low.split()) <= 6:
        return comp
    return None


# ----------------------------------------------------------------------
# Pure logic (unit-testable, no DB) -- rule-based intent fast path
# ----------------------------------------------------------------------
_VS = re.compile(
    r"^\s*(?:can you |please )?(?:predict|forecast)?\s*(.+?)\s+"
    r"(?:vs\.?|versus|v|against)\s+(.+?)\s*[\?\.!]*$", re.I)
_VENUE_SUFFIX = re.compile(r"\s+(?:in|at)\s+(.+?)\s*[\?\.!]*$", re.I)
# Common host cities -> national team name (football-data.org labels)
_VENUE_CITIES = {
    "seoul": "South Korea",
    "busan": "South Korea",
    "mexico city": "Mexico",
    "cdmx": "Mexico",
    "guadalajara": "Mexico",
    "monterrey": "Mexico",
    "azteca": "Mexico",
    "estadio azteca": "Mexico",
    "wembley": "England",
    "london": "England",
    "paris": "France",
    "berlin": "Germany",
    "munich": "Germany",
    "madrid": "Spain",
    "barcelona": "Spain",
    "rome": "Italy",
    "milan": "Italy",
    "tokyo": "Japan",
    "doha": "Qatar",
    "sydney": "Australia",
    "melbourne": "Australia",
}


def _extract_venue(message: str) -> tuple[str, str | None]:
    """Pull trailing 'in Mexico' / 'at Wembley' off a predict query."""
    m = _VENUE_SUFFIX.search(message)
    if not m:
        return message, None
    venue = m.group(1).strip().rstrip("?!.")
    base = (message[:m.start()] + message[m.end():]).strip().rstrip("?!.")
    return base, venue


def _norm_team_label(name: str) -> str:
    return _TEAM_ALIASES.get(name.lower().strip(), name.strip()).lower()


def _venue_matches_team(venue: str, team: str) -> bool:
    """True when a location phrase refers to a team's home country/ground."""
    v = _norm_team_label(venue)
    t = _norm_team_label(team)
    if v == t or v in t or t in v:
        return True
    # "mexico city" / city aliases
    mapped = _VENUE_CITIES.get(v)
    if mapped and _norm_team_label(mapped) == t:
        return True
    v0, t0 = v.split()[0], t.split()[0]
    return v0 == t0 or v0 in t or t0 in v


def _resolve_prediction_venue(home: str, away: str, venue: str | None,
                              explicit_neutral: bool | None,
                              message: str) -> tuple[str, str, bool | None, str | None]:
    """Decide home/away orientation and neutral flag.

    Returns (home, away, neutral, venue_label).
    Priority: UI toggle > explicit neutral/home phrases > 'in Mexico' host detection > auto.
    """
    low = message.lower()
    venue_label = None

    if explicit_neutral is not None:
        neutral = bool(explicit_neutral)
        if venue and not neutral:
            venue_label = venue
        return home, away, neutral, venue_label

    if any(w in low for w in ("neutral", "at a neutral", "at neutral", "neutral venue")):
        return home, away, True, None
    if any(w in low for w in ("at home", "home ground", "home stadium")):
        return home, away, False, None

    if venue:
        if _venue_matches_team(venue, home):
            return home, away, False, venue
        if _venue_matches_team(venue, away):
            # Host listed second — flip so the model's home side is the host.
            return away, home, False, venue
        venue_label = venue

    return home, away, None, venue_label


def _venue_note(neutral: bool | None, venue_label: str | None, home: str) -> str:
    if neutral is True:
        return " (neutral venue)"
    if neutral is False:
        if venue_label:
            return f" ({home} at home — {venue_label})"
        return f" ({home} at home)"
    return ""


def _clean_team(s):
    s = s.strip()
    # strip leading question/filler words before the team name
    s = re.sub(r"^(who\s+will\s+win\s+|who\s+wins\s+|will\s+|can\s+|"
               r"what\s+about\s+|how\s+about\s+|the\s+|a\s+)", "", s, flags=re.I)
    # strip trailing context filler and venue clauses stuck on a team name
    s = re.sub(r"\s+(?:in|at)\s+.+$", "", s, flags=re.I)
    s = re.sub(r"\s+(match|game|fixture|this weekend|today|tomorrow|on \w+)\b.*$",
               "", s, flags=re.I)
    return s.strip()


_COMPARE_VS = re.compile(
    r"^\s*(?:compare|comparison(?:\s+of)?)\s+(.+?)\s+(?:vs\.?|versus|v)\s+(.+?)\s*[\?\.!]*$",
    re.I)
_PLAYER_VS = re.compile(
    r"^\s*(?:who(?:'s|\s+is)\s+better[,:]?\s*)?(.+?)\s+(?:vs\.?|versus|v|or)\s+(.+?)\s*[\?\.!]*$",
    re.I)
_PREDICT_HINTS = ("predict", "forecast", "who will win", "who wins", "match", "fixture", "game")


_COMPARE_TOPIC_WORDS = (
    "what about", "how about", "their ", "the ", "is it", "does ", "did ",
    "passing", "completion", "rate", "style", "tactics", "possession",
    "defence", "defense", "pressing", "formation", "good ", "bad ",
)


def _looks_like_player_name(name: str) -> bool:
    """Reject sentence fragments mistaken for player names."""
    if not name or len(name) > 45:
        return False
    if any(c in name for c in "?:"):
        return False
    if any(w in name.lower() for w in _COMPARE_TOPIC_WORDS):
        return False
    return len(name.split()) <= 5


def _parse_player_compare(message: str) -> tuple[str, str] | None:
    """Extract two player names from a comparison query, or None."""
    low = message.lower().strip()
    if any(h in low for h in _PREDICT_HINTS):
        return None
    if any(w in low for w in _COMPARE_TOPIC_WORDS):
        return None
    m = _COMPARE_VS.match(message.strip())
    if m:
        a, b = _clean_team(m.group(1)), _clean_team(m.group(2))
        if _looks_like_player_name(a) and _looks_like_player_name(b):
            return a, b
        return None
    has_compare_hint = any(h in low for h in (
        "compare", " vs ", " versus ", "who is better", "who's better",
    ))
    if has_compare_hint:
        m = _PLAYER_VS.match(message.strip())
        if m:
            a, b = _clean_team(m.group(1)), _clean_team(m.group(2))
            if _looks_like_player_name(a) and _looks_like_player_name(b):
                return a, b
    # "Messi or Ronaldo" — short name-only phrasing
    if " or " in low and len(low.split()) <= 6:
        m = _PLAYER_VS.match(message.strip())
        if m:
            a, b = _clean_team(m.group(1)), _clean_team(m.group(2))
            if _looks_like_player_name(a) and _looks_like_player_name(b):
                return a, b
    return None


def _format_player_compare(result: dict) -> str:
    """Readable comparison from compare_players() output."""
    a, b = result["player_a"], result["player_b"]
    comp = result.get("comp") or "WC"
    note = result.get("comparison_note")

    def block(p):
        header_bits = [f"**{p['name']}**"]
        if p.get("position"):
            header_bits.append(p["position"])
        if p.get("age"):
            header_bits.append(f"{p['age']}y")
        if p.get("nationality"):
            header_bits.append(p["nationality"])
        lines = [" · ".join(header_bits)]
        if p.get("national_team"):
            nr = p.get("national_rating")
            elo = f" (Elo {nr})" if nr else ""
            lines.append(f"National: **{p['national_team']}**{elo}")
        if p.get("club"):
            cr = p.get("club_rating")
            elo = f" (Elo {cr})" if cr else ""
            lines.append(f"Club: **{p['club']}**{elo}")
        cs = p.get("club_season") or {}
        if cs.get("goals") is not None or cs.get("assists"):
            cc = cs.get("comp_code", "?")
            lines.append(
                f"Club form ({cc}): {cs.get('goals', 0)}G · "
                f"{cs.get('assists', 0)}A · {cs.get('appearances', 0)} apps"
            )
        if p.get("goals") is not None and comp:
            season = p.get("comp_season")
            hist = " (synced season)" if p.get("comp_stats_are_historical") else ""
            label = f"{comp} stats ({season}){hist}" if season else f"{comp} stats"
            lines.append(
                f"{label}: {p['goals']}G · {p.get('assists', 0)}A · "
                f"{p.get('appearances', 0)} apps"
            )
        elif comp and not cs:
            lines.append(f"No synced {comp} stats on file for this player.")
        elif not cs and p.get("team_rating"):
            lines.append(f"Squad Elo: {round(p['team_rating'])}")
        return "\n".join(lines)

    parts = []
    if note:
        parts.append(f"*{note}*")
    parts.extend([block(a), block(b)])

    fa, fb = _form_score(a), _form_score(b)
    ra = a.get("national_rating") or a.get("team_rating") or 0
    rb = b.get("national_rating") or b.get("team_rating") or 0
    if fa or fb:
        edge = a["name"] if fa >= fb else b["name"]
        parts.append(f"On club season output, **{edge}** has the stronger numbers.")
    elif a.get("goals") is not None or b.get("goals") is not None:
        edge = a["name"] if fa >= fb else b["name"]
        parts.append(f"On {comp} stats, **{edge}** has the stronger output so far.")
    elif ra or rb:
        edge = a["name"] if ra >= rb else b["name"]
        parts.append(f"By national team strength (Elo), **{edge}**'s side rates higher.")
    return "\n\n".join(parts)


def _parse_knockout_stage(message: str) -> str | None:
    """Map natural language to a knockout stage for predictions."""
    low = message.lower()
    if any(x in low for x in ("round of 32", "last 32", " r32")):
        return "round_of_32"
    if any(x in low for x in ("round of 16", "last 16", " r16")):
        return "round_of_16"
    if any(x in low for x in ("quarter-final", "quarter final", " qf")):
        return "quarter_final"
    if any(x in low for x in ("semi-final", "semi final", " sf")):
        return "semi_final"
    if " final" in low and "semi" not in low and "quarter" not in low:
        return "final"
    return None


def parse_intent(message):
    low = message.lower()
    if ("bracket" in low or "knockout tree" in low
            or ("knockout" in low and any(x in low for x in ("show", "draw", "tree", "round")))):
        return {"type": "bracket"}
    if "standing" in low or "table" in low or "league position" in low:
        return {"type": "standings"}
    players = _parse_player_compare(message)
    if players:
        return {"type": "compare", "player_a": players[0], "player_b": players[1]}
    base, venue = _extract_venue(message)
    m = _VS.match(base)
    if m and any(h in low for h in ("predict", "forecast", "who will win",
                                    "who wins", " vs", "versus", "against")):
        if any(h in low for h in ("compare", "who is better", "who's better")):
            pass
        else:
            return {"type": "predict",
                    "home": _clean_team(m.group(1)),
                    "away": _clean_team(m.group(2)),
                    "venue": venue,
                    "stage": _parse_knockout_stage(message)}
    return {"type": "unknown"}


def _standings(conn, comp_code, season=None):
    return get_standings(conn, comp_code, season)


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.post("/api/predict")
@limiter.exempt
def api_predict():
    data = request.get_json(force=True) or {}
    if not data.get("home") or not data.get("away"):
        return jsonify({"error": "home and away are required"}), 400
    if data.get("session_id"):                  # predictions.session_id is a FK
        touch_session(get_conn(), data["session_id"], client_ip())
    # neutral: explicit bool from caller; None = auto-detect
    neutral_raw = data.get("neutral")
    neutral = bool(neutral_raw) if neutral_raw is not None else None
    try:
        result = _predict_match(get_conn(), data["home"], data["away"],
                                data.get("match_date"),
                                data.get("stage", "regular_season"),
                                session_id=data.get("session_id"),
                                neutral=neutral,
                                comp=data.get("comp"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


@app.post("/api/chat")
@limiter.limit("20 per hour")
def api_chat():
    t0 = time.time()
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    session_id = data.get("session_id") or "anon"
    if not message:
        return jsonify({"error": "message is required"}), 400

    conn = get_conn()
    touch_session(conn, session_id, client_ip())
    chat_comp = _resolve_chat_comp(data)
    history = _normalize_history(data.get("history"))
    if not history:
        history = _load_chat_history(conn, session_id)
    intent = parse_intent(message)
    entities, prediction, bracket_payload = {"comp": chat_comp}, None, None

    switch_comp = _comp_switch_compare(message, history)
    if switch_comp:
        players = _last_compare_from_history(history)
        entities = {"player_a": players[0], "player_b": players[1], "comp": switch_comp}
        result = compare_players(conn, players[0], players[1], switch_comp)
        if result.get("error"):
            reply = result["error"]
        else:
            reply = _format_player_compare(result)
        intent = {"type": "compare"}
    elif _is_followup(message, history):
        import footballmind_llm
        if footballmind_llm.is_configured():
            reply, prediction = footballmind_llm.answer_followup(
                message, history, comp=chat_comp)
            intent = {"type": "followup"}
        else:
            reply = ("Follow-up questions need the AI chat enabled. "
                     "Ask your full question in one message, e.g. "
                     "\"Explain why Messi rates higher than Ronaldo for Argentina.\"")
            intent = {"type": "followup"}
    elif intent["type"] == "bracket":
        bracket_comp = chat_comp if chat_comp in ("WC", "CL") else "WC"
        bracket_payload = get_bracket(conn, bracket_comp)
        entities = {"competition": bracket_comp, "comp": bracket_comp}
        comp_label = _COMP_LABELS.get(bracket_comp, bracket_comp)
        reply = f"{comp_label} knockout bracket — scroll the tree below."
    elif intent["type"] == "predict":
        explicit_neutral = data.get("neutral")
        if explicit_neutral is not None:
            explicit_neutral = bool(explicit_neutral)
        home, away, neutral, venue_label = _resolve_prediction_venue(
            intent["home"], intent["away"], intent.get("venue"),
            explicit_neutral, message)
        entities = {"home": home, "away": away}
        if venue_label:
            entities["venue"] = venue_label
        try:
            prediction = _predict_match(conn, home, away,
                                        None,
                                        intent.get("stage") or "regular_season",
                                        session_id=session_id,
                                        neutral=neutral, comp=chat_comp)
            note = _venue_note(neutral if neutral is not None else prediction.get("neutral"),
                               venue_label, home)
            reply = (f"{prediction['prediction']} "
                     f"({round(prediction['confidence'] * 100)}% confidence){note}. "
                     f"{prediction['reasoning']}")
        except ValueError as e:
            reply = f"I couldn't run that prediction: {e}"
    elif intent["type"] == "compare":
        entities = {"player_a": intent["player_a"], "player_b": intent["player_b"],
                    "comp": chat_comp}
        result = compare_players(conn, intent["player_a"], intent["player_b"], chat_comp)
        if result.get("error"):
            reply = result["error"]
        else:
            reply = _format_player_compare(result)
    elif intent["type"] == "standings":
        table = _standings(conn, chat_comp)
        entities = {"competition": chat_comp, "comp": chat_comp}
        comp_label = _COMP_LABELS.get(chat_comp, chat_comp)
        if table:
            top = ", ".join(
                f"{t['rank']}. {t['team']} ({t['Pts']})"
                + (f" [{t['zone']['short']}]" if t.get("zone") else "")
                for t in table[:5]
            )
            rel = [t for t in table if (t.get("zone") or {}).get("id") == "rel"]
            rel_note = (
                f" Relegation zone: {', '.join(t['team'] for t in rel)}."
                if rel else ""
            )
            reply = f"Top of the {comp_label} table: {top}.{rel_note}"
        else:
            reply = f"No {comp_label} results recorded yet."
    else:
        import footballmind_llm                 # lazy: litellm is heavy and optional
        if footballmind_llm.is_configured():
            reply, prediction = footballmind_llm.answer(
                conn, message, session_id=session_id, history=history, comp=chat_comp)
            intent = {"type": "llm"}
        else:
            reply = ("I can predict matches (e.g. \"Predict Arsenal vs Chelsea\") "
                     "or show the standings (\"show the table\"). Set "
                     "ANTHROPIC_API_KEY to enable free-form questions.")

    ms = int((time.time() - t0) * 1000)
    log_query(conn, session_id, message, reply, intent["type"], entities, ms)
    out = {"reply": reply, "intent": intent["type"], "prediction": prediction}
    if bracket_payload is not None:
        out["bracket"] = bracket_payload
        out["bracket_comp"] = entities.get("comp", "WC")
    return jsonify(out)


@app.get("/api/standings")
@limiter.exempt
def api_standings():
    return jsonify(_standings(get_conn(), request.args.get("comp", "PL"),
                              request.args.get("season")))


@app.get("/api/predictions/calibration")
@limiter.exempt
def api_predictions_calibration():
    """Confidence calibration bins for graded predictions (one row per match)."""
    return jsonify(get_prediction_calibration(get_conn()))


@app.get("/api/predictions")
@limiter.exempt
def api_predictions():
    limit = min(int(request.args.get("limit", 25)), 100)
    conn = get_conn()
    if request.args.get("finished") in ("1", "true", "yes"):
        results = get_prediction_results(conn, limit)
        return jsonify({"results": results, "summary": get_prediction_summary(conn)})
    if request.args.get("history") in ("1", "true", "yes"):
        payload = get_prediction_history(
            conn,
            comp=request.args.get("comp") or None,
            season=request.args.get("season") or request.args.get("year") or None,
            limit=limit,
        )
        payload["summary"] = get_prediction_summary(conn)
        return jsonify(payload)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, "
            "       COALESCE(thp.name, thm.name) AS home, "
            "       COALESCE(tap.name, tam.name) AS away, "
            "       p.home_win_prob, p.draw_prob, p.away_win_prob, "
            "       p.home_advance_prob, p.confidence, "
            "       p.actual_home_goals, p.actual_away_goals, p.was_correct, p.created_at "
            "FROM predictions p "
            "LEFT JOIN matches m ON m.id = p.match_id "
            "LEFT JOIN teams thp ON thp.id = p.home_team_id "
            "LEFT JOIN teams tap ON tap.id = p.away_team_id "
            "LEFT JOIN teams thm ON thm.id = m.home_team_id "
            "LEFT JOIN teams tam ON tam.id = m.away_team_id "
            "ORDER BY p.created_at DESC LIMIT %s", (limit,))
        cols = [d[0] for d in cur.description]
        preds = [dict(zip(cols, r)) for r in cur.fetchall()]
    return jsonify({"predictions": preds, "summary": get_prediction_summary(conn)})


@app.get("/api/history")
@limiter.exempt
def api_history():
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT query, response, query_type, timestamp FROM queries "
            "WHERE session_id = %s ORDER BY timestamp DESC LIMIT 50", (session_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return jsonify({"history": rows})


@app.get("/api/groups")
@limiter.exempt
def api_groups():
    """Per-group standings for a tournament (default WC). Returns {A: [...], B: [...]}."""
    comp = request.args.get("comp", "WC")
    return jsonify({"groups": get_groups(get_conn(), comp), "comp": comp})


@app.get("/api/fixtures")
@limiter.exempt
def api_fixtures():
    """Upcoming matches for a competition. Defaults to WC, limit 16."""
    from footballmind_services import enrich_fixtures_with_previews

    comp = request.args.get("comp", "WC")
    limit = min(int(request.args.get("limit", 16)), 64)
    preview = request.args.get("preview", "1").lower() not in ("0", "false", "no")
    conn = get_conn()
    fixtures = get_fixtures(conn, comp, limit)
    if preview:
        enrich_fixtures_with_previews(conn, fixtures, comp)
    return jsonify({"fixtures": fixtures, "comp": comp})


@app.get("/api/results")
@limiter.exempt
def api_results():
    """Recent finished matches for a competition (newest first)."""
    comp = request.args.get("comp", "WC")
    limit = min(int(request.args.get("limit", 40)), 100)
    results = get_recent_match_results(get_conn(), comp, limit)
    return jsonify({"results": results, "comp": comp})


@app.get("/api/rankings")
@limiter.exempt
def api_rankings():
    """National team Elo power rankings, sorted strongest first."""
    comp = request.args.get("comp", "WC")
    limit = min(int(request.args.get("limit", 48)), 100)
    rankings = get_rankings(get_conn(), comp, limit)
    return jsonify({"rankings": rankings, "comp": comp})


@app.get("/api/standouts")
@limiter.exempt
def api_standouts():
    """Key players from top-rated teams in a competition, grouped by position."""
    comp = request.args.get("comp", "WC")
    pos_filter = request.args.get("position", "").upper() or None
    limit = min(int(request.args.get("limit", 20)), 60)
    standouts = get_standouts(get_conn(), comp, pos_filter, limit)
    return jsonify({"standouts": standouts, "comp": comp})


@app.get("/api/players/search")
@limiter.exempt
def api_players_search():
    q = request.args.get("q", "").strip()
    comp = request.args.get("comp") or None
    limit = min(int(request.args.get("limit", 15)), 30)
    players = search_players(get_conn(), q, comp, limit)
    return jsonify({"players": players, "query": q, "comp": comp})


@app.get("/api/players/squad")
@limiter.exempt
def api_players_squad():
    team = request.args.get("team", "").strip()
    if not team:
        return jsonify({"error": "team is required"}), 400
    comp = request.args.get("comp") or None
    try:
        squad = get_team_squad(get_conn(), team, comp)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(squad)


@app.get("/api/players/teams")
@limiter.exempt
def api_players_teams():
    comp = request.args.get("comp", "WC")
    teams = get_teams_in_comp(get_conn(), comp)
    return jsonify({"teams": teams, "comp": comp})


@app.get("/api/players/profile")
@limiter.exempt
def api_players_profile():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    comp = request.args.get("comp") or None
    profile = get_player_profile(get_conn(), name, comp)
    if not profile:
        return jsonify({"error": f"No player found matching {name!r}"}), 404
    return jsonify({"player": profile, "comp": comp})


@app.get("/api/players/scorers")
@limiter.exempt
def api_players_scorers():
    comp = request.args.get("comp", "PL")
    limit = min(int(request.args.get("limit", 20)), 50)
    scorers = get_top_scorers(get_conn(), comp, limit)
    return jsonify({"scorers": scorers, "comp": comp})


@app.get("/api/players/formations")
@limiter.exempt
def api_players_formations():
    team = request.args.get("team", "").strip()
    if not team:
        return jsonify({"error": "team is required"}), 400
    comp = request.args.get("comp") or None
    limit = min(int(request.args.get("limit", 5)), 10)
    try:
        formations = get_team_formations(get_conn(), team, comp, limit)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"team": team, "comp": comp, "formations": formations})


@app.get("/api/players/predicted-lineup")
@limiter.exempt
def api_players_predicted_lineup():
    team = request.args.get("team", "").strip()
    if not team:
        return jsonify({"error": "team is required"}), 400
    comp = request.args.get("comp", "WC")
    try:
        result = get_predicted_lineup(get_conn(), team, comp)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


@app.get("/api/players/availability")
@limiter.exempt
def api_players_availability():
    """Manual injury/doubt flags for a team (suspensions are computed at runtime)."""
    team = request.args.get("team", "").strip()
    if not team:
        return jsonify({"error": "team is required"}), 400
    comp = _resolve_chat_comp({"comp": request.args.get("comp", "WC")})
    try:
        flags = list_availability_flags(get_conn(), team, comp)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"team": team, "comp": comp, "flags": flags})


@app.post("/api/admin/availability")
@limiter.limit("60 per hour")
def api_admin_availability_set():
    denied = _require_admin()
    if denied:
        return denied
    data = request.get_json(force=True) or {}
    player = (data.get("player") or data.get("name") or "").strip()
    team = (data.get("team") or "").strip()
    comp = _resolve_chat_comp(data)
    status = (data.get("status") or "").strip()
    reason = (data.get("reason") or "").strip() or None
    if not player or not team or not status:
        return jsonify({"error": "player, team, and status are required"}), 400
    try:
        result = set_availability_flag(get_conn(), player, team, comp, status, reason)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


@app.delete("/api/admin/availability")
@limiter.limit("60 per hour")
def api_admin_availability_clear():
    denied = _require_admin()
    if denied:
        return denied
    data = request.get_json(force=True) or {}
    player = (data.get("player") or data.get("name") or "").strip()
    team = (data.get("team") or "").strip()
    comp = _resolve_chat_comp(data)
    if not player or not team:
        return jsonify({"error": "player and team are required"}), 400
    try:
        result = clear_availability_flag(get_conn(), player, team, comp)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


@app.get("/api/players/lineup")
@limiter.exempt
def api_players_lineup():
    home = request.args.get("home", "").strip()
    away = request.args.get("away", "").strip()
    if not home or not away:
        return jsonify({"error": "home and away are required"}), 400
    comp = request.args.get("comp") or None
    lineup = get_match_lineup(get_conn(), home, away, comp)
    if not lineup:
        return jsonify({"error": f"No finished match found for {home} vs {away}"}), 404
    return jsonify(lineup)


@app.get("/api/bracket")
@limiter.exempt
def api_bracket():
    """Knockout bracket for a tournament. Returns rounds in order."""
    comp = request.args.get("comp", "WC")
    bracket = get_bracket(get_conn(), comp)
    return jsonify({"bracket": bracket, "comp": comp})


@app.post("/api/analyze")
@limiter.limit("10 per hour")   # stricter: each call hits Claude
def api_analyze():
    """Generate a Claude-written match analysis for a prediction already made."""
    data = request.get_json(force=True) or {}
    home = data.get("home")
    away = data.get("away")
    prediction = data.get("prediction")
    if not home or not away or not prediction:
        return jsonify({"error": "home, away, and prediction are required"}), 400
    import footballmind_llm
    if not footballmind_llm.is_configured():
        return jsonify({"error": "ANTHROPIC_API_KEY not configured on the server"}), 503
    comp = data.get("comp") or prediction.get("comp")
    if not prediction.get("stakes"):
        from footballmind_mcp_predict import _resolve_team
        from footballmind_stakes import compute_match_stakes
        conn = get_conn()
        with conn.cursor() as cur:
            try:
                home_id, _ = _resolve_team(cur, home)
                away_id, _ = _resolve_team(cur, away)
                prediction = dict(prediction)
                prediction["stakes"] = compute_match_stakes(
                    conn, comp, home_id, away_id, home, away,
                    prediction.get("stage", "regular_season"))
                prediction.setdefault("comp", comp)
            except ValueError:
                pass
    try:
        analysis = footballmind_llm.analyze_match(home, away, prediction)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500
    return jsonify({"analysis": analysis})


@app.get("/api/sync-health")
@limiter.exempt
def sync_health():
    try:
        from footballmind_sync_status import get_sync_health
        return jsonify(get_sync_health(get_conn()))
    except Exception as e:
        return jsonify({"error": str(e), "jobs": []}), 500


@app.get("/api/health")
@limiter.exempt
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
