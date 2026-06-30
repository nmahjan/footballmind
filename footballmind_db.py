"""
FootballMind -- database connection factory.

Single place every module gets its Postgres connection from. Reads
DATABASE_URL from the environment, loading a local .env first if present
(see .env.example). Use Neon's *pooled* connection string in DATABASE_URL --
that gives connection pooling at the server side, so each process can keep
using plain short-lived psycopg connections.
"""

import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_CONNECT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_BASE_SEC = 3.0


def _ipv4_hostaddr(host: str | None) -> str | None:
    """Resolve host to IPv4 only.

    GitHub Actions runners often lack working IPv6 routing; psycopg otherwise
    tries every A/AAAA record and can hang for minutes before failing.
    """
    if not host:
        return None
    try:
        infos = socket.getaddrinfo(
            host, 5432, family=socket.AF_INET, type=socket.SOCK_STREAM)
        return infos[0][4][0] if infos else None
    except OSError:
        return None


def get_connection(max_retries: int = DEFAULT_MAX_RETRIES,
                   connect_timeout: int = DEFAULT_CONNECT_TIMEOUT):
    import psycopg
    from psycopg import OperationalError

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill it in, "
            "or export DATABASE_URL (use Neon's pooled connection string).")

    host = urlparse(url).hostname
    hostaddr = _ipv4_hostaddr(host)
    kwargs: dict = {"connect_timeout": connect_timeout}
    if hostaddr:
        kwargs["hostaddr"] = hostaddr

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return psycopg.connect(url, **kwargs)
        except OperationalError as exc:
            last_err = exc
            if attempt + 1 >= max_retries:
                break
            delay = DEFAULT_RETRY_BASE_SEC * (2 ** attempt)
            time.sleep(delay)

    assert last_err is not None
    raise last_err


def release_transaction(conn) -> None:
    """Close the current transaction after read-only queries.

    Neon kills connections that sit idle *inside* an open transaction (used by
    retrain/backtest while scipy runs for several minutes).
    """
    try:
        conn.commit()
    except Exception:
        conn.rollback()
