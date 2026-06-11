# Football Mind

A football intelligence app for the Premier League and World Cup 2026. Ask about matches in plain English and get data-driven predictions with confidence ratings.

**Stack:** Python (Flask + Dixon-Coles + Elo) · React (Vite) · Neon Postgres · Render · GitHub Pages

## Features

- Natural-language match predictions via Claude (free-form chat)
- Dixon-Coles / Elo hybrid model with credibility-weighted cold start
- Premier League live standings and accuracy tracking
- World Cup 2026 fixture predictions (48 teams, seeded from world Elo ratings)
- Auto-retraining pipeline (GitHub Actions cron — sync every 6h, retrain weekly)
- MCP server (`server.py`) for tool use in Claude Desktop / Cursor

## Structure

```
footballmind/   Python backend (Flask API, model, sync, migrations)
frontend/       Vite + React frontend
.github/        Workflows: pages deploy + scheduled data jobs
```

## Quick start

```bash
cd footballmind
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, FOOTBALL_DATA_API_KEY, ANTHROPIC_API_KEY
python footballmind_migrate.py
python footballmind_jobs.py sync --full
python footballmind_jobs.py seed-elo
python footballmind_jobs.py retrain
flask --app footballmind_app run
```

## Deploy

- **Database:** Neon free tier (use pooled connection string)
- **Backend:** Render web service — root dir `footballmind`, start command `gunicorn footballmind_app:app`
- **Frontend:** GitHub Pages via `.github/workflows/pages.yml` (set `VITE_API_BASE` repo variable to Render URL)
- **Jobs:** GitHub Actions secrets `DATABASE_URL` + `FOOTBALL_DATA_API_KEY`
