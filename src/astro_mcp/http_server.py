"""Streamable-HTTP transport for remote MCP clients (claude.ai custom connectors).

Local stdio clients keep using ``astro_mcp.server._run``; this module exposes the
same low-level ``Server`` over HTTP for hosts that cannot spawn processes
(Render, Koyeb, Cloud Run, ``cloudflared`` tunnels).
"""

from __future__ import annotations

import logging

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from astro_mcp.config import settings
from astro_mcp.server import create_server

logger = logging.getLogger(__name__)


class BoundedConcurrencyMiddleware:
    """Cap concurrently active ``/mcp`` requests; reject overflow with 503.

    Admission never waits or reads the body. Slots cover the whole ASGI
    exchange, including streaming responses, and are released on cancellation
    or failure. Other paths (notably ``/health``) and lifespan bypass the cap.
    The counter is local to this app's event loop, not shared across workers;
    it does not prevent synchronous calculations from blocking that loop.
    """

    def __init__(self, app: ASGIApp, max_concurrent: int) -> None:
        self.app = app
        self.max_concurrent = max_concurrent
        self._active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in ("/mcp", "/mcp/"):
            await self.app(scope, receive, send)
            return

        # No await between check and increment: atomic within the serving loop.
        if self._active >= self.max_concurrent:
            response = PlainTextResponse(
                "Too many concurrent requests; retry shortly.",
                status_code=503,
                headers={"Retry-After": "2"},
            )
            await response(scope, receive, send)
            return

        self._active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._active -= 1


async def health(_request: Request) -> JSONResponse:
    """Liveness probe: also the target for free keepalive pings (UptimeRobot)."""
    return JSONResponse({"status": "ok"})


def create_asgi_app() -> Starlette:
    """Build the streamable-HTTP app from the SDK's own wiring.

    ``stateless_http`` gives every request a fresh transport, so the app works
    behind load-balancing proxies (Render, Koyeb, Cloud Run) without session
    affinity. ``json_response`` lets POST replies be plain JSON instead of an
    SSE stream, which some intermediaries relay more reliably.

    Passing ``host=settings.host`` keeps the SDK's automatic DNS-rebinding
    guard for loopback bindings (loopback Host/Origin values with explicit
    ports are accepted), while a public deployment binding
    ``0.0.0.0`` disables the automatic guard — that guard would otherwise
    reject tunnelled traffic (cloudflared) arriving with a foreign ``Host``
    header. Public deployments should then set ``HTTP_ALLOWED_HOSTS`` /
    ``HTTP_ALLOWED_ORIGINS`` to restore explicit header validation through the
    SDK's ``TransportSecuritySettings``.

    A concurrency middleware bounds the number of simultaneously active
    ``/mcp`` requests; overflow is rejected with 503 (see
    ``BoundedConcurrencyMiddleware``). Actual binding is still uvicorn's job
    (``HOST``/``PORT``).
    """
    server = create_server()
    transport_security: TransportSecuritySettings | None = None
    if settings.http_allowed_hosts is not None or settings.http_allowed_origins is not None:
        # Explicit public allowlist: delegate Host/Origin validation to the SDK
        # middleware regardless of the bind address. Patterns support
        # ``host:*`` / ``scheme://host:*`` suffixes like the SDK's localhost
        # guard. No auth is introduced — this only hardens header validation.
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.http_allowed_hosts or [],
            allowed_origins=settings.http_allowed_origins or [],
        )
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host=settings.host,
        transport_security=transport_security,
        custom_starlette_routes=[Route("/health", health, methods=["GET"])],
    )
    app.add_middleware(
        BoundedConcurrencyMiddleware, max_concurrent=settings.http_max_concurrent_requests
    )
    return app


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
