# FootballMind [![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

A football intelligence app: ask about Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Champions League, or World Cup matches in plain English — get data-driven predictions with confidence, form context, head-to-head history, and optional AI-written match analysis.

| | URL |
|---|---|
| **Live app** | [nmahjan.github.io/footballmind](https://nmahjan.github.io/footballmind) |
| **API** | [football-mind.onrender.com](https://football-mind.onrender.com) |

---

## Features

### Web app (GitHub Pages)

- **Chat predictions** — type or tap a fixture: *"Predict Mexico vs USA"*
- **Prediction cards** — W/D/L bar, form dots, H2H, xG, rule-based narrative
- **Deep analysis** — optional Claude Haiku write-up per prediction (`/api/analyze`)
- **Sidebar modes** — **Matches** (fixtures, tables, bracket, rankings) or **Players** (squads, scorers, search)
- **Upcoming fixtures** — tabbed panel for WC, PL, La Liga, Bundesliga, Serie A, Ligue 1, CL, Eredivisie
- **League tables** — live standings for all synced domestic leagues + CL
- **WC group standings** — per-group tables during the tournament
- **Tournament bracket** — knockout rounds (Final → Semi → QF → R16) for WC and CL
- **Power rankings** — national team Elo rankings
- **Players panel** — standouts, top scorers, **predicted starting XI** (pitch view), full team squads; tap a player to ask the chat
- **Predicted XI** — most likely lineup per team; adjusts for red-card suspensions and injury flags; prefers recent formations when synced
- **Player chat** — LLM answers with squad/scorer tools; markdown replies render as formatted text
- **Neutral venue toggle** — disable home-field advantage for WC / neutral-site games
- **Share prediction** — copy a formatted summary to clipboard

### Backend

- Hybrid **Elo + Dixon-Coles** model with weekly retrain (RPS backtest)
- football-data.org sync every 6 hours (GitHub Actions) — matches, squads, **top scorers** (100/comp)
- Migrations run automatically before each Actions sync (`footballmind_migrate.py`)
- Rate-limited LLM chat (20 req/hr per IP) to protect API cost
- **MCP server** — 13+ tools for Cursor / Claude Desktop (local stdio + remote HTTP)

---

## How the models work

FootballMind chains three statistical layers together. Each layer feeds the next.

### 1. Elo ratings (always available)

Every team carries an Elo rating (default 1500). After each match the ratings are updated using a formula that accounts for:

- **Result margin** — a 3-0 win transfers more rating points than a 1-0 win (logarithmic capping prevents anomalies)
- **Match importance** — World Cup knockouts carry higher weight than a mid-table league game
- **Pre-match expectation** — beating a much weaker team earns fewer points than beating a much stronger one

Clubs and national teams live on **separate ladders** and are never mixed. Elo is computed sequentially and exactly once per match (enforced by a `rating_history` ledger), so re-running the pipeline never corrupts the ratings.

### 2. Dixon-Coles model (trained weekly)

When enough match data exists, a time-weighted Maximum Likelihood Estimation fit runs over historical results to produce per-team parameters:

- **Attack strength** — how many goals a team tends to score relative to average
- **Defence weakness** — how many goals a team tends to concede
- **Home advantage** — a global offset applied when the match is at the home team's ground
- **ρ (rho) correction** — a small adjustment that improves accuracy for 0-0, 1-0, 0-1, and 1-1 scorelines (Dixon-Coles 1997)

Recent matches are weighted more heavily using an exponential decay (half-life tuned via backtesting).

### 3. Hybrid lambda model (blends Elo + Dixon-Coles)

```
λ = credibility × λ_DixonColes + (1 − credibility) × λ_Elo
```

`credibility` is tuned by walk-forward backtesting using **Ranked Probability Score (RPS)**. Data-rich club teams get full Dixon-Coles weight; WC nations with sparse records blend toward Elo.

### 4. Poisson score matrix → probabilities

Given expected goals λ_home and λ_away, the model builds a scoreline probability matrix and sums it to W/D/L (and knockout advancement probabilities).

### 5. Backtesting and deployment

Each weekly retrain sweeps half-life × credibility, picks the best RPS, retrains on all data, and stores the artifact in `model_artifacts`. Two models deploy: `production_club` and `production_international`.

---

## Architecture

```
football-data.org API
        │
        ▼
footballmind_sync.py          ← rate-limited ingestion (10 req/min)
        │  upserts teams, matches, players, squads, scorers
        ▼
PostgreSQL (Neon)
        │
        ├── apply_pending_ratings       ← Elo, sequential, exactly once
        ├── footballmind_backtest.py    ← walk-forward RPS sweep
        └── footballmind_production.py  ← select best, retrain, store artifact
                │
                ▼
        model_artifacts (JSONB)
                │
                ▼
footballmind_mcp_predict.py     ← load_hybrid → predict_match
        │
        ├──────────────────────────────────────┐
        ▼                                      ▼
footballmind_asgi.py (Render)            server.py (local MCP, stdio)
  ├── /api/*  Flask REST                   MCP tools
  └── /mcp    streamable-http              (Cursor / Claude Desktop)
        │
        ▼
frontend/  (Vite + React → GitHub Pages)
```

### REST API (`/api/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness probe |
| POST | `/api/predict` | Direct match prediction |
| POST | `/api/chat` | Intent router + LLM fallback (rate-limited) |
| POST | `/api/analyze` | Claude match analysis (rate-limited) |
| GET | `/api/standings?comp=PL` | League table |
| GET | `/api/fixtures?comp=WC` | Upcoming fixtures |
| GET | `/api/groups?comp=WC` | Tournament group standings |
| GET | `/api/bracket?comp=CL` | Knockout bracket |
| GET | `/api/rankings?comp=WC` | National Elo power rankings |
| GET | `/api/standouts?comp=WC` | Notable players ranked by form + team strength (max 2 per nation) |
| GET | `/api/players/scorers?comp=PL` | Top scorers with goals, assists, appearances |
| GET | `/api/players/squad?team=…&comp=…` | Full squad by position |
| GET | `/api/players/search?q=…` | Player name search |
| GET | `/api/players/profile?name=…` | Player profile + competition stats |
| GET | `/api/players/formations?team=…` | Recent formations (when lineup data exists) |
| GET | `/api/players/predicted-lineup?team=…&comp=WC` | Most likely starting XI (injuries + suspensions) |
| GET | `/api/players/lineup?home=…&away=…` | Last H2H lineups |
| GET | `/api/predictions` | Graded prediction history + hit rate |

Shared query logic lives in `footballmind_services.py` (used by both Flask and MCP).

---

## Project structure

```
footballmind/
├── frontend/                  # Vite + React UI (GitHub Pages)
├── migrations/                # Ordered SQL schema migrations
├── scripts/
│   └── setup_cursor_mcp.py    # Wire ~/.cursor/mcp.json from .env
├── server.py                  # MCP server (stdio / streamable-http)
├── footballmind_asgi.py       # Combined REST + MCP for Render
├── footballmind_app.py        # Flask REST API
├── footballmind_services.py   # Shared read/query helpers
├── footballmind_lineup.py     # Predicted XI + availability logic
├── footballmind_mcp_predict.py
├── footballmind_sync.py       # football-data.org ingestion
├── footballmind_jobs.py       # CLI: sync, retrain, seed-elo
├── footballmind_elo.py
├── footballmind_dixoncoles.py
├── footballmind_predict.py
├── footballmind_production.py
├── footballmind_backtest.py
├── footballmind_llm.py        # LiteLLM / Claude gateway
├── render.yaml                # Render deploy config
└── mcp.json.example           # Cursor MCP config template
```

---

## Competitions synced

| Code | Competition | Type |
|------|-------------|------|
| PL   | Premier League | Club |
| PD   | La Liga | Club |
| BL1  | Bundesliga | Club |
| SA   | Serie A | Club |
| FL1  | Ligue 1 | Club |
| CL   | Champions League | Club |
| DED  | Eredivisie | Club |
| WC   | FIFA World Cup | National |

Run a full backfill after adding a league: **GitHub Actions → footballmind-jobs → Run workflow → sync → check "Full season backfill".**

Migrations (`006` player positions, `007` scorer stats / lineup schema, `008` prediction team links, `009` player availability) run automatically at the start of each Actions job. To check locally:

```bash
python footballmind_migrate.py --status
```

**Note:** football-data.org free tier includes competition scorers but not per-match lineups/goals in match detail. Formation tools populate when that data becomes available (paid tier or live tournament detail).

### Predicted lineups & availability

`footballmind_lineup.py` builds a most-likely XI from squad depth and form scores:

1. **Formation** — prefers the team's most recent synced formation; otherwise picks the best-fit template (4-3-3, 4-2-3-1, 3-4-3, etc.) from available players.
2. **Starters** — highest-rated player per slot (Elo + club goals/assists + appearances).
3. **Red-card suspensions** — computed at runtime from `match_events` (player sent off in last finished match is excluded for the next fixture).
4. **Injuries / doubtful** — stored in `player_availability` (manual flags until an injury feed is added).

Flag a player out manually:

```sql
INSERT INTO player_availability (player_id, team_id, comp_code, status, reason)
VALUES (
  (SELECT id FROM players WHERE name ILIKE 'Pedri%' LIMIT 1),
  (SELECT id FROM teams WHERE name = 'Spain'),
  'WC', 'injured', 'Hamstring'
);
```

Status values: `injured`, `doubtful`, `suspended`.

---

## Quick start (local)

```bash
cd footballmind
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in DATABASE_URL, API keys

python footballmind_migrate.py
python footballmind_jobs.py sync --full
python footballmind_jobs.py seed-elo
python footballmind_jobs.py retrain

# REST API only
flask --app footballmind_app run --port 5000

# REST + MCP (matches Render locally)
uvicorn footballmind_asgi:app --reload --port 8000

# Frontend
cd frontend && cp .env.example .env   # VITE_API_BASE=http://127.0.0.1:8000
npm install && npm run dev
```

---

## MCP server (Cursor / Claude Desktop)

FootballMind is an **MCP server** — agents can call football tools directly instead of going through the web UI.

| Tool | What it does |
|------|----------------|
| `predict_match` | W/D/L probabilities + expected goals |
| `get_league_standings` | League table (PL, PD, BL1, SA, FL1, CL, DED) |
| `list_fixtures` | Upcoming matches |
| `get_tournament_groups` | WC group standings |
| `get_tournament_bracket` | Knockout bracket (Final first) |
| `get_power_rankings` | National Elo rankings |
| `list_standout_players` | Key players by position / goals |
| `search_players` | Find players by name |
| `get_team_squad` | Full roster with positions |
| `get_player_profile` | Player bio + competition stats |
| `get_top_scorers` | Competition scoring table |
| `get_team_formations` | Recent formations for a team |
| `get_match_lineup` | Lineups from latest H2H meeting |
| `get_predicted_lineup` | Most likely starting XI (injuries + red-card suspensions) |

### Local (stdio)

```bash
python scripts/setup_cursor_mcp.py   # writes ~/.cursor/mcp.json from .env
```

Restart Cursor — you should see **footballmind** under MCP servers.

Or copy `mcp.json.example` and set paths + `DATABASE_URL` manually.

### Remote (HTTP on Render)

The combined ASGI app serves MCP at `/mcp` alongside the existing REST API. **The website is unaffected** — same `/api/*` routes, same env vars; only the process wrapper changes from gunicorn to uvicorn.

1. `openssl rand -hex 24` → set as `MCP_API_KEY` on Render
2. Add the same key to `~/.cursor/mcp.json`:
   ```json
   "footballmind-remote": {
     "type": "http",
     "url": "https://football-mind.onrender.com/mcp",
     "headers": { "Authorization": "Bearer YOUR_MCP_API_KEY" }
   }
   ```
3. Ensure Render **Start Command** is:
   ```
   uvicorn footballmind_asgi:app --host 0.0.0.0 --port $PORT
   ```
4. Verify: `curl https://football-mind.onrender.com/api/health`

---

## Deployment

| Layer | Service | Notes |
|-------|---------|-------|
| Database | [Neon](https://neon.tech) (free tier) | Pooled connection string for `DATABASE_URL` |
| Backend + MCP | [Render](https://render.com) (free web service) | `uvicorn footballmind_asgi:app` |
| Frontend | GitHub Pages | Auto-deployed on push to `main` via `.github/workflows/pages.yml` |
| Scheduled jobs | GitHub Actions | Sync every 6h, retrain Monday 05:30 UTC |

### Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | Render + Actions secret | Neon pooled connection string |
| `MCP_API_KEY` | Render + local `.env` | Bearer token for remote MCP at `/mcp` (optional for website) |
| `FOOTBALL_DATA_API_KEY` | Actions secret | football-data.org API key |
| `ANTHROPIC_API_KEY` | Render env var | Claude API (LLM chat + deep analysis) |
| `FRONTEND_ORIGIN` | Render env var | GitHub Pages URL for CORS (or `*`) |
| `VITE_API_BASE` | GitHub Pages repo variable | `https://football-mind.onrender.com` |

**Never commit `.env` or put secrets in `VITE_*` vars** — those are baked into the public frontend bundle.

### Render checklist (existing service)

If you already have a Render web service, updating does **not** break the site:

- [ ] Push latest `main` (triggers auto-deploy)
- [ ] Update **Start Command** to `uvicorn footballmind_asgi:app --host 0.0.0.0 --port $PORT`
- [ ] Add `MCP_API_KEY` (optional — only secures `/mcp`)
- [ ] Confirm `/api/health` returns `{"status":"ok"}` after deploy

---

## Key design decisions

- **Elo is sequential and non-idempotent** — only `apply_pending_ratings` may update ratings; never bypass the `rating_history` ledger.
- **Clubs and nations are separate ladders** — never fit one Dixon-Coles across both.
- **Prediction orientation matters** — stored probabilities are home/away specific.
- **RPS not accuracy** — football outcomes are ordinal; RPS is the proper scoring rule.
- **Hybrid cold start** — data-poor WC teams blend toward Elo by design.
- **Three interfaces, one brain** — Flask REST, MCP tools, and LiteLLM function-calling all call the same `_predict_match` / `footballmind_services` functions.

---

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) for details.
If you run a modified version of this software as a network service, you must publish your source code under the same license.
