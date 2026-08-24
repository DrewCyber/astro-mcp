"""Pydantic input models for every MCP tool.

These models are the single source of truth for two things that previously
drifted apart: the JSON Schema advertised to the client, and the arguments the
tool functions actually accept. Hand-maintaining the schemas in ``server.py``
had already let three parameters go undocumented.

Validated arguments are forwarded with ``exclude_unset=True`` so the tool
functions keep ownership of their own defaults — the schema only advertises
them.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HouseSystem = Literal["P", "W", "K"]
DegreeFormat = Literal["dms", "dec"]
AspectCode = Literal["Cnj", "Opp", "Tri", "Squ", "Sex", "SSq", "Ses"]
StepCode = Literal["1h", "2h", "3h", "6h", "12h", "1d", "7d", "30d"]
Technique = Literal["transits", "progressions", "profections"]

DATE_DESC = "Date as YYYY-MM-DD"
TIME_DESC = "Local wall-clock time as HH:MM or HH:MM:SS"


class Coordinates(BaseModel):
    """Explicit geographic coordinates."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90.0, le=90.0, description="Latitude in degrees, north positive")
    lon: float = Field(ge=-180.0, le=180.0, description="Longitude in degrees, east positive")
    tz: str | None = Field(
        default=None,
        description="IANA timezone (e.g. 'Europe/Berlin'). Derived from the coordinates "
        "when omitted.",
    )
    name: str | None = Field(default=None, description="Optional label for the output")


Location = Annotated[
    str | Coordinates,
    Field(description="City name (e.g. 'Moscow') or explicit {lat, lon} coordinates"),
]


class LifeEvent(BaseModel):
    """A dated life event used to score candidate birth times."""

    model_config = ConfigDict(extra="forbid")

    date: str = Field(description=DATE_DESC)
    type: str = Field(
        description="Event category, e.g. 'marriage', 'relocation', 'career_rise', 'loss'"
    )
    description: str | None = Field(default=None, description="Free-text detail")
    date_accuracy: Literal["exact", "month", "year"] | None = Field(
        default=None,
        description="Only events with 'exact' accuracy are scored",
    )


class _ToolInput(BaseModel):
    """Base for every tool input: unknown arguments are rejected."""

    model_config = ConfigDict(extra="forbid")


class _BirthData(_ToolInput):
    """Mixin for the tools that always need a complete birth chart."""

    birth_date: str = Field(description=DATE_DESC)
    birth_time: str = Field(description=TIME_DESC)
    birth_location: Location


# ---------------------------------------------------------------------------
# Tool inputs
# ---------------------------------------------------------------------------


class NatalChartInput(_BirthData):
    """Calculate a full natal (birth) chart: planets, angles, houses, aspects.

    House systems: P=Placidus, W=WholeSign, K=Koch. Placidus and Koch are
    undefined above ~66 degrees latitude and fall back to Whole Sign with a
    warning in the output.
    """

    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"
    include_asteroids: bool = False
    include_arabic_parts: bool = False


class TransitsInput(_BirthData):
    """Calculate transiting planets and their aspects to a natal chart.

    With period_days > 1 the response also reports the dates on which each
    aspect becomes exact within the window.
    """

    transit_date: str = Field(description=DATE_DESC)
    transit_time: str | None = Field(
        default=None,
        description="Local time at the transit location (default: 12:00 local)",
    )
    transit_location: Location | None = Field(
        default=None, description="Defaults to birth_location when omitted"
    )
    period_days: int = Field(
        default=1,
        ge=1,
        le=366,
        description="Scan this many days starting at transit_date",
    )
    orbs: dict[str, float] | None = Field(
        default=None, description="Per-aspect orb overrides in degrees, e.g. {'Cnj': 8}"
    )
    fast_planets_only: bool = Field(
        default=False, description="Restrict to Moon, Mercury, Venus, Sun and Mars"
    )
    include_asteroids: bool = Field(
        default=False,
        description="Add Ceres (Ce), Pallas (Pa), Juno (Jun) and Vesta (Ves)",
    )
    include_moon_events: bool | None = Field(
        default=None,
        description=(
            "Include lunar contacts in aspect_events. Defaults to true for "
            "windows of 14 days or less and false beyond that, where the Moon "
            "aspects every natal point and buries the slower transits"
        ),
    )
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"
    max_orb: float | None = Field(
        default=3.0, ge=0.0, le=15.0, description="Only report aspects within this orb"
    )


