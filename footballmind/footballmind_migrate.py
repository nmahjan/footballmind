"""
FootballMind -- migration runner.

Applies migrations/*.sql in lexical order, exactly once, recording each in a
schema_migrations ledger. Re-running is always safe: applied files are skipped.

Usage:
    python footballmind_migrate.py            # apply pending migrations
    python footballmind_migrate.py --status   # show applied / pending
"""

import sys
from pathlib import Path

from footballmind_db import get_connection

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_ledger(conn):
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  filename   TEXT PRIMARY KEY,"
            "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    conn.commit()


def _applied(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def migrate(conn):
    """Apply every pending migration in order. Each file runs in its own
    transaction: a failure rolls back that file and stops the run, leaving
    everything before it applied and recorded."""
    _ensure_ledger(conn)
    done = _applied(conn)
    pending = [p for p in sorted(MIGRATIONS_DIR.glob("*.sql")) if p.name not in done]
    for path in pending:
        try:
            with conn.cursor() as cur:
                # Fail fast if a lock is held by another connection (e.g. the
                # live web service) rather than blocking indefinitely.
                cur.execute("SET lock_timeout = '10s'")
                cur.execute(path.read_text())
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)",
                            (path.name,))
            conn.commit()
            print(f"[migrate] applied {path.name}")
        except Exception:
            conn.rollback()
            print(f"[migrate] FAILED {path.name} -- rolled back, stopping",
                  file=sys.stderr)
            raise
    if not pending:
        print("[migrate] up to date")
    return [p.name for p in pending]


def status(conn):
    _ensure_ledger(conn)
    done = _applied(conn)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        mark = "applied" if path.name in done else "pending"
        print(f"  {mark:8s} {path.name}")


if __name__ == "__main__":
    with get_connection() as connection:
        if "--status" in sys.argv:
            status(connection)
        else:
            migrate(connection)
