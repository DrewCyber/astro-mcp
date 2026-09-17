"""R16: SDK header validation and admission, without traffic flooding."""

import asyncio

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsError
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from astro_mcp.config import Settings, settings
from astro_mcp.http_server import BoundedConcurrencyMiddleware, create_asgi_app

ACCEPT_HEADERS = {"Accept": "application/json, text/event-stream"}
PAYLOAD = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


async def invoke(app, path="/mcp", method="POST"):
    messages = []

    async def receive():
        raise AssertionError("Admission must not consume the request body")

    async def send(message):
        messages.append(message)

    await app({"type": "http", "path": path, "method": method}, receive, send)
    return messages


class BlockingApp:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        if scope["path"] in ("/mcp", "/mcp/"):
            self.entered.set()
            await self.release.wait()
        await JSONResponse({"ok": True})(scope, receive, send)


@pytest.mark.parametrize("path,method", [("/mcp", "POST"), ("/mcp/", "GET")])
async def test_overflow_rejected_without_waiting(path, method):
    inner = BlockingApp()
    middleware = BoundedConcurrencyMiddleware(inner, max_concurrent=1)
    first = asyncio.create_task(invoke(middleware))
    try:
        await asyncio.wait_for(inner.entered.wait(), timeout=2)
        messages = await asyncio.wait_for(invoke(middleware, path, method), timeout=2)
        assert messages[0]["status"] == 503
        assert int(dict(messages[0]["headers"])[b"retry-after"]) > 0
        assert inner.calls == 1
        assert not first.done()
    finally:
        inner.release.set()
        result = await first
    assert result[0]["status"] == 200
    assert middleware._active == 0


async def test_health_bypasses_saturated_limit():
    inner = BlockingApp()
    middleware = BoundedConcurrencyMiddleware(inner, max_concurrent=1)
    first = asyncio.create_task(invoke(middleware))
    try:
        await asyncio.wait_for(inner.entered.wait(), timeout=2)
        messages = await asyncio.wait_for(invoke(middleware, "/health", "GET"), timeout=2)
        assert messages[0]["status"] == 200
        assert middleware._active == 1
    finally:
        inner.release.set()
        await first
    assert middleware._active == 0


async def test_non_http_scope_passthrough():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope)

    middleware = BoundedConcurrencyMiddleware(inner, max_concurrent=1)
    scope = {"type": "lifespan"}
    await middleware(scope, None, None)
    assert seen == [scope]
    assert middleware._active == 0


async def test_release_after_exception_allows_next_request():
    calls = 0

    async def inner(scope, receive, send):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        await JSONResponse({"ok": True})(scope, receive, send)

    middleware = BoundedConcurrencyMiddleware(inner, max_concurrent=1)
    with pytest.raises(RuntimeError, match="boom"):
        await invoke(middleware)
    assert middleware._active == 0
    assert (await invoke(middleware))[0]["status"] == 200
    assert middleware._active == 0


async def test_release_after_cancellation_allows_next_request():
    inner = BlockingApp()
    middleware = BoundedConcurrencyMiddleware(inner, max_concurrent=1)
    first = asyncio.create_task(invoke(middleware))
    try:
        await asyncio.wait_for(inner.entered.wait(), timeout=2)
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    assert middleware._active == 0
    inner.release.set()
    assert (await invoke(middleware))[0]["status"] == 200
    assert middleware._active == 0


@pytest.fixture(autouse=True)
def isolated_http_settings(monkeypatch):
    monkeypatch.setattr(settings, "host", "127.0.0.1")
    monkeypatch.setattr(settings, "http_allowed_hosts", None)
    monkeypatch.setattr(settings, "http_allowed_origins", None)
    monkeypatch.setattr(settings, "http_max_concurrent_requests", 16)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_local_bindings_enable_sdk_guard(monkeypatch, host):
    monkeypatch.setattr(settings, "host", host)
    with TestClient(create_asgi_app(), base_url="http://localhost:8080") as client:
        assert client.post("/mcp", json=PAYLOAD, headers=ACCEPT_HEADERS).status_code == 200
        response = client.post(
            "/mcp", json=PAYLOAD, headers={**ACCEPT_HEADERS, "Host": "foreign.example"}
        )
        assert response.status_code == 421


