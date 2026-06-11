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

from footballmind_mcp_predict import _predict_match

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


# ----------------------------------------------------------------------
# Pure logic (unit-testable, no DB) -- rule-based intent fast path
# ----------------------------------------------------------------------
_VS = re.compile(
    r"^\s*(?:can you |please )?(?:predict|forecast)?\s*(.+?)\s+"
    r"(?:vs\.?|versus|v|against)\s+(.+?)\s*[\?\.!]*$", re.I)


def _clean_team(s):
    s = s.strip()
    # strip leading question/filler words before the team name
    s = re.sub(r"^(who\s+will\s+win\s+|who\s+wins\s+|will\s+|can\s+|"
               r"what\s+about\s+|how\s+about\s+|the\s+|a\s+)", "", s, flags=re.I)
    # strip trailing context filler
    s = re.sub(r"\s+(match|game|fixture|this weekend|today|tomorrow|on \w+)\b.*$",
               "", s, flags=re.I)
    return s.strip()


def parse_intent(message):
    low = message.lower()
    if "standing" in low or "table" in low or "league position" in low:
        return {"type": "standings"}
    m = _VS.match(message)
    if m and ("predict" in low or " vs" in low or "versus" in low or "against" in low):
        return {"type": "predict",
                "home": _clean_team(m.group(1)), "away": _clean_team(m.group(2))}
    return {"type": "unknown"}


def compute_standings(rows):
    """rows: iterable of (home, away, home_goals, away_goals). Returns sorted table."""
    tbl = {}

    def slot(t):
        return tbl.setdefault(t, {"team": t, "P": 0, "W": 0, "D": 0,
                                  "L": 0, "GF": 0, "GA": 0, "Pts": 0})
    for home, away, hg, ag in rows:
        h, a = slot(home), slot(away)
        h["P"] += 1; a["P"] += 1
        h["GF"] += hg; h["GA"] += ag; a["GF"] += ag; a["GA"] += hg
        if hg > ag:
            h["W"] += 1; h["Pts"] += 3; a["L"] += 1
        elif hg < ag:
            a["W"] += 1; a["Pts"] += 3; h["L"] += 1
        else:
            h["D"] += 1; a["D"] += 1; h["Pts"] += 1; a["Pts"] += 1
    table = list(tbl.values())
    for t in table:
        t["GD"] = t["GF"] - t["GA"]
    table.sort(key=lambda t: (t["Pts"], t["GD"], t["GF"]), reverse=True)
    for i, t in enumerate(table, 1):
        t["rank"] = i
    return table


