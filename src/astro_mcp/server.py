"""MCP server — registers all 14 astrological tools."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from astro_mcp.config import settings
from astro_mcp.core.formatters import to_compact_json

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


def create_server() -> Server:
    server = Server("astro-mcp")

    # ------------------------------------------------------------------
    # Tool definitions (just metadata, actual logic is in tools/)
    # ------------------------------------------------------------------

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="calculate_natal_chart",
                description=(
                    "Calculate a full natal (birth) chart: planets, angles, houses, aspects. "
                    "Returns compact JSON. House systems: P=Placidus, W=WholeSign, K=Koch."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["date", "time", "location"],
                    "properties": {
                        "date": {"type": "string", "description": "Birth date YYYY-MM-DD"},
                        "time": {"type": "string", "description": "Birth time HH:MM or HH:MM:SS (local)"},
                        "location": {"description": "City name or {lat, lon, tz}"},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                        "include_asteroids": {"type": "boolean", "default": False},
                        "include_arabic_parts": {"type": "boolean", "default": False},
                    },
                },
            ),
            Tool(
                name="calculate_transits",
                description=(
                    "Calculate transit planets and their aspects to a natal chart for a given date. "
                    "Provide birth_date, birth_time, birth_location and transit_date."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["transit_date", "birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "transit_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "transit_time": {"type": "string", "description": "Local time at transit location HH:MM (default: 12:00 local)"},
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {"description": "City name or {lat,lon,tz}"},
                        "transit_location": {"description": "City name or {lat,lon,tz} for transit location"},
                        "period_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                        "orbs": {"type": "object"},
                        "fast_planets_only": {"type": "boolean", "default": False},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                        "max_orb": {"type": "number", "description": "Filter aspects to those within this orb (degrees). Default: 3."},
                    },
                },
            ),
            Tool(
                name="calculate_secondary_progressions",
                description=(
                    "Secondary progressions (day-for-a-year). Returns progressed planets, "
                    "angles, and aspects to natal chart. Optionally includes Solar Arc."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["progression_date", "birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {},
                        "progression_date": {"type": "string", "description": "Date YYYY-MM-DD"},
                        "include_solar_arc": {"type": "boolean", "default": False},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                        "max_orb": {"type": "number", "description": "Filter aspects to those within this orb (degrees). Default: 3."},
                    },
                },
            ),
            Tool(
                name="calculate_solar_return",
                description=(
                    "Solar return chart for a given year (exact moment Sun returns to natal position)."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["year", "birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {},
                        "year": {"type": "integer"},
                        "return_location": {"description": "City or coords for relocation solar return"},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="calculate_rectification_hints",
                description=(
                    "Score candidate birth times against life events. "
                    "Provide a time range and at least 3 dated life events."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["birth_date", "birth_location", "time_from", "time_to", "events"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_location": {},
                        "time_from": {"type": "string", "description": "HH:MM"},
                        "time_to": {"type": "string", "description": "HH:MM"},
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["date","type"],
                                "properties": {
                                    "date": {"type": "string"},
                                    "type": {"type": "string"},
                                    "description": {"type": "string"},
                                    "date_accuracy": {"type": "string", "enum": ["exact","month","year"]},
                                },
                            },
                        },
                        "time_step_min": {"type": "integer", "default": 4},
                        "techniques": {"type": "array", "items": {"type": "string"}},
                        "top_n": {"type": "integer", "default": 5},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                    },
                },
            ),
            Tool(
                name="calculate_lunar_return",
                description=(
                    "Lunar return chart — moment Moon returns to natal position. "
                    "Returns up to 12 consecutive lunar returns."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {},
                        "from_date": {"type": "string"},
                        "count": {"type": "integer", "default": 1, "maximum": 12},
                        "return_location": {},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="calculate_synastry",
                description=(
                    "Synastry: cross-aspects and house overlays between two charts. "
                    "Also returns Davison chart datetime and compatibility indicators."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["person1_date", "person1_time", "person1_location", "person2_date", "person2_time", "person2_location"],
                    "properties": {
                        "person1_date": {"type": "string"},
                        "person1_time": {"type": "string"},
                        "person1_location": {},
                        "person2_date": {"type": "string"},
                        "person2_time": {"type": "string"},
                        "person2_location": {},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "orbs": {"type": "object"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="calculate_composite_chart",
                description=(
                    "Composite chart via midpoints or Davison method. "
                    "Returns composite planets, angles, houses, and aspects."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["person1_date", "person1_time", "person1_location", "person2_date", "person2_time", "person2_location"],
                    "properties": {
                        "person1_date": {"type": "string"},
                        "person1_time": {"type": "string"},
                        "person1_location": {},
                        "person2_date": {"type": "string"},
                        "person2_time": {"type": "string"},
                        "person2_location": {},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "method": {"type": "string", "enum": ["midpoint","davison"], "default": "midpoint"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="calculate_profections",
                description=(
                    "Annual profections — Hellenistic technique. Each life-year the ASC advances one house. "
                    "Returns profected house, sign, year lord, and activated planets."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["target_date", "birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {},
                        "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="get_planetary_hours",
                description=(
                    "Calculate 24 planetary hours (12 day + 12 night) for a location and date. "
                    "Returns start/end times in local timezone."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["date", "location"],
                    "properties": {
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "location": {"description": "City name or {lat, lon}"},
                        "tz_output": {"type": "string", "description": "IANA timezone for output"},
                    },
                },
            ),
            Tool(
                name="calculate_arabic_parts",
                description=(
                    "Calculate Arabic (Hermetic) Parts/Lots. Supports: FortPt, SpiritPt, "
                    "MarriagePt, DeathPt, ChildrenPt, CareerPt, TravelPt (or 'all')."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {},
                        "parts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["all"],
                        },
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="get_ephemeris",
                description=(
                    "Ephemeris table: planet positions over a date range with a given step. "
                    "Steps: 1h, 6h, 12h, 1d, 7d, 30d."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["planet", "date_from", "date_to"],
                    "properties": {
                        "planet": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "step": {"type": "string", "enum": ["1h","6h","12h","1d","7d","30d"], "default": "1d"},
                        "output_tz": {"type": "string", "default": "UTC"},
                        "include_speed": {"type": "boolean", "default": False},
                        "include_retrograde": {"type": "boolean", "default": True},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
            Tool(
                name="find_aspect_exact_dates",
                description=(
                    "Find exact dates when a specific aspect forms between two bodies "
                    "(or a body and a natal point) within a date range."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["planet1", "planet2", "aspect", "date_from", "date_to"],
                    "properties": {
                        "planet1": {"type": "string"},
                        "planet2": {"type": "string"},
                        "aspect": {"type": "string",
                                   "enum": ["Cnj","Opp","Tri","Squ","Sex","SSq","Ses"]},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "birth_date": {"type": "string", "description": "Birth date if planet2 is a natal point"},
                        "birth_time": {"type": "string"},
                        "birth_location": {"description": "Birth location if planet2 is a natal point"},
                        "orb": {"type": "number", "default": 1.0},
                    },
                },
            ),
            Tool(
                name="calculate_antiscia",
                description=(
                    "Calculate antiscia (Cancer/Capricorn axis reflections) and contra-antiscia "
                    "(Aries/Libra axis) for natal planets. Optionally finds transit aspects to antiscia."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["birth_date", "birth_time", "birth_location"],
                    "properties": {
                        "birth_date": {"type": "string"},
                        "birth_time": {"type": "string"},
                        "birth_location": {},
                        "include_transits_date": {"type": "string",
                                                  "description": "Optional date to check transit aspects to antiscia"},
                        "house_system": {"type": "string", "enum": ["P","W","K"], "default": "P"},
                        "degree_format": {"type": "string", "enum": ["dms","dec"], "default": "dms"},
                    },
                },
            ),
        ]

    # ------------------------------------------------------------------
    # Tool call dispatcher
    # ------------------------------------------------------------------

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name == "calculate_natal_chart":
                from astro_mcp.tools.natal import calculate_natal_chart
                result = calculate_natal_chart(**arguments)

            elif name == "calculate_transits":
                from astro_mcp.tools.transits import calculate_transits
                result = calculate_transits(**arguments)

            elif name == "calculate_secondary_progressions":
                from astro_mcp.tools.progressions import calculate_secondary_progressions
                result = calculate_secondary_progressions(**arguments)

            elif name == "calculate_solar_return":
                from astro_mcp.tools.returns import calculate_solar_return
                result = calculate_solar_return(**arguments)

            elif name == "calculate_lunar_return":
                from astro_mcp.tools.returns import calculate_lunar_return
                result = calculate_lunar_return(**arguments)

            elif name == "calculate_rectification_hints":
                from astro_mcp.tools.rectification import calculate_rectification_hints
                result = calculate_rectification_hints(**arguments)

            elif name == "calculate_synastry":
                from astro_mcp.tools.synastry import calculate_synastry
                result = calculate_synastry(**arguments)

            elif name == "calculate_composite_chart":
                from astro_mcp.tools.synastry import calculate_composite_chart
                result = calculate_composite_chart(**arguments)

            elif name == "calculate_profections":
                from astro_mcp.tools.profections import calculate_profections
                result = calculate_profections(**arguments)

            elif name == "get_planetary_hours":
                from astro_mcp.tools.planetary_hours import get_planetary_hours
                result = get_planetary_hours(**arguments)

            elif name == "calculate_arabic_parts":
                from astro_mcp.tools.arabic_parts import calculate_arabic_parts
                result = calculate_arabic_parts(**arguments)

            elif name == "get_ephemeris":
                from astro_mcp.tools.ephemeris import get_ephemeris
                result = get_ephemeris(**arguments)

            elif name == "find_aspect_exact_dates":
                from astro_mcp.tools.ephemeris import find_aspect_exact_dates
                result = find_aspect_exact_dates(**arguments)

            elif name == "calculate_antiscia":
                from astro_mcp.tools.antiscia import calculate_antiscia
                result = calculate_antiscia(**arguments)

            else:
                return _err("UNKNOWN_TOOL", f"Tool '{name}' not found.")

            return _ok(result)

        except ValueError as exc:
            logger.warning("ValueError in tool %s: %s", name, exc)
            code = str(exc).split(":")[0] if ":" in str(exc) else "INPUT_ERROR"
            return _err(code, str(exc))
        except Exception as exc:
            logger.exception("Unexpected error in tool %s", name)
            return _err("INTERNAL_ERROR", f"Unexpected error: {exc}")

    return server


async def _run() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
