# FootballMind — Premier League & UEFA Intelligent Data Explorer
## Full Project Specification

**Version:** 1.0  
**Date:** April 2026  
**Developer:** Neil Mahajan  
**Purpose:** Portfolio project + public showcase  
**Methodology:** 40/40 AI Stack (Superpowers → Amp → Traycer review)

---

## Overview

FootballMind is a publicly deployable football intelligence platform that lets anyone ask questions about Premier League and UEFA data in plain English and receive contextual, AI-powered answers — including match outcome predictions and player performance forecasts.

It is built on an MCP (Model Context Protocol) server architecture, exposed through a LiteLLM gateway, with full session history, IP tracking, and contextual search that understands follow-up questions.

**Core tagline:** *"Ask anything about football. Get answers, not just data."*

---

## User Experience Goals

1. User types: *"Who is Arsenal's best performer this season?"* → gets a contextual answer with stats
2. User follows up: *"Will they start on Saturday?"* → system understands "they" from context
3. User asks: *"Predict the Arsenal vs Chelsea match this weekend"* → gets W/D/L prediction with confidence score and reasoning
4. User asks: *"Who should I watch in the Champions League this week?"* → gets player performance forecast
5. Every session is tracked — user can revisit past questions and see how predictions performed

---

## Architecture

```
Data Sources
├── football-data.org API (live — fixtures, results, standings, lineups)
└── Kaggle Historical Dataset (5+ seasons PL + UEFA stats)
         ↓
   Data Layer (Python + Pandas + SQLite)
   - Normalizes and caches API responses
   - Stores historical dataset
   - Updates live data every 6 hours
         ↓
   MCP Server (Python mcp SDK)
   - Tool: query_stats(question) — NL to SQL
   - Tool: search_players(query, context) — semantic player search
   - Tool: predict_match(home_team, away_team, date) — ML prediction
   - Tool: forecast_player(player_name, match_context) — performance forecast
   - Tool: get_context(session_id) — retrieve conversation history
         ↓
   LiteLLM Gateway (open source)
   - Routes to Claude Sonnet (primary) or Ollama (fallback)
   - Handles rate limiting and auth
   - No vendor lock-in
         ↓
   Flask Backend API
   - POST /api/chat — main NLP query endpoint
   - GET /api/history — session history
   - GET /api/predictions — past predictions + outcomes
   - GET /api/standings — current league tables
   - Tracks: IP address, session ID, timestamp, query, response, context chain
   - SQLite: sessions, queries, predictions, users
         ↓
   React Frontend
   - Chat interface (left panel)
   - Live standings sidebar (right panel)
   - Prediction cards with confidence scores
   - Session history drawer
   - "How did my predictions do?" dashboard
```

---

## Data Sources

### Live Data — football-data.org
- **Free tier:** 10 calls/minute, covers PL + Champions League + Europa League
- **Endpoints used:**
  - `/competitions/PL/matches` — Premier League fixtures and results
  - `/competitions/CL/matches` — Champions League
  - `/competitions/PL/standings` — League table
  - `/competitions/PL/scorers` — Top scorers
  - `/teams/{id}/matches` — Team-specific history
- **API Key:** Required (free at football-data.org)

### Historical Data — Kaggle
- **Dataset:** European Soccer Database or Premier League Dataset (2010–2025)
- **Covers:** Player stats, match results, team performance, season summaries
- **Use:** Training prediction models + answering historical questions
- **No API key needed** — download once, store in SQLite

---

## MCP Server Specification

### Tools Exposed

**1. query_stats**
```python
@mcp.tool()
def query_stats(question: str, session_id: str) -> dict:
    """
    Convert a natural language question into a database query
    and return a structured answer with context.
    
    Example: "Who has the most Premier League goals this season?"
    Returns: {player, team, goals, rank, context_summary}
    """
```

**2. search_players**
```python
@mcp.tool()
def search_players(query: str, context: list) -> dict:
    """
    Semantic search for players using sentence embeddings.
    Understands follow-up context (e.g., "that player" refers to
    the last mentioned player in conversation history).
    
    Example: "Show me players like Salah but younger"
    Returns: {players: [{name, team, similarity_score, stats}]}
    """
```

