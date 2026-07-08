"""Database connection helpers."""

import socket

import pytest

from footballmind_db import _ipv4_hostaddr, get_connection


def test_ipv4_hostaddr_resolves_localhost():
    addr = _ipv4_hostaddr("localhost")
    assert addr in ("127.0.0.1", "::1") or addr.startswith("127.")


def test_ipv4_hostaddr_unknown_host():
    assert _ipv4_hostaddr("this-host-definitely-does-not-exist.invalid") is None


def test_get_connection_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_connection()


def test_get_connection_retries_on_operational_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@example.com/db")
    monkeypatch.setattr("footballmind_db._ipv4_hostaddr", lambda _h: "203.0.113.1")

    calls = {"n": 0}

    class FakeOperationalError(Exception):
        pass

    def fake_connect(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeOperationalError("connection timeout expired")
        return object()

    import psycopg
    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(psycopg, "OperationalError", FakeOperationalError)
    monkeypatch.setattr("footballmind_db.time.sleep", lambda _s: None)

    conn = get_connection(max_retries=5, connect_timeout=1)
    assert conn is not None
    assert calls["n"] == 3