class ProgressionsInput(_BirthData):
    """Secondary progressions (day-for-a-year).

    Returns progressed planets and angles plus their aspects to the natal
    chart. Optionally includes Solar Arc directions.
    """

    progression_date: str = Field(description=DATE_DESC)
    include_solar_arc: bool = False
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"
    max_orb: float | None = Field(
        default=3.0, ge=0.0, le=15.0, description="Only report aspects within this orb"
    )


class SolarReturnInput(_BirthData):
    """Solar return chart — the exact moment the Sun returns to its natal longitude."""

    year: int = Field(
        ge=1800, le=2400,
        description=(
            "Calendar year of the return (1800-2400: the span covered by the "
            "bundled Swiss Ephemeris data files)"
        ),
    )
    return_location: Location | None = Field(
        default=None,
        description="Location for a relocated solar return; defaults to birth_location",
    )
    location: Location | None = Field(
        default=None, description="Deprecated alias for return_location"
    )
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"


class LunarReturnInput(_BirthData):
    """Lunar return chart — the moment the Moon returns to its natal longitude."""

    from_date: str | None = Field(
        default=None, description=f"{DATE_DESC}. Defaults to today."
    )
    count: int = Field(default=1, ge=1, le=12, description="Number of consecutive returns")
    return_location: Location | None = Field(
        default=None, description="Defaults to birth_location"
    )
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"


class RectificationInput(_ToolInput):
    """Score candidate birth times against dated life events.

    Scans a time range, or supply birth_time to verify one specific time.
    Requires at least 3 events with exactly known dates. Scores are relative
    to each other, not absolute confidence measures.
    """

    birth_date: str = Field(description=DATE_DESC)
    birth_location: Location
    birth_time: str | None = Field(
        default=None,
        description="Supply to verify one specific time instead of scanning a range",
    )
    time_from: str = Field(default="00:00", description="Start of the scan range, HH:MM")
    time_to: str = Field(default="23:56", description="End of the scan range, HH:MM")
    events: list[LifeEvent] = Field(
        description="At least 3 events with date_accuracy 'exact' are needed to rank times"
    )
    time_step_min: int = Field(
        default=4, ge=1, le=720, description="Candidate time granularity in minutes"
    )
    techniques: list[Technique] | None = Field(
        default=None, description="Defaults to all three techniques"
    )
    top_n: int = Field(default=5, ge=1, le=50, description="How many candidates to return")
    house_system: HouseSystem = "P"


class _TwoPeople(_ToolInput):
    person1_date: str = Field(description=DATE_DESC)
    person1_time: str = Field(description=TIME_DESC)
    person1_location: Location
    person2_date: str = Field(description=DATE_DESC)
    person2_time: str = Field(description=TIME_DESC)
    person2_location: Location


class SynastryInput(_TwoPeople):
    """Synastry between two charts.

    Returns cross-aspects, bidirectional house overlays (each person's planets
    in the other's houses), and relative harmony/tension indicators.
    """

    house_system: HouseSystem = "P"
    orbs: dict[str, float] | None = Field(
        default=None, description="Per-aspect orb overrides in degrees"
    )
    degree_format: DegreeFormat = "dms"


class CompositeInput(_TwoPeople):
    """Composite chart via the midpoint or Davison method.

    Midpoint composites use equal houses measured from the composite
    Ascendant; Davison charts use real houses for the Davison time and place.
    """

    method: Literal["midpoint", "davison"] = "midpoint"
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"


class ProfectionsInput(_BirthData):
    """Annual profections — the Hellenistic technique in which the Ascendant
    advances one whole sign per completed year of life.

    Returns the profected house and sign, the year lord, and the planets it
    activates.
    """

    target_date: str = Field(description=DATE_DESC)
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"


class PlanetaryHoursInput(_ToolInput):
    """Planetary hours for a date and place — 12 day hours and 12 night hours,
    measured between sunrise, sunset and the following sunrise.
    """

    date: str = Field(description=DATE_DESC)
    location: Location
    tz_output: str | None = Field(
        default=None, description="IANA timezone for the returned times"
    )


class ArabicPartsInput(_BirthData):
    """Arabic (Hermetic) Parts, or Lots.

    Supports FortPt, SpiritPt, MarriagePt, DeathPt, ChildrenPt, CareerPt,
    TravelPt, IllnessPt, InjuryPt, FatherPt, MotherPt and SaturnPt. Formulas
    are reversed automatically for nocturnal charts where tradition requires.
    """

    parts: list[str] | None = Field(
        default=None, description="Part codes, or ['all']. Defaults to all parts."
    )
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"
    include_transits_date: str | None = Field(
        default=None,
        description=f"{DATE_DESC}. Adds transit activations of the lots on this date.",
    )


