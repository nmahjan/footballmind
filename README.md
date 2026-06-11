# FootballMind

A football intelligence app: ask about Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, or World Cup matches in plain English — get data-driven predictions with confidence intervals, form context, head-to-head history, and an optional AI-written match analysis.

**Live:** [nmahjan.github.io/footballmind](https://nmahjan.github.io/footballmind)

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

Recent matches are weighted more heavily using an exponential decay (half-life tuned via backtesting). This means a team's form over the last 2 months matters more than results from a year ago.

### 3. Hybrid lambda model (blends Elo + Dixon-Coles)

Neither model is perfect on its own:
- Dixon-Coles is highly accurate for teams with lots of data but unreliable for teams with few matches (e.g. World Cup qualifiers)
- Elo works for any team but can't model goal distributions directly

The **Hybrid** blends the expected-goals (lambda) estimates from both:

```
λ = credibility × λ_DixonColes + (1 − credibility) × λ_Elo
```

`credibility` is determined by how much data the team has: data-rich club teams get full Dixon-Coles weight; WC nations with sparse records blend toward Elo. The optimal `credibility` threshold and Dixon-Coles half-life are selected by **walk-forward backtesting** using Ranked Probability Score (RPS) — a proper scoring rule for ordered outcomes (win/draw/loss).

### 4. Poisson score matrix → probabilities

Given expected goals λ_home and λ_away, the model computes the full N×N scoreline probability matrix (truncated at ~10 goals per side) using independent Poisson distributions. Summing the matrix gives:

- P(home win), P(draw), P(away win)
- For knockout stages: P(home advances), accounting for extra time and penalties via an Elo-derived edge

### 5. Backtesting and deployment

Each weekly retrain:
1. Sweeps over a grid of half-life × credibility combinations
2. Evaluates each on a held-out test window using mean RPS
3. Retrains the best configuration on the full dataset
4. Stores the serialised model artifact in the database (`model_artifacts` table)
5. Marks it as the production model — `predict_match` loads it on the next request

Two separate models are deployed: `production_club` and `production_international`.

---

## Architecture

```
football-data.org API
        │
        ▼
footballmind_sync.py   ← rate-limited ingestion (10 req/min TokenBucket)
        │  upserts teams, matches, players, squads
        ▼
PostgreSQL (Neon)
        │
        ├── apply_pending_ratings  ← Elo updates, sequential, exactly once
        │
        ├── footballmind_backtest.py   ← walk-forward RPS sweep
        │
        └── footballmind_production.py ← select best, retrain, store artifact
                │
                ▼
        model_artifacts (JSONB blob in DB)
                │
                ▼
footballmind_mcp_predict.py   ← load_hybrid → predict_match
        │
        ▼
footballmind_app.py (Flask on Render)
        │
        ├── POST /api/chat       ← rule-based intent → LLM fallback
        ├── POST /api/predict
        ├── POST /api/analyze    ← Claude Haiku match analysis
        ├── GET  /api/standings
        ├── GET  /api/fixtures
        ├── GET  /api/groups
        ├── GET  /api/rankings
        └── GET  /api/bracket
                │
                ▼
frontend/ (Vite + React → GitHub Pages)
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

---

## Quick start (local)

```bash
cd footballmind
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy and fill in credentials
cp .env.example .env

# Apply database schema
python footballmind_migrate.py

# Pull data + seed national Elo ratings
python footballmind_jobs.py sync --full
python footballmind_jobs.py seed-elo

# Train models
python footballmind_jobs.py retrain

# Start the API
flask --app footballmind_app run

# In a separate terminal, start the frontend
cd frontend && npm install && npm run dev
```

---

## Deployment

| Layer | Service | Notes |
|-------|---------|-------|
| Database | Neon (free tier) | Persistent, scale-to-zero, pooled connection |
| Backend API | Render (free web service) | `gunicorn footballmind_app:app`, spins down after 15 min idle |
| Frontend | GitHub Pages | Static Vite build, auto-deployed on push to main |
| Scheduled jobs | GitHub Actions | Sync every 6h, retrain Monday 05:30 UTC |

### Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | Render + Actions secret | Neon pooled connection string |
| `FOOTBALL_DATA_API_KEY` | Actions secret | football-data.org API key |
| `ANTHROPIC_API_KEY` | Render env var | Claude API key (optional — enables LLM chat + deep analysis) |
| `FRONTEND_ORIGIN` | Render env var | GitHub Pages URL for CORS (or `*` for open access) |
| `VITE_API_BASE` | GitHub Pages variable | Points frontend at the Render backend URL |

---

## Key design decisions

- **Elo is sequential and non-idempotent** — `apply_pending_ratings` selects only matches with no entry in `rating_history` yet, ordered by date. Never bypass this.
- **Clubs and nations are separate ladders** — they never play each other; don't fit one Dixon-Coles across both.
- **Prediction orientation matters** — stored probabilities are home/away specific. `find_fixture` links predictions to results using exact orientation.
- **RPS not accuracy** — football outcomes are ordinal. A model that says "70% home win" when the draw happens is better than one that confidently predicts the wrong team. RPS captures this.
- **Hybrid cold start** — data-poor teams (WC nations) blend toward Elo by design. Don't override this for international predictions.
