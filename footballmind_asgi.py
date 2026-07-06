"""
Combined ASGI app: Flask REST API at / + MCP streamable-http at /mcp.

Used on Render so one service exposes both the website backend and remote MCP.
Start: uvicorn footballmind_asgi:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount

load_dotenv()

from footballmind_app import app as flask_app  # noqa: E402
from server import mcp  # noqa: E402

# Optional Bearer token for remote MCP (set MCP_API_KEY on Render)
_mcp_key = os.environ.get("MCP_API_KEY", "")


class _McpAuthMiddleware:
    """ASGI middleware: require Authorization: Bearer <MCP_API_KEY> when set."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if _mcp_key and scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            expected = f"Bearer {_mcp_key}"
            if auth != expected:
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [[b"content-type", b"text/plain"]],
                })
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await self.app(scope, receive, send)


_mcp_app = mcp.streamable_http_app()
if _mcp_key:
    _mcp_app = _McpAuthMiddleware(_mcp_app)

app = Starlette(routes=[
    Mount("/mcp", app=_mcp_app),
    Mount("/", app=WSGIMiddleware(flask_app)),
])