class EphemerisInput(_ToolInput):
    """Ephemeris table: positions for one or more bodies over a date range."""

    planet: str | list[str] = Field(description="Planet code, or a list of codes")
    date_from: str = Field(description=DATE_DESC)
    date_to: str = Field(description=DATE_DESC)
    step: StepCode = "1d"
    interval_days: int | None = Field(
        default=None, ge=1, description="Custom step in days; overrides step"
    )
    interval_hours: int | None = Field(
        default=None,
        ge=1,
        description="Custom step in hours; overrides interval_days and step",
    )
    output_tz: str = Field(default="UTC", description="IANA timezone for the returned times")
    include_speed: bool = False
    include_retrograde: bool = True
    degree_format: DegreeFormat = "dms"


class AspectDatesInput(_ToolInput):
    """Find the exact dates on which an aspect perfects between two bodies, or
    between a transiting body and a natal point.

    Detects multi-pass (retrograde) sequences and reports which passes occur
    while the faster body is retrograde.
    """

    planet1: str = Field(description="Transiting body code")
    planet2: str = Field(description="Second body, or the natal point in transit-to-natal mode")
    aspect: AspectCode
    date_from: str = Field(description=DATE_DESC)
    date_to: str = Field(description=DATE_DESC)
    birth_date: str | None = Field(default=None, description="Required for transit-to-natal mode")
    birth_time: str | None = Field(default=None, description="Required for transit-to-natal mode")
    birth_location: Location | None = Field(
        default=None, description="Required for transit-to-natal mode"
    )
    orb: float = Field(default=1.0, gt=0.0, le=15.0, description="Orb used to bracket a pass")
    mode: Literal["auto", "transit-to-transit", "transit-to-natal"] = "auto"
    degree_format: DegreeFormat = "dms"


class AntisciaInput(_BirthData):
    """Antiscia (reflections across the Cancer/Capricorn axis) and
    contra-antiscia (across the Aries/Libra axis) for the natal planets.
    """

    orb: float = Field(
        default=1.5, gt=0.0, le=10.0, description="Orb for antiscion contacts"
    )
    include_contra: bool = True
    include_transits_date: str | None = Field(
        default=None,
        description=f"{DATE_DESC}. Adds transit contacts to the antiscia on this date.",
    )
    house_system: HouseSystem = "P"
    degree_format: DegreeFormat = "dms"


#: tool name -> input model. Keys must match ``server._TOOL_REGISTRY``.
TOOL_INPUTS: dict[str, type[_ToolInput]] = {
    "calculate_natal_chart": NatalChartInput,
    "calculate_transits": TransitsInput,
    "calculate_secondary_progressions": ProgressionsInput,
    "calculate_solar_return": SolarReturnInput,
    "calculate_lunar_return": LunarReturnInput,
    "calculate_rectification_hints": RectificationInput,
    "calculate_synastry": SynastryInput,
    "calculate_composite_chart": CompositeInput,
    "calculate_profections": ProfectionsInput,
    "get_planetary_hours": PlanetaryHoursInput,
    "calculate_arabic_parts": ArabicPartsInput,
    "get_ephemeris": EphemerisInput,
    "find_aspect_exact_dates": AspectDatesInput,
    "calculate_antiscia": AntisciaInput,
}


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively replace local ``$ref`` pointers with their definitions.

    Pydantic factors shared sub-models (``Coordinates``, ``LifeEvent``) into
    ``$defs``. That is valid JSON Schema, but MCP clients vary in whether they
    resolve references, so the advertised schema is fully self-contained.
    """
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = defs.get(ref.rsplit("/", 1)[1], {})
        merged = {**_inline_refs(target, defs)}
        # Keep any sibling keywords, e.g. a description on the referring field.
        merged.update({k: _inline_refs(v, defs) for k, v in node.items() if k != "$ref"})
        return merged

    return {k: _inline_refs(v, defs) for k, v in node.items()}


def tool_description(model: type[_ToolInput]) -> str:
    """Use the model docstring as the tool description shown to the model."""
    return " ".join((model.__doc__ or "").split())


def json_schema_for(model: type[_ToolInput]) -> dict[str, Any]:
    """Build a self-contained JSON Schema for a tool's arguments."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    resolved: dict[str, Any] = _inline_refs(schema, defs)
    # The docstring is surfaced as the tool description, not as part of the
    # argument schema, and the class name is not useful to the caller.
    resolved.pop("description", None)
    resolved.pop("title", None)
    return resolved
