"""MCP server — registers all 14 astrological tools."""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from collections.abc import Callable
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from astro_mcp.config import settings
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import to_compact_json
from astro_mcp.schemas import TOOL_INPUTS, json_schema_for, tool_description

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.WARNING),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=to_compact_json(data))]


def _err(code: str, message: str, hint: str = "") -> list[TextContent]:
    payload: dict[str, Any] = {"error": True, "code": code, "message": message}
    if hint:
        payload["hint"] = hint
    return [TextContent(type="text", text=to_compact_json(payload))]


def _load_tool(name: str) -> Callable[..., Any] | None:
    """Import a tool function lazily so a broken module cannot block startup."""
    entry = _TOOL_REGISTRY.get(name)
    if entry is None:
        return None
    module_path, func_name = entry
    module = importlib.import_module(module_path)
    return getattr(module, func_name)  # type: ignore[no-any-return]


#: Pydantic tags each union branch it tried with the branch's type name. Those
#: tags are noise to the caller, who only cares about the field path.
_UNION_BRANCH_TAGS = frozenset({"str", "int", "float", "bool", "list", "dict"})


def _clean_loc(loc: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for item in loc:
        text = str(item)
        is_model_tag = text.isidentifier() and text[:1].isupper()
        if text in _UNION_BRANCH_TAGS or is_model_tag:
            continue
        parts.append(text)
    return ".".join(parts)


def _format_validation_error(exc: ValidationError) -> str:
    """Turn a Pydantic error into a short, actionable hint for the model.

    A failed union (``str | Coordinates``) reports one error per branch. Only
    the most specific one is useful, so errors are collapsed per field.
    """
    best: dict[str, tuple[int, str]] = {}
    for err in exc.errors():
        path = _clean_loc(err["loc"])
        field = path.split(".", 1)[0] or "(arguments)"
        depth = len(err["loc"])
        if field not in best or depth > best[field][0]:
            best[field] = (depth, f"{path or '(arguments)'}: {err['msg']}")
    return "; ".join(msg for _, msg in list(best.values())[:5])


#: tool name -> (module path, function name)
_TOOL_REGISTRY: dict[str, tuple[str, str]] = {
    "calculate_natal_chart": ("astro_mcp.tools.natal", "calculate_natal_chart"),
    "calculate_transits": ("astro_mcp.tools.transits", "calculate_transits"),
    "calculate_secondary_progressions": (
        "astro_mcp.tools.progressions", "calculate_secondary_progressions"),
    "calculate_solar_return": ("astro_mcp.tools.returns", "calculate_solar_return"),
    "calculate_lunar_return": ("astro_mcp.tools.returns", "calculate_lunar_return"),
    "calculate_rectification_hints": (
        "astro_mcp.tools.rectification", "calculate_rectification_hints"),
    "calculate_synastry": ("astro_mcp.tools.synastry", "calculate_synastry"),
    "calculate_composite_chart": ("astro_mcp.tools.synastry", "calculate_composite_chart"),
    "calculate_profections": ("astro_mcp.tools.profections", "calculate_profections"),
    "get_planetary_hours": ("astro_mcp.tools.planetary_hours", "get_planetary_hours"),
    "calculate_arabic_parts": ("astro_mcp.tools.arabic_parts", "calculate_arabic_parts"),
    "get_ephemeris": ("astro_mcp.tools.ephemeris", "get_ephemeris"),
    "find_aspect_exact_dates": ("astro_mcp.tools.ephemeris", "find_aspect_exact_dates"),
    "calculate_antiscia": ("astro_mcp.tools.antiscia", "calculate_antiscia"),
}


def create_server() -> Server:
    server = Server("astro-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        # Descriptions and schemas are both derived from the Pydantic models in
        # schemas.py, so they cannot drift from what the tools accept.
        return [
            Tool(
                name=name,
                description=tool_description(model),
                inputSchema=json_schema_for(model),
            )
            for name, model in TOOL_INPUTS.items()
        ]

    # validate_input=False: the SDK would otherwise validate against the same
    # schema a second time and report failures as prose, breaking the
    # structured-JSON error contract every other failure path honours. The
    # models below are the source of that schema, so nothing is lost.
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        func = _load_tool(name)
        model = TOOL_INPUTS.get(name)
        if func is None or model is None:
            return _err(
                "UNKNOWN_TOOL",
                f"Tool '{name}' not found.",
                hint=f"Available tools: {', '.join(sorted(_TOOL_REGISTRY))}",
            )

        try:
            parsed = model.model_validate(arguments)
        except ValidationError as exc:
            logger.warning("Bad arguments for tool %s: %s", name, exc)
            return _err(
                "INPUT_ERROR",
                f"Invalid arguments for '{name}'.",
                hint=_format_validation_error(exc),
            )

        # exclude_unset keeps the tool functions authoritative for their own
        # defaults; the schema only advertises them.
        kwargs = parsed.model_dump(exclude_unset=True)

        try:
            # Every tool is CPU-bound Swiss Ephemeris work plus (for geocoding)
            # a blocking network call. Running it inline would stall the whole
            # asyncio event loop and freeze the stdio transport.
            result = await asyncio.to_thread(func, **kwargs)
            return _ok(result)

        except AstroError as exc:
            logger.warning("%s in tool %s: %s", exc.code, name, exc)
            return [TextContent(type="text", text=to_compact_json(exc.to_payload()))]
        except ValueError as exc:
            logger.warning("ValueError in tool %s: %s", name, exc)
            return _err("INPUT_ERROR", str(exc))
        except Exception:
            # Log the full traceback server-side, but never echo internal
            # details (paths, library internals) back to the model.
            logger.exception("Unexpected error in tool %s", name)
            return _err(
                "INTERNAL_ERROR",
                "An internal error occurred while computing this chart.",
                hint="Check the server logs for details.",
            )

    return server


async def _run() -> None:
    from astro_mcp.core.ephemeris_provider import init_ephemeris

    # Fail loudly at startup rather than silently degrading to the much less
    # accurate built-in Moshier ephemeris on every subsequent request.
    try:
        init_ephemeris()
    except AstroError as exc:
        logger.error("Ephemeris initialisation failed: %s", exc)
        raise

    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
