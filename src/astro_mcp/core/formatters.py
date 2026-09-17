"""LLM-optimized serialization helpers."""

from __future__ import annotations

import json
from typing import Any

from astro_mcp.core.ephemeris_provider import lon_to_sign_info
from astro_mcp.core.models import (
    ASPECT_NAMES,
    PLANET_NAMES,
    RULERS,
    SIGN_NAMES,
    Aspect,
    ChartPoint,
    HouseCusp,
)

# ---------------------------------------------------------------------------
# Degree formatting
# ---------------------------------------------------------------------------

def decimal_to_dms(decimal_deg: float) -> str:
    """Convert decimal degrees (within a sign, 0-30) to 'DD°MM'SS\"'."""
    total_seconds = round(decimal_deg * 3600)
    deg, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{deg:02d}\u00b0{minutes:02d}'{seconds:02d}\""


# ---------------------------------------------------------------------------
# ChartPoint serialisation
# ---------------------------------------------------------------------------

def serialize_point(
    point: ChartPoint,
    degree_format: str = "dec",
    include_house: bool = True,
) -> dict[str, Any]:
    """
    Compact planet dict for LLM output.
    Retrograde field included only when True (saves tokens).

    In ``dms`` mode ``lon`` carries the human-readable degree string; in ``dec``
    mode it is dropped entirely, because a stringified copy of ``deg`` is pure
    duplication and invites consumers to parse a number out of a string.
    """
    longitude = (round(point.lon_decimal * 3600) / 3600 if degree_format == "dms"
                 else round(point.lon_decimal, 2)) % 360
    sign, sign_lon = lon_to_sign_info(longitude)
    result: dict[str, Any] = {"sign": sign, "deg": round(longitude, 6)}
    if degree_format == "dms":
        result = {"lon": decimal_to_dms(sign_lon) + sign, **result}
    if include_house and point.house is not None:
        result["house"] = point.house
    if point.retrograde:
        result["R"] = True
    return result


def serialize_aspect(asp: Aspect) -> dict[str, Any]:
    return {
        "p1": asp.point1,
        "p2": asp.point2,
        "asp": asp.aspect_type,
        "orb": round(asp.orb, 2),
        "apply": asp.applying,
        "sig": asp.significance,
    }


def build_legend() -> dict[str, Any]:
    """One-shot decoding dictionary for the wire format's abbreviations.

    Emitted only when the caller passes ``include_legend=true``; the default
    stays off so the token budget is not spent on every call.
    """
    return {
        "bodies": PLANET_NAMES,
        "aspects": ASPECT_NAMES,
        "signs": SIGN_NAMES,
        "other": {
            "R": "retrograde (present only when true)",
            "apply": "aspect is applying (tightening), not separating",
            "sig": "significance 0-1: body weight x aspect weight x orb tightness",
            "deg": "absolute ecliptic longitude 0-360; 'lon' (dms mode) is degrees within the sign",
        },
    }


def serialize_house(hc: HouseCusp, degree_format: str = "dec") -> dict[str, Any]:
    cusp = (round(hc.lon_decimal * 3600) / 3600 if degree_format == "dms"
            else round(hc.lon_decimal, 2)) % 360
    sign, sign_lon = lon_to_sign_info(cusp)
    if degree_format == "dms":
        cusp_str = decimal_to_dms(sign_lon) + sign
    else:
        cusp_str = str(cusp)
    d: dict[str, Any] = {
        "n": hc.number,
        "cusp": cusp_str,
        "sign": sign,
        "ruler": RULERS[sign][0],
    }
    if RULERS[sign][1]:
        d["mod_ruler"] = RULERS[sign][1]
    return d


# ---------------------------------------------------------------------------
# Full chart serialisation
# ---------------------------------------------------------------------------

def serialize_natal(
    meta: dict[str, Any],
    planets: dict[str, ChartPoint],
    angles: dict[str, ChartPoint],
    houses: list[HouseCusp],
    aspects: list[Aspect],
    degree_format: str = "dec",
) -> dict[str, Any]:
    return {
        "meta": meta,
        "planets": {k: serialize_point(v, degree_format) for k, v in planets.items()},
        "angles": {k: serialize_point(v, degree_format, include_house=False) for k, v in angles.items()},
        "houses": [serialize_house(h, degree_format) for h in houses],
        "aspects": [serialize_aspect(a) for a in aspects],
    }


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def to_compact_json(data: Any) -> str:
    """Serialize without whitespace and with proper unicode (non-ASCII preserved)."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def strip_nulls(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None values (saves tokens)."""
    return {k: v for k, v in d.items() if v is not None}
