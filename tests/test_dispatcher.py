"""Dispatcher-level tests through server.call_tool.

These exercise the real dispatch round-trip — handler lookup, Pydantic
validation, error mapping, success-path serialization — rather than calling
tool functions directly.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp import types

from astro_mcp.server import create_server


@pytest.fixture(scope="module")
def call_handler():
    server = create_server()
    entry = server.get_request_handler("tools/call")
    assert entry is not None
    return entry.handler


async def _call(call_handler, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await call_handler(
        None,  # ServerRequestContext — the dispatcher never reads it
        types.CallToolRequestParams(name=name, arguments=arguments),
    )
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    return json.loads(content.text)


async def test_unknown_tool_returns_structured_error(call_handler) -> None:
    payload = await _call(call_handler, "no_such_tool", {})
    assert payload["error"] is True
    assert payload["code"] == "UNKNOWN_TOOL"
    assert "no_such_tool" in payload["message"]
    # The hint must help the model recover: every registered tool is listed.
    hint = payload["hint"]
    assert "calculate_natal_chart" in hint and "get_ephemeris" in hint


async def test_malformed_arguments_name_the_offending_fields(call_handler) -> None:
    payload = await _call(call_handler, "calculate_natal_chart", {"birth_date": "1990-06-15"})
    assert payload["error"] is True
    assert payload["code"] == "INPUT_ERROR"
    hint = payload.get("hint", "")
    assert "birth_time" in hint or "birth_location" in hint


async def test_unknown_argument_is_rejected_not_ignored(call_handler) -> None:
    payload = await _call(
        call_handler,
        "get_ephemeris",
        {"planet": "Su", "date_from": "2026-01-01", "date_to": "2026-01-02",
         "planetz": "Su"},
    )
    assert payload["error"] is True
    assert payload["code"] == "INPUT_ERROR"
    assert "planetz" in payload.get("hint", "")


async def test_success_path_never_carries_an_error_body(call_handler) -> None:
    payload = await _call(
        call_handler,
        "get_ephemeris",
        {"planet": "Su", "date_from": "2026-01-01", "date_to": "2026-01-02"},
    )
    assert not payload.pop("error", False)
    assert payload["planet"] == "Su"
    assert len(payload["rows"]) == 2


async def test_astro_error_maps_to_structured_payload(call_handler) -> None:
    """A tool raising AstroError must surface its code verbatim, with no
    INTERNAL_ERROR flattening."""
    payload = await _call(
        call_handler,
        "calculate_rectification_hints",
        {
            "birth_date": "1990-06-15",
            "birth_location": {"lat": 55.75, "lon": 37.62},
            "events": [{"date": "2015-06-15", "type": "marriage"}],
            "birth_time": "12:00",
        },
    )
    assert payload["error"] is True
    assert payload["code"] == "TOO_FEW_EVENTS"


async def test_internal_errors_do_not_leak_internals(
    call_handler, monkeypatch: pytest.MonkeyPatch
) -> None:
    import astro_mcp.tools.ephemeris as ephemeris_module

    def boom(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("secret value /home/user/.secrets/api_key")

    monkeypatch.setattr(ephemeris_module, "get_ephemeris", boom)
    payload = await _call(
        call_handler,
        "get_ephemeris",
        {"planet": "Su", "date_from": "2026-01-01", "date_to": "2026-01-02"},
    )
    assert payload["error"] is True
    assert payload["code"] == "INTERNAL_ERROR"
    blob = json.dumps(payload)
    assert "secret" not in blob and "/home" not in blob


async def test_broken_tool_module_keeps_the_structured_contract(
    call_handler, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lazy import that explodes must not escape into transport-level prose."""
    import astro_mcp.server as server_module

    def boom(name: str):
        raise ImportError("broken optional dependency")

    monkeypatch.setattr(server_module, "_load_tool", boom)
    payload = await _call(
        call_handler,
        "get_ephemeris",
        {"planet": "Su", "date_from": "2026-01-01", "date_to": "2026-01-02"},
    )
    assert payload["error"] is True
    assert payload["code"] == "INTERNAL_ERROR"
