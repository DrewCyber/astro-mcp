"""Protocol envelope and sanitized execution errors."""

import json

import pytest
from mcp.types import CallToolRequestParams

from astro_mcp import server
from astro_mcp.core.errors import AstroError

ARGS = {"planet": "Su", "date_from": "2026-01-01", "date_to": "2026-01-02"}


@pytest.mark.parametrize("failure", [ValueError("private-path"), RuntimeError("private-path"),
                                     AstroError("INPUT_ERROR", "Expected public error")])
async def test_execution_errors_mark_envelope(monkeypatch, failure):
    def fail(**kwargs):
        raise failure
    monkeypatch.setattr(server, "_load_tool", lambda name: fail)
    result = await server._call_tool(None, CallToolRequestParams(name="get_ephemeris", arguments=ARGS))
    assert result.is_error is True
    payload = json.loads(result.content[0].text)
    assert payload["code"] == ("INPUT_ERROR" if isinstance(failure, AstroError) else "INTERNAL_ERROR")
    assert "private-path" not in str(payload)


@pytest.mark.parametrize("name,args", [("missing", {}), ("get_ephemeris", {})])
async def test_lookup_and_validation_errors_mark_envelope(name, args):
    result = await server._call_tool(None, CallToolRequestParams(name=name, arguments=args))
    assert result.is_error is True


async def test_serialization_failure_is_sanitized(monkeypatch):
    monkeypatch.setattr(server, "_load_tool", lambda name: lambda **kwargs: {"value": object()})
    result = await server._call_tool(None, CallToolRequestParams(name="get_ephemeris", arguments=ARGS))
    assert result.is_error is True
    assert json.loads(result.content[0].text)["code"] == "INTERNAL_ERROR"


async def test_success_envelope(monkeypatch):
    monkeypatch.setattr(server, "_load_tool", lambda name: lambda **kwargs: {"ok": True})
    result = await server._call_tool(None, CallToolRequestParams(name="get_ephemeris", arguments=ARGS))
    assert result.is_error is False
