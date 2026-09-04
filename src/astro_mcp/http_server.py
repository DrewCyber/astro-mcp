"""Streamable-HTTP transport for remote MCP clients (claude.ai custom connectors).

Local stdio clients keep using ``astro_mcp.server._run``; this module exposes the
same low-level ``Server`` over HTTP for hosts that cannot spawn processes
(Render, Koyeb, Cloud Run, ``cloudflared`` tunnels).
"""

from __future__ import annotations

import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from astro_mcp.config import settings
from astro_mcp.server import create_server

logger = logging.getLogger(__name__)


async def health(_request: Request) -> JSONResponse:
    """Liveness probe: also the target for free keepalive pings (UptimeRobot)."""
    return JSONResponse({"status": "ok"})


def create_asgi_app() -> Starlette:
    """Build the streamable-HTTP app from the SDK's own wiring.

    ``stateless_http`` gives every request a fresh transport, so the app works
    behind load-balancing proxies (Render, Koyeb, Cloud Run) without session
    affinity. ``json_response`` lets POST replies be plain JSON instead of an
    SSE stream, which some intermediaries relay more reliably.

    ``host="0.0.0.0"`` only disables the SDK's localhost DNS-rebinding guard —
    that guard would reject tunnelled traffic (cloudflared) arriving with a
    foreign ``Host`` header. Actual binding is uvicorn's job (``HOST``/``PORT``).
    """
    server = create_server()
    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        custom_starlette_routes=[Route("/health", health, methods=["GET"])],
    )


def run_http() -> None:
    """Serve the streamable-HTTP transport on the configured host and port."""
    import uvicorn

    from astro_mcp.core.ephemeris_provider import init_ephemeris

    # Same fail-fast contract as the stdio path: crash at startup rather than
    # serve every request from the low-precision Moshier fallback.
    init_ephemeris()

    uvicorn.run(
        create_asgi_app(),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