**3. predict_match**
```python
@mcp.tool()
def predict_match(home_team: str, away_team: str, match_date: str) -> dict:
    """
    Predict match outcome using historical data + current form.
    
    Returns: {
        prediction: "Home Win" | "Draw" | "Away Win",
        confidence: 0.0-1.0,
        home_win_prob: float,
        draw_prob: float,
        away_win_prob: float,
        reasoning: str,
        key_factors: list
    }
    """
```

**4. forecast_player**
```python
@mcp.tool()
def forecast_player(player_name: str, match_context: str) -> dict:
    """
    Forecast player performance for an upcoming match.
    
    Returns: {
        player: str,
        expected_goals: float,
        expected_assists: float,
        form_rating: float,
        injury_risk: str,
        recommendation: str,
        reasoning: str
    }
    """
```

**5. get_context**
```python
@mcp.tool()
def get_context(session_id: str, last_n: int = 5) -> dict:
    """
    Retrieve conversation history for contextual follow-up questions.
    
    Returns: {messages: [{role, content, timestamp}], entities: []}
    """
```

---

## Prediction Model Specification

### Match Outcome Prediction
- **Algorithm:** Gradient Boosting (scikit-learn GradientBoostingClassifier)
- **Features:**
  - Home/away last 5 match results (points, goals for, goals against)
  - Head-to-head record (last 10 meetings)
  - Current league position
  - Goals scored/conceded per game (season average)
  - Days since last match (fatigue proxy)
  - Home advantage factor
- **Output:** Win/Draw/Loss probabilities + confidence score
- **Training data:** Kaggle historical dataset (5+ seasons)
- **Retraining:** Weekly with new results

### Player Performance Forecast
- **Algorithm:** Linear Regression per player (goals, assists)
- **Features:**
  - Last 5 match stats (goals, assists, shots, key passes)
  - Opponent defensive strength (goals conceded per game)
  - Home vs away performance split
  - Minutes played trend
- **Output:** Expected goals, expected assists, form rating (1-10)

---

## Database Schema

```sql
-- Session tracking
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    ip_address TEXT,
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    query_count INTEGER DEFAULT 0
);

-- Query history with context
CREATE TABLE queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    query TEXT,
    response TEXT,
    query_type TEXT, -- 'stats' | 'prediction' | 'search' | 'forecast'
    entities_mentioned TEXT, -- JSON: teams, players referenced
    timestamp TIMESTAMP,
    response_time_ms INTEGER
);

-- Prediction tracking
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    match_id TEXT,
    home_team TEXT,
    away_team TEXT,
    match_date DATE,
    predicted_outcome TEXT,
    confidence REAL,
    home_prob REAL,
    draw_prob REAL,
    away_prob REAL,
    actual_outcome TEXT, -- filled in after match
    was_correct BOOLEAN,
    created_at TIMESTAMP
);

-- Cached live data
CREATE TABLE live_cache (
    key TEXT PRIMARY KEY,
    data TEXT, -- JSON
    fetched_at TIMESTAMP,
    expires_at TIMESTAMP
);
```

---

## Frontend Specification

### Layout
- **Left panel (60%):** Chat interface
  - Message input at bottom
  - Conversation history scrolling up
  - Prediction cards rendered inline
  - Follow-up suggestions below each response
- **Right panel (40%):** Live data sidebar
  - Current PL standings table
  - This week's fixtures
  - Top scorers widget
  - "My predictions" tracker

### Chat Interface
- Dark theme (consistent with Federal Spending Dashboard aesthetic)
- User messages: right-aligned, blue
- AI responses: left-aligned, dark card
- Prediction cards: expandable with confidence bar, probability breakdown
- Player forecast cards: stats grid with trend arrows

### Prediction Card Component
```
┌─────────────────────────────────────┐
│ Arsenal vs Chelsea — Apr 12, 2026   │
│ ─────────────────────────────────── │
│ 🏆 Predicted: Arsenal Win           │
│ Confidence: ████████░░ 78%          │
│                                     │
│ Home Win  68% ████████░░            │
│ Draw      18% ██░░░░░░░░            │
│ Away Win  14% █░░░░░░░░░            │
│                                     │
│ Key factors:                        │
│ • Arsenal: 4W in last 5 home games  │
│ • Chelsea: 2 key players injured    │
│ • H2H: Arsenal won 3 of last 5     │
└─────────────────────────────────────┘
```

---

## Deployment Plan