def _standings(conn, comp_code, season=None):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT th.name, ta.name, m.home_goals, m.away_goals FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE c.code = %s AND m.home_goals IS NOT NULL "
            "  AND (%s::text IS NULL OR e.season = %s)", (comp_code, season, season))
        return compute_standings(cur.fetchall())


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
    intent = parse_intent(message)
    entities, prediction = {}, None

    if intent["type"] == "predict":
        entities = {"home": intent["home"], "away": intent["away"]}
        # detect venue override from natural language
        neutral_override = None
        low = message.lower()
        if any(w in low for w in ("neutral", "at a neutral", "at neutral")):
            neutral_override = True
        elif any(w in low for w in ("at home", "home ground", "home stadium", "wembley")):
            neutral_override = False
        try:
            prediction = _predict_match(conn, intent["home"], intent["away"],
                                        None, "regular_season", session_id=session_id,
                                        neutral=neutral_override)
            venue_note = "" if neutral_override is None else (" (neutral venue)" if neutral_override else " (home advantage)")
            reply = (f"{prediction['prediction']} "
                     f"({round(prediction['confidence'] * 100)}% confidence){venue_note}. "
                     f"{prediction['reasoning']}")
        except ValueError as e:
            reply = f"I couldn't run that prediction: {e}"
    elif intent["type"] == "standings":
        table = _standings(conn, "PL")
        entities = {"competition": "PL"}
        reply = ("Top of the table: "
                 + ", ".join(f"{t['rank']}. {t['team']} ({t['Pts']})" for t in table[:5])
                 if table else "No results recorded yet.")
    else:
        import footballmind_llm                 # lazy: litellm is heavy and optional
        if footballmind_llm.is_configured():
            reply, prediction = footballmind_llm.answer(conn, message,
                                                        session_id=session_id)
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
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, th.name AS home, ta.name AS away, p.home_win_prob, "
            "       p.draw_prob, p.away_win_prob, p.home_advance_prob, p.confidence, "
            "       p.actual_home_goals, p.actual_away_goals, p.was_correct, p.created_at "
            "FROM predictions p "
            "LEFT JOIN matches m ON m.id = p.match_id "
            "LEFT JOIN teams th ON th.id = m.home_team_id "
            "LEFT JOIN teams ta ON ta.id = m.away_team_id "
            "ORDER BY p.created_at DESC LIMIT %s", (limit,))
        cols = [d[0] for d in cur.description]
        preds = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute("SELECT count(*) FILTER (WHERE was_correct IS NOT NULL), "
                    "       count(*) FILTER (WHERE was_correct) FROM predictions")
        graded, correct = cur.fetchone()
    return jsonify({"predictions": preds,
                    "summary": {"graded": graded or 0, "correct": correct or 0,
                                "hit_rate": (correct / graded) if graded else None}})


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
    conn = get_conn()
    with conn.cursor() as cur:
        # Aggregate home and away stats per team per group
        cur.execute(
            "SELECT g, team, SUM(W) W, SUM(D) D, SUM(L) L, "
            "       SUM(GF) GF, SUM(GA) GA, SUM(Pts) Pts "
            "FROM ("
            "  SELECT m.group_name g, th.name team,"
            "    COUNT(*) FILTER (WHERE m.home_goals > m.away_goals) W,"
            "    COUNT(*) FILTER (WHERE m.home_goals = m.away_goals) D,"
            "    COUNT(*) FILTER (WHERE m.home_goals < m.away_goals) L,"
            "    COALESCE(SUM(m.home_goals),0) GF, COALESCE(SUM(m.away_goals),0) GA,"
            "    SUM(CASE WHEN m.home_goals > m.away_goals THEN 3"
            "             WHEN m.home_goals = m.away_goals THEN 1 ELSE 0 END) Pts"
            "  FROM matches m"
            "  JOIN competition_editions e ON e.id = m.edition_id"
            "  JOIN competitions c ON c.id = e.competition_id"
            "  JOIN teams th ON th.id = m.home_team_id"
            "  WHERE c.code = %s AND m.home_goals IS NOT NULL AND m.group_name IS NOT NULL"
            "  GROUP BY m.group_name, th.name"
            "  UNION ALL"
            "  SELECT m.group_name, ta.name,"
            "    COUNT(*) FILTER (WHERE m.away_goals > m.home_goals),"
            "    COUNT(*) FILTER (WHERE m.away_goals = m.home_goals),"
            "    COUNT(*) FILTER (WHERE m.away_goals < m.home_goals),"
            "    COALESCE(SUM(m.away_goals),0), COALESCE(SUM(m.home_goals),0),"
            "    SUM(CASE WHEN m.away_goals > m.home_goals THEN 3"
            "             WHEN m.away_goals = m.home_goals THEN 1 ELSE 0 END)"
            "  FROM matches m"
            "  JOIN competition_editions e ON e.id = m.edition_id"
            "  JOIN competitions c ON c.id = e.competition_id"
            "  JOIN teams ta ON ta.id = m.away_team_id"
            "  WHERE c.code = %s AND m.home_goals IS NOT NULL AND m.group_name IS NOT NULL"
            "  GROUP BY m.group_name, ta.name"
            ") s GROUP BY g, team ORDER BY g, Pts DESC, (SUM(GF)-SUM(GA)) DESC",
            (comp, comp))
        rows = cur.fetchall()

    groups = {}
    for g, team, W, D, L, GF, GA, Pts in rows:
        groups.setdefault(g, []).append({
            "team": team, "W": W, "D": D, "L": L,
            "GD": GF - GA, "GF": GF, "GA": GA, "Pts": Pts,
        })
    return jsonify({"groups": groups, "comp": comp})


@app.get("/api/fixtures")
@limiter.exempt
def api_fixtures():
    """Upcoming matches for a competition. Defaults to WC, limit 16."""
    comp = request.args.get("comp", "WC")
    limit = min(int(request.args.get("limit", 16)), 64)
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT th.name AS home, ta.name AS away, "
            "       m.match_date, m.stage, m.home_goals, m.away_goals "
            "FROM matches m "
            "JOIN competition_editions e ON e.id = m.edition_id "
            "JOIN competitions c ON c.id = e.competition_id "
            "JOIN teams th ON th.id = m.home_team_id "
            "JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE c.code = %s "
            "  AND m.match_date >= now() - interval '3 hours' "
            "ORDER BY m.match_date ASC LIMIT %s",
            (comp, limit))
        cols = [d[0] for d in cur.description]
        fixtures = [dict(zip(cols, r)) for r in cur.fetchall()]
    return jsonify({"fixtures": fixtures, "comp": comp})


@app.get("/api/health")
@limiter.exempt
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
