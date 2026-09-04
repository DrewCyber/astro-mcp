"""Streamable-HTTP transport: health probe and stateless JSON-RPC handling."""

import pytest
from starlette.testclient import TestClient

from astro_mcp.config import settings
from astro_mcp.http_server import create_asgi_app
from astro_mcp.server import _TOOL_REGISTRY

#: Streamable HTTP requires the client to accept both response modes.
ACCEPT_HEADERS = {"Accept": "application/json, text/event-stream"}

INITIALIZE_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.0"},
    },
}


@pytest.fixture()
def client():
    # Entering the context manager runs the lifespan, which starts the
    # StreamableHTTPSessionManager — exactly what uvicorn does in production.
    with TestClient(create_asgi_app()) as test_client:
        yield test_client


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_initialize(client):
    response = client.post("/mcp", json=INITIALIZE_PAYLOAD, headers=ACCEPT_HEADERS)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["serverInfo"]["name"] == "astro-mcp"


def test_mcp_no_redirect_on_exact_path(client):
    # POST /mcp must be answered directly, never via a 307 to /mcp/ — some
    # MCP clients do not follow redirects.
    response = client.post(
        "/mcp", json=INITIALIZE_PAYLOAD, headers=ACCEPT_HEADERS, follow_redirects=False
    )
    assert response.status_code == 200


def test_mcp_trailing_slash_also_served(client):
    response = client.post("/mcp/", json=INITIALIZE_PAYLOAD, headers=ACCEPT_HEADERS)
    assert response.status_code == 200


def test_mcp_stateless_request_needs_no_initialize(client):
    # claude.ai custom connectors hit the endpoint without a session; every
    # request must stand alone (manager runs with stateless=True).
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=ACCEPT_HEADERS,
    )
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == set(_TOOL_REGISTRY)


def test_mcp_rejects_wrong_accept_header(client):
    response = client.post(
        "/mcp",
        json=INITIALIZE_PAYLOAD,
        headers={"Accept": "text/plain"},
    )
    assert response.status_code == 406


def test_mcp_get_requires_sse_accept_header(client):
    # A GET with an SSE Accept header opens a long-lived stream in the SDK
    # transport (it never terminates inside TestClient), so pin only the
    # deterministic rejection path: GET without it must be a 406.
    response = client.get("/mcp", headers={"Accept": "application/json"})
    assert response.status_code == 406


def test_main_dispatches_http(monkeypatch):
    from astro_mcp.__main__ import main

    monkeypatch.setattr(settings, "transport", "http")
    monkeypatch.setattr("astro_mcp.http_server.run_http", lambda: None)
    main()  # must not touch the stdio path


def test_main_dispatches_stdio(monkeypatch):
    from astro_mcp.__main__ import main

    ran = False

    async def fake_run() -> None:
        nonlocal ran
        ran = True

    monkeypatch.setattr(settings, "transport", "stdio")
    monkeypatch.setattr("astro_mcp.server._run", fake_run)
    main()
    assert ran