### Local Development
```bash
# 1. Install dependencies
pip install mcp litellm flask flask-cors pandas scikit-learn
pip install sentence-transformers football-data-api
npm install (React frontend)

# 2. Set environment variables
FOOTBALL_DATA_API_KEY=your_key
ANTHROPIC_API_KEY=your_key (or use Ollama free)

# 3. Start MCP server
python mcp_server.py

# 4. Start LiteLLM gateway
litellm --model claude-sonnet-4-6

# 5. Start Flask backend
python app.py

# 6. Start React frontend
npm run dev
```

### Public Deployment (GitHub Pages + Render)
- **Frontend:** GitHub Pages (same as Federal Spending Dashboard)
  - URL: `nmahjan.github.io/footballmind`
  - React builds to static files, deployed on push
- **Backend + MCP:** Render free tier
  - URL: `footballmind.onrender.com`
  - Auto-deploys from GitHub on every push
  - ⚠️ Spins down after 15 min inactivity — first request takes ~30s to wake
  - Add "Waking up server..." loading state in React frontend
- **Database:** SQLite (local dev) → SQLite on Render (production, persisted volume)
- **Live data cache:** 6-hour refresh via scheduled job
- **Config file:** `render.yaml` in repo root

```yaml
# render.yaml
services:
  - type: web
    name: footballmind-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python backend/app.py
    envVars:
      - key: FOOTBALL_DATA_API_KEY
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
```

### Deployment Steps
1. Push code to GitHub repo
2. render.com → New Web Service → Connect GitHub repo
3. Set environment variables (API keys) in Render dashboard
4. Deploy frontend: `npm run build` → GitHub Pages
5. Update React `.env` to point to Render URL

---

## File Structure

```
footballmind/
├── mcp_server/
│   ├── server.py           # MCP server entry point
│   ├── tools/
│   │   ├── query_stats.py
│   │   ├── search_players.py
│   │   ├── predict_match.py
│   │   ├── forecast_player.py
│   │   └── get_context.py
│   └── embeddings/
│       └── player_index.pkl # Pre-computed sentence embeddings
├── backend/
│   ├── app.py              # Flask API
│   ├── data/
│   │   ├── loader.py       # Kaggle + API data loading
│   │   ├── cache.py        # Live data caching
│   │   └── db.py           # SQLite operations
│   ├── models/
│   │   ├── match_predictor.py
│   │   └── player_forecaster.py
│   └── nlp/
│       └── context_manager.py  # Session + context tracking
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx
│   │   │   ├── PredictionCard.jsx
│   │   │   ├── PlayerForecast.jsx
│   │   │   ├── Standings.jsx
│   │   │   └── SessionHistory.jsx
│   │   ├── App.jsx
│   │   └── index.jsx
│   └── package.json
├── data/
│   ├── historical/         # Kaggle dataset
│   └── footballmind.db     # SQLite database
├── requirements.txt
├── README.md
└── .env.example
```

---

## MVP Scope (Build First)

To keep the first version focused and shippable:

1. ✅ MCP server with `query_stats` and `predict_match` tools only
2. ✅ football-data.org live API for current season data
3. ✅ Flask backend with session tracking and IP logging
4. ✅ React chat interface with prediction cards
5. ✅ PL standings sidebar
6. ✅ Basic match outcome prediction (gradient boosting)
7. ✅ Deployed publicly

**Save for v2:**
- Player performance forecasting
- Kaggle historical dataset integration
- Semantic player search
- "How did my predictions do?" dashboard
- UEFA / Champions League data

---

## Out of Scope

- User accounts or authentication
- Payment / premium features
- Mobile app
- Real-time live match updates (websockets)
- Fantasy football integration

---

## Success Criteria

- [ ] User can ask "Who is top scorer in the Premier League?" and get a correct answer
- [ ] User can ask "Predict Arsenal vs Chelsea" and get a W/D/L prediction with reasoning
- [ ] Follow-up questions use context ("What about their last meeting?" after a prediction)
- [ ] Session history persists across page refreshes
- [ ] IP tracking logs every query
- [ ] App is publicly accessible via URL
- [ ] Loads in under 3 seconds

---

*FootballMind — Built by Neil Mahajan using the 40/40 AI Stack*
*Superpowers (planning) → Amp (execution) → Traycer (review)*