@pytest.mark.parametrize(
    "origin,status", [("http://localhost:8080", 200), ("https://foreign.example", 403)]
)
def test_local_origin_guard(origin, status):
    with TestClient(create_asgi_app(), base_url="http://localhost:8080") as client:
        response = client.post("/mcp", json=PAYLOAD, headers={**ACCEPT_HEADERS, "Origin": origin})
        assert response.status_code == status


def test_sdk_automatic_guard_requires_explicit_port():
    with TestClient(create_asgi_app(), base_url="http://localhost") as client:
        assert client.post("/mcp", json=PAYLOAD, headers=ACCEPT_HEADERS).status_code == 421


def test_public_default_stateless_direct_mcp(monkeypatch):
    monkeypatch.setattr(settings, "host", "0.0.0.0")
    with TestClient(create_asgi_app(), base_url="https://public.example") as client:
        response = client.post(
            "/mcp",
            json=PAYLOAD,
            headers={**ACCEPT_HEADERS, "Origin": "https://client.example"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert response.json()["result"]["tools"]
        assert "mcp-session-id" not in response.headers
        assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "host,origin,status",
    [
        ("public.example", None, 200),
        ("public.example:8443", "https://client.example", 200),
        ("foreign.example", None, 421),
        ("public.example", "https://foreign.example", 403),
    ],
)
def test_explicit_public_allowlists(monkeypatch, host, origin, status):
    monkeypatch.setattr(settings, "host", "0.0.0.0")
    monkeypatch.setattr(settings, "http_allowed_hosts", ["public.example", "public.example:*"])
    monkeypatch.setattr(settings, "http_allowed_origins", ["https://client.example"])
    headers = {**ACCEPT_HEADERS, "Host": host}
    if origin is not None:
        headers["Origin"] = origin
    with TestClient(create_asgi_app()) as client:
        assert client.post("/mcp", json=PAYLOAD, headers=headers).status_code == status


@pytest.mark.parametrize(
    "hosts,origins,status",
    [
        ([], None, 421),
        (None, ["https://client.example"], 421),
        (["public.example"], None, 403),
    ],
)
def test_partial_or_empty_allowlists_fail_closed(monkeypatch, hosts, origins, status):
    monkeypatch.setattr(settings, "host", "0.0.0.0")
    monkeypatch.setattr(settings, "http_allowed_hosts", hosts)
    monkeypatch.setattr(settings, "http_allowed_origins", origins)
    with TestClient(create_asgi_app(), base_url="https://public.example") as client:
        response = client.post(
            "/mcp",
            json=PAYLOAD,
            headers={**ACCEPT_HEADERS, "Origin": "https://client.example"},
        )
        assert response.status_code == status
        assert client.get("/health").status_code == 200


def test_http_settings_json_environment(monkeypatch):
    monkeypatch.setenv("HTTP_ALLOWED_HOSTS", '["public.example", "public.example:*"]')
    monkeypatch.setenv("HTTP_ALLOWED_ORIGINS", '["https://client.example"]')
    monkeypatch.setenv("HTTP_MAX_CONCURRENT_REQUESTS", "2")
    configured = Settings(_env_file=None)
    assert configured.http_allowed_hosts == ["public.example", "public.example:*"]
    assert configured.http_allowed_origins == ["https://client.example"]
    assert configured.http_max_concurrent_requests == 2


@pytest.mark.parametrize(
    "name,value",
    [
        ("HTTP_ALLOWED_HOSTS", "not-json"),
        ("HTTP_ALLOWED_ORIGINS", "[12]"),
        ("HTTP_MAX_CONCURRENT_REQUESTS", "0"),
    ],
)
def test_invalid_http_settings_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises((ValidationError, SettingsError)):
        Settings(_env_file=None)
