"""
FootballMind -- database connection factory.

Single place every module gets its Postgres connection from. Reads
DATABASE_URL from the environment, loading a local .env first if present
(see .env.example). Use Neon's *pooled* connection string in DATABASE_URL --
that gives connection pooling at the server side, so each process can keep
using plain short-lived psycopg connections.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def get_connection():
    import psycopg                       # lazy so pure-logic imports don't need it
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill it in, "
            "or export DATABASE_URL (use Neon's pooled connection string).")
    return psycopg.connect(url)
