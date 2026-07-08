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
- **Prediction cards** — W/D/L bar, form dots, H2H, xG, predicted XI for both teams (compact list + optional pitch view), rule-based narrative
- **Deep analysis** — optional Claude Haiku write-up per prediction (`/api/analyze`)
- **Sidebar modes** — **Matches** (fixtures, tables, bracket, rankings) or **Players** (squads, scorers, search)
- **Upcoming fixtures** — tabbed panel for WC, PL, La Liga, Bundesliga, Serie A, Ligue 1, CL, Eredivisie
- **League tables** — live standings for all synced domestic leagues + CL, with **qualification zone highlights** (Champions League, Europa League, Conference League, relegation, and CL knockout cutoffs)
- **WC group standings** — per-group tables with **top-two knockout** highlighting
- **Tournament bracket** — knockout rounds (Final → Semi → QF → R16) for WC and CL
- **Power rankings** — national team Elo rankings
- **Players panel** — standouts, top scorers, **predicted starting XI** (pitch view), full team squads; tap a player to ask the chat
- **Predicted XI** — most likely lineup per team; adjusts for red-card suspensions and injury flags; prefers recent formations when synced
- **Player chat** — LLM answers with squad/scorer tools; markdown replies render as formatted text
- **Player compare** — *"Compare Messi vs Ronaldo"* returns national team Elo, club affiliation, and comp stats; follow up with *"what about in La Liga"* to re-compare in another competition (PD, PL, CL, etc.)
- **Conversational follow-ups** — short replies like *"explain"*, *"why?"*, or *"tell me more"* use prior chat turns (frontend history + session log) so you don't have to repeat yourself
- **Results & calibration** — sidebar shows graded predictions plus a **calibration** view: when the model says ~70%, do those picks win ~70% of the time?
- **Chat persists on refresh** — your session id is stored locally and prior messages reload from `/api/history`
- **Competition-aware chat** — the active sidebar tab (WC, PL, La Liga, etc.) is sent as `comp` so *"show the table"* or *"top scorers"* default to what you're viewing
- **Chat loading states** — animated typing indicator with context-aware messages (model run, player compare, backend wake-up on Render cold start)
- **Neutral venue toggle** — disable home-field advantage for WC / neutral-site games
- **Host venue in chat** — e.g. *"Predict Mexico vs South Korea in Mexico"* applies home advantage to Mexico; the 🏠 Home / 🏟 Neutral buttons also work in chat
- **Share prediction** — copy a formatted summary to clipboard, or copy a **share link** (`?predict=Mexico+vs+USA&comp=WC&neutral=1`) that re-runs the prediction on open

### Backend

