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

from footballmind_lineup import get_predicted_lineup
from footballmind_mcp_predict import _predict_match, _TEAM_ALIASES
from footballmind_services import (
    compare_players,
    get_bracket,
    get_fixtures,
    get_groups,
    get_match_lineup,
    get_player_profile,
    get_prediction_results,
    get_prediction_summary,
    get_rankings,
    get_standings,
    get_standouts,
    get_team_formations,
    get_team_squad,
    get_teams_in_comp,
    get_top_scorers,
    search_players,
    _form_score,
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
                  storage_uri="memory://")


@app.errorhandler(429)
def _rate_limited(e):
    return jsonify({"error": "rate limit exceeded",
                    "detail": f"Too many requests ({e.description}). "
                              "Please slow down and try again later."}), 429


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


_VALID_COMPS = frozenset({"PL", "PD", "BL1", "SA", "FL1", "CL", "DED", "WC"})
_COMP_LABELS = {
    "PL": "Premier League", "PD": "La Liga", "BL1": "Bundesliga",
    "SA": "Serie A", "FL1": "Ligue 1", "CL": "Champions League",
    "DED": "Eredivisie", "WC": "World Cup",
}


def _resolve_chat_comp(data, default: str = "WC") -> str:
    raw = str(data.get("comp") or default).strip().upper()
    return raw if raw in _VALID_COMPS else default


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


def _parse_player_compare(message: str) -> tuple[str, str] | None:
    """Extract two player names from a comparison query, or None."""
    low = message.lower().strip()
    if any(h in low for h in _PREDICT_HINTS):
        return None
    if not any(h in low for h in ("compare", " vs ", " versus ", "who is better",
                                  "who's better", " or ")):
        return None
    m = _COMPARE_VS.match(message.strip())
    if not m:
        m = _PLAYER_VS.match(message.strip())
    if not m:
        return None
    return _clean_team(m.group(1)), _clean_team(m.group(2))


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
            lines.append(
                f"{comp} stats: {p['goals']}G · {p.get('assists', 0)}A · "
                f"{p.get('appearances', 0)} apps"
            )
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


def parse_intent(message):
    low = message.lower()
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
                    "venue": venue}
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
                                neutral=neutral)
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
    entities, prediction = {"comp": chat_comp}, None

    if _is_followup(message, history):
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
                                        None, "regular_season", session_id=session_id,
                                        neutral=neutral)
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
        reply = (f"Top of the {comp_label} table: "
                 + ", ".join(f"{t['rank']}. {t['team']} ({t['Pts']})" for t in table[:5])
                 if table else f"No {comp_label} results recorded yet.")
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
    return jsonify({"reply": reply, "intent": intent["type"], "prediction": prediction})


@app.get("/api/standings")
@limiter.exempt
def api_standings():
    return jsonify(_standings(get_conn(), request.args.get("comp", "PL"),
                              request.args.get("season")))


@app.get("/api/predictions")
@limiter.exempt
def api_predictions():
    limit = min(int(request.args.get("limit", 25)), 100)
    conn = get_conn()
    if request.args.get("finished") in ("1", "true", "yes"):
        results = get_prediction_results(conn, limit)
        return jsonify({"results": results, "summary": get_prediction_summary(conn)})
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
    comp = request.args.get("comp", "WC")
    limit = min(int(request.args.get("limit", 16)), 64)
    fixtures = get_fixtures(get_conn(), comp, limit)
    return jsonify({"fixtures": fixtures, "comp": comp})


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
    try:
        analysis = footballmind_llm.analyze_match(home, away, prediction)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500
    return jsonify({"analysis": analysis})


@app.get("/api/health")
@limiter.exempt
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
