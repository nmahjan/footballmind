#!/usr/bin/env python3
"""Merge FootballMind MCP entries into ~/.cursor/mcp.json from .env."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
MCP = Path.home() / ".cursor" / "mcp.json"


def load_env():
    out = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def main():
    env = load_env()
    db = env.get("DATABASE_URL")
    mcp_key = env.get("MCP_API_KEY", "REPLACE_WITH_MCP_API_KEY")
    if not db:
        raise SystemExit("DATABASE_URL missing in footballmind/.env")

    cfg = {"mcpServers": {}}
    if MCP.exists():
        try:
            cfg = json.loads(MCP.read_text())
        except json.JSONDecodeError:
            print("Warning: existing mcp.json was invalid; replacing footballmind entries only.")
            cfg = {"mcpServers": {}}
    cfg.setdefault("mcpServers", {})

    py = ROOT / ".venv" / "bin" / "python"
    cfg["mcpServers"]["footballmind"] = {
        "command": str(py),
        "args": [str(ROOT / "server.py")],
        "env": {"DATABASE_URL": db},
    }
    render_base = env.get("RENDER_URL", "https://football-mind.onrender.com")
    cfg["mcpServers"]["footballmind-remote"] = {
        "type": "http",
        "url": f"{render_base.rstrip('/')}/mcp",
        "headers": {"Authorization": f"Bearer {mcp_key}"},
    }

    MCP.parent.mkdir(parents=True, exist_ok=True)
    MCP.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"Updated {MCP}")
    if mcp_key == "REPLACE_WITH_MCP_API_KEY":
        print("Set MCP_API_KEY in .env (openssl rand -hex 24) and on Render, then re-run.")


if __name__ == "__main__":
    main()