- Hybrid **Elo + Dixon-Coles** model with weekly retrain (RPS backtest)
- football-data.org sync every 6 hours (GitHub Actions) — matches, squads, **top scorers** (500/comp)
- **Wikipedia squad sync** every 3 months — WC national squads (all 48 teams) + PL club wikitext; creates missing NT players and refreshes `line_role` / shirt numbers (free, no API key)
- **Free enrichment feeds** (`sync-enrich`) — FPL injury flags for the Premier League, Understat xG for top-5 leagues; optional API-Football key for non-PL injuries + match ratings (see [Data enrichment](#data-enrichment))
- Match-day sync every 30 min when fixtures are in the live window — results + grading only
- **Historical scorer backfill** — `backfill-scorers` pulls past seasons into `player_edition_stats` (additive; never wipes current season)
- LLM chat covers **all synced competitions** (PL, PD, BL1, SA, FL1, CL, DED, WC) via tool calls — not just PL/CL/WC
- Migrations run automatically before each Actions sync (`footballmind_migrate.py`)
- Rate-limited LLM chat (20 req/hr per IP) with friendly retry messaging; deep analysis limited to 10/hr
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
PostgreSQL (Neon)  ◄── footballmind_wikipedia.py (quarterly + enrich)
        │                    WC squads + PL club wikitext → line_role, shirts
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
| POST | `/api/chat` | Intent router + LLM fallback; accepts optional `history` and `comp` (sidebar context) for multi-turn follow-ups (rate-limited) |
| POST | `/api/analyze` | Claude match analysis (rate-limited) |
| GET | `/api/standings?comp=PL` | League table with per-row `zone` (UCL / UEL / relegation etc.) |
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
| GET | `/api/players/availability?team=…&comp=WC` | Manual injury/doubt flags for a team |
| POST | `/api/admin/availability` | Set player availability (admin key) |
| DELETE | `/api/admin/availability` | Clear manual availability flag (admin key) |
| GET | `/api/players/lineup?home=…&away=…` | Last H2H lineups |
| GET | `/api/predictions/calibration` | Confidence calibration bins (predicted vs actual win rate) |
| GET | `/api/predictions` | Graded prediction history + hit rate |

Shared query logic lives in `footballmind_services.py` (used by both Flask and MCP).

**Chat follow-ups:** The web UI sends the last few turns as `history` on each `/api/chat` request. The backend also loads recent turns from the `queries` table when `history` is omitted.

| Follow-up type | Example | What happens |
|----------------|---------|--------------|
| Explain / elaborate | *"explain"*, *"why?"*, *"tell me more"* | LLM reads history (no new tool calls) |
| Comp switch after compare | *"what about in La Liga"* | Re-runs `compare_players` with `comp=PD` and the same two names from history |
| New question | *"Predict Arsenal vs Chelsea"* | Rule-based intent or LLM with tools |

Short explain-style follow-ups skip the intent parser and go straight to the LLM with conversation context.

```json
POST /api/chat
{
  "message": "explain",
  "session_id": "abc-123",
  "comp": "PL",
  "history": [
    {"role": "user", "content": "Compare Messi vs Ronaldo"},
    {"role": "assistant", "content": "Messi edges Ronaldo on rating..."}
  ]
}
```

---

## Project structure

> **Everything lives at the repository root** — this is the single source of truth and
> exactly what gets deployed: Render runs `uvicorn footballmind_asgi:app` and GitHub
> Actions run `python footballmind_jobs.py`, both from the root. The `render.yaml` and
> workflow paths are root-relative, so do **not** nest the app in a subdirectory — a
> duplicate copy there will not deploy and will silently drift from what's live.

```
├── frontend/                  # Vite + React UI (GitHub Pages)
├── migrations/                # Ordered SQL schema migrations
├── scripts/
│   └── setup_cursor_mcp.py    # Wire ~/.cursor/mcp.json from .env
├── server.py                  # MCP server (stdio / streamable-http)
├── footballmind_asgi.py       # Combined REST + MCP for Render
├── footballmind_app.py        # Flask REST API
├── footballmind_services.py   # Shared read/query helpers
├── footballmind_standings_zones.py  # UCL / UEL / relegation zone rules
├── footballmind_enrich.py     # FPL + API-Football + Understat + Wikipedia enrichment
├── footballmind_wikipedia.py  # WC + PL squad sync from Wikipedia (free)
├── footballmind_roles.py      # Tactical line_role mapping + manual overrides
├── footballmind_sofifa.py     # EA FC / SoFIFA height, foot, overall (optional sync)
├── footballmind_footballdata_io.py  # Optional footballdata.io squad positions
├── footballmind_lineup.py     # Predicted XI + availability logic
├── footballmind_mcp_predict.py
├── footballmind_sync.py       # football-data.org ingestion
├── footballmind_jobs.py       # CLI: sync, sync-matchday, quick-refit, retrain, sync-wikipedia, …
├── scrape_squads.py           # Local CSV export for Wikipedia club squads (optional)
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

Migrations (`006` player positions, `007` scorer stats / lineup schema, `008` prediction team links, `009` player availability, `010` prediction dedupe per session, `011` captain flags, `012` enrichment tables, `013` EA FC attributes, `014` tactical `line_role`) run automatically at the start of each Actions job. To check locally:

```bash
python footballmind_migrate.py --status
```

**Note:** football-data.org free tier includes competition scorers but not per-match lineups/goals in match detail. Formation tools populate when that data becomes available (paid tier or live tournament detail).

### League table zones

Standings rows include a `zone` object when the team sits in a qualification or relegation band. The sidebar colours each row and shows a legend.

| Competition | Zones shown |
|-------------|-------------|
| PL, PD, SA | UCL (1–4), Europa (5), Conference (6), Relegation (bottom 3) |
| BL1, DED | UCL, Europa, Conference, Relegation play-off, Relegation |
| FL1 | UCL (1–3), Europa (4), Conference (5), Relegation (bottom 3) |
| CL | Round of 16 (1–8), Knockout play-offs (9–24), Eliminated |
| WC groups | Top 2 → knockout stage |

Zone rules live in `footballmind_standings_zones.py` (shared by the API and frontend). Cup-winner spot shuffles (e.g. FA Cup → Europa) are not modelled — league positions only.

Example API row:

```json
{
  "rank": 4,
  "team": "Arsenal FC",
  "Pts": 71,
  "GD": 28,
  "zone": { "id": "ucl", "label": "Champions League", "short": "UCL", "color": "#38bdf8" }
}
```

### Data enrichment

Complements football-data.org with zero/low-cost feeds. Run manually or as part of `sync`:

```bash
python footballmind_jobs.py sync-enrich   # enrichment only
python footballmind_jobs.py sync          # includes sync-enrich at the end
```

| Source | Env var | What it adds |
|--------|---------|--------------|
| **FPL API** | — | Premier League injury/doubt flags → `player_availability` (`source=fpl`) |
| **Understat** | — | Match xG for PL, La Liga, Bundesliga, Serie A, Ligue 1 |
| **API-Football** | `API_FOOTBALL_KEY` | Non-PL injuries + per-match player ratings (optional) |
| **Footballdata.io** | `FOOTBALLDATA_IO_KEY` | Club squad positions when `FOOTBALLDATA_IO_SYNC_ROLES=1` (optional) |
| **Wikipedia** | — | WC national squads (48 teams) + PL club wikitext → `line_role`, shirt numbers; creates missing NT players (free) |
| **SoFIFA / EA FC** | — (optional) | Height, weight, preferred/weak foot, overall/potential → `player_eafc_attributes` |

Set `WIKIPEDIA_SYNC=0` to skip Wikipedia during `sync-enrich`. For a full refresh:

```bash
python footballmind_jobs.py sync-wikipedia              # WC + PL clubs
python footballmind_jobs.py sync-wikipedia --wc-only    # national teams only
python footballmind_jobs.py sync-wikipedia --clubs-only # Premier League clubs only
```

GitHub Actions runs the same job **quarterly** (1 Jan / Apr / Jul / Oct) via `footballmind-wikipedia-sync.yml`. Expect ~10–15 minutes for a full WC pass.

**Local CSV review** (no DB writes):

```bash
python scrape_squads.py   # writes squads_output.csv for manual sanity-check
```

**API-Football free tier:** the key validates, but the free plan does **not** include the current season (2025/26) or the `last N fixtures` shortcut used for ratings — expect **0 rows** until you upgrade (~$10/mo). **FPL still covers PL injuries** without a key.

Manual availability (`source=manual`) is never overwritten by feed sync.

### Wikipedia squad sync

Primary source for **World Cup national-team rosters** and **tactical positions** when football-data.org only covers top-league club players.

| Source | Method | What it adds |
|--------|--------|--------------|
| `2026_FIFA_World_Cup_squads` | HTML wikitable via MediaWiki API | All 48 NT squads: name, shirt, caps, goals, club, FIFA position → `line_role` |
| PL club pages | Wikitext `{{fs player}}` templates | First-team squad only; maps to DB club names |

**Players outside top leagues** (Saudi Pro League, MLS, J2, etc.) are created in the DB from the WC page when missing — they get a `national` affiliation, coarse position, and optional WC edition caps/goals. Club names from Wikipedia are stored on the squad row but obscure clubs are not auto-created in `teams`.

Position mapping uses FIFA codes (GK / DF / MF / FW) → tactical roles (`GK`, `CB`, `CM`, `ST`, …). Manual overrides in `footballmind_roles.py` (e.g. Yamal → RW, Gyökeres → ST) take precedence.

### EA FC / SoFIFA attributes

Real-world APIs (football-data.org) do not expose height, weight, or weak foot. We optionally ingest those from [SoFIFA](https://sofifa.com) — EA FC’s public player database — into `player_eafc_attributes`.

| Field | Example | Used for |
|-------|---------|----------|
| `height_cm` / `weight_kg` | 180 / 72 | Squad tab, player compare, chat context |
| `preferred_foot` / `weak_foot` | Left / 3 | Compare, scouting-style questions |
| `overall_rating` / `potential` | 89 / 95 | Display; future tie-break when comp stats are sparse |

**What we do *not* use EA FC for:** match predictions and Elo still come from real results. Game overalls are **not** mixed into the hybrid W/D/L model.

**Sync (optional — not part of the default 6h job):**

```bash
pip install -r requirements-sofifa.txt   # soccerdata + selenium
python footballmind_jobs.py sync-sofifa --max 20 --visible   # visible Chrome (pass Cloudflare)
python footballmind_jobs.py sync-sofifa                      # top-5 European leagues (headless)
python footballmind_jobs.py sync-sofifa --teams Spain,Argentina
python footballmind_jobs.py sync-sofifa --import-cache         # offline: ~/soccerdata/data/SoFIFA/*.html
python footballmind_jobs.py sync-sofifa --version 250001     # pin EA FC release id (SOFIFA_VERSION_R)
```

SoFIFA is Cloudflare-protected. If headless sync returns 0 rows:

1. Run with **`--visible`** — a Chrome window opens; complete the Cloudflare check if prompted.
2. Or browse SoFIFA normally, then import cached HTML with **`--import-cache`** (soccerdata stores pages under `~/soccerdata/data/SoFIFA/`).

Club-league sync covers most WC squad players (via their domestic clubs). After sync, squad and compare API responses include an `eafc` object when matched.

**Not in soccerdata’s default export:** `read_player_ratings()` returns skill columns only — our parser adds height, weight, and foot data from the same profile HTML.

### Player stats & seasons

Scorer stats are stored **per competition edition** (season) in `player_edition_stats`. Each `(player_id, edition_id)` row is independent.

| Question | Answer |
|----------|--------|
| Does a new season wipe last season? | **No.** Sync creates a new `competition_editions` row; old stats remain. |
| What does compare use by default? | Current synced season for that comp; if a player has no row, the **best past synced season** in that comp. |
| How do I get Messi/Ronaldo La Liga numbers? | Run `backfill-scorers` (top ~100 scorers per season from the API — not full career totals for every player). |

When you roll into a new campaign, bump the season string in `COMPETITIONS` inside `footballmind_jobs.py` (e.g. `2025/26` → `2026/27`) and sync as usual.

### Predicted lineups & availability

`footballmind_lineup.py` builds a most-likely XI from squad depth and form scores:

1. **Formation** — prefers the team's most recent synced formation (including **4-3-2-1**); when lineups are synced, keeps last-match starters where possible; otherwise picks from modern club shapes before defaulting to 4-3-3.
2. **Starters** — ranked by comp appearances + recent starts, not goals alone (so mids/GKs aren't benched for fringe forwards).
3. **Red-card suspensions** — computed at runtime from `match_events` (player sent off in last finished match is excluded for the next fixture).
4. **Injuries / doubtful** — `player_availability` from FPL (PL), API-Football (other leagues, paid tier), or manual admin flags.

Flag a player out via the **Predicted XI** admin panel (append `?admin_key=YOUR_KEY` once to enable), the REST admin API, or SQL:

```bash
curl -X POST https://football-mind.onrender.com/api/admin/availability \
  -H "Authorization: Bearer $FOOTBALLMIND_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"player":"Pedri","team":"Spain","comp":"WC","status":"injured","reason":"Hamstring"}'
```

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/players/availability?team=…&comp=WC` | — | List manual flags for a team |
| POST | `/api/admin/availability` | Bearer admin key | Set injured / doubtful / suspended |
| DELETE | `/api/admin/availability` | Bearer admin key | Remove a manual flag |

Status values: `injured`, `doubtful`, `suspended` (manual only — red-card suspensions are computed from match events).

Legacy SQL:

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

# Optional: pull past season top scorers (Messi/Ronaldo La Liga era, etc.)
python footballmind_jobs.py backfill-scorers
# Or specific seasons:
python footballmind_jobs.py backfill-scorers 2019/20 2020/21

# REST API only
flask --app footballmind_app run --port 5000

# REST + MCP (matches Render locally)
uvicorn footballmind_asgi:app --reload --port 8000

# Frontend
cd frontend && cp .env.example .env   # VITE_API_BASE=http://127.0.0.1:8000
npm ci && npm run dev

# Frontend tests + production smoke check
cd frontend && npm ci && npm test && npm run build && npm run preview
# open http://127.0.0.1:4173/footballmind/ — chat header and input should render
```

```bash
python -m pytest tests/ -q   # backend unit tests (no DB)
cd frontend && npm ci && npm test   # Vitest (fm/* helpers + deeplink)
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
| `compare_players` | Side-by-side stats; optional `comp` (current or best past synced season) |

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
| Scheduled jobs | GitHub Actions | `footballmind-jobs` (sync 6h, retrain Mon), `footballmind-matchday-sync` (30m), `footballmind-wikipedia-sync` (quarterly), `footballmind-tests` (pytest on push) |

### Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | Render + Actions secret | Neon pooled connection string |
| `FOOTBALLMIND_ADMIN_KEY` | Render env var | Bearer token for `/api/admin/*` (optional; falls back to `MCP_API_KEY`) |
| `MCP_API_KEY` | Render + local `.env` | Bearer token for remote MCP at `/mcp` (optional for website) |
| `FOOTBALL_DATA_API_KEY` | Actions secret | football-data.org API key |
| `FOOTBALLDATA_IO_KEY` | Actions secret (optional) | footballdata.io squad positions |
| `API_FOOTBALL_KEY` | Actions secret (optional) | api-sports.io key for enrichment; free tier limited to older seasons |
| `ANTHROPIC_API_KEY` | Render env var | Claude API (LLM chat + deep analysis) |
| `FRONTEND_ORIGIN` | Render env var | GitHub Pages URL for CORS (or `*`) |
| `VITE_API_BASE` | GitHub Pages repo variable | `https://football-mind.onrender.com` |
| `WIKIPEDIA_SYNC` | Actions / local (optional) | Set `0` to disable Wikipedia during `sync-enrich` (default: on) |

**Never commit `.env` or put secrets in `VITE_*` vars** — those are baked into the public frontend bundle.

### Security checklist

Audited for common leaks — current status:

| Check | Status |
|-------|--------|
| `.env` gitignored; no `.env` in git history | OK |
| No API keys / DB URLs in tracked source files | OK |
| GitHub Actions use `secrets.*` (not inline values) | OK |
| `VITE_API_BASE` is a public URL only (Pages workflow) | OK |
| MCP `/mcp` requires `MCP_API_KEY` when set | OK |
| Admin API requires Bearer token | OK |

**Do not commit:** `.env`, `mcp.json` (local Cursor config with `DATABASE_URL`), `squads_output.csv` / `squads_insert.sql` (scraper artifacts).

**Admin key UX:** the injury admin panel accepts `?admin_key=…` once; the key is stored in **browser localStorage**, not in the frontend bundle. Avoid sharing URLs that still contain the query param (browser history / referrers).

**Rotate if exposed:** `FOOTBALL_DATA_API_KEY`, `API_FOOTBALL_KEY`, `FOOTBALLDATA_IO_KEY`, `ANTHROPIC_API_KEY`, `MCP_API_KEY` / `FOOTBALLMIND_ADMIN_KEY`, and Neon credentials via the Neon dashboard.

### Render checklist (existing service)

If you already have a Render web service, updating does **not** break the site:

- [ ] Push latest `main` (triggers auto-deploy)
- [ ] Update **Start Command** to `uvicorn footballmind_asgi:app --host 0.0.0.0 --port $PORT`
- [ ] Add `MCP_API_KEY` (optional — only secures `/mcp`)
- [ ] Confirm `/api/health` returns `{"status":"ok"}` after deploy

### GitHub Pages (frontend)

- **Live URL:** [nmahjan.github.io/footballmind](https://nmahjan.github.io/footballmind) — built from `frontend/` on every push to `main` (`deploy-pages` workflow).
- **Repo variable:** set `VITE_API_BASE` under **Settings → Secrets and variables → Actions → Variables** to your Render URL (e.g. `https://football-mind.onrender.com`). Without it, the UI runs in offline demo mode.
- **Manual redeploy:** Actions → **deploy-pages** → **Run workflow** (useful if a deploy job failed while the build succeeded).
- **Blank page after deploy:** open DevTools → Console. A runtime error (e.g. missing React hook import) prevents the app from mounting — `#root` stays empty even though `index.html` loads. Fix the JS error, push to `main`, and wait for `deploy-pages` to finish. Smoke-test locally with `npm run build && npm run preview` before merging.

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
