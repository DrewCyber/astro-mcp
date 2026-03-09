"""LLM-optimized serialization helpers."""

from __future__ import annotations

import json
import math
from typing import Any

from astro_mcp.core.models import Aspect, ChartPoint, HouseCusp, SIGNS


# ---------------------------------------------------------------------------
# Degree formatting
# ---------------------------------------------------------------------------

def decimal_to_dms(decimal_deg: float) -> str:
    """Convert decimal degrees (within a sign, 0-30) to 'DD°MM'SS\"'."""
    deg = int(decimal_deg)
    rem = (decimal_deg - deg) * 60
    minutes = int(rem)
    seconds = int((rem - minutes) * 60)
    return f"{deg:02d}\u00b0{minutes:02d}'{seconds:02d}\""


def lon_to_dms_with_sign(lon_decimal: float, sign: str, sign_lon: float) -> str:
    """Format as '24°45'12\"Pis'."""
    return decimal_to_dms(sign_lon) + sign


def dms_to_decimal(dms_str: str) -> float:
    """Parse '24°45'12\"' to decimal degrees."""
    import re
    m = re.match(r"(\d+)\u00b0(\d+)'(\d+)\"", dms_str)
    if not m:
        raise ValueError(f"Cannot parse DMS: {dms_str}")
    d, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return d + mi / 60 + s / 3600


# ---------------------------------------------------------------------------
# ChartPoint serialisation
# ---------------------------------------------------------------------------

def serialize_point(
    point: ChartPoint,
    degree_format: str = "dms",
    include_house: bool = True,
) -> dict[str, Any]:
    """
    Compact planet dict for LLM output.
    Retrograde field included only when True (saves tokens).
    """
    if degree_format == "dms":
        lon_str = decimal_to_dms(point.sign_lon) + point.sign
    else:
        lon_str = str(round(point.lon_decimal, 2))

    result: dict[str, Any] = {
        "lon": lon_str,
        "sign": point.sign,
        "deg": round(point.lon_decimal, 2),
    }
    if include_house and point.house is not None:
        result["house"] = point.house
    if point.retrograde:
        result["R"] = True
    return result


def serialize_aspect(asp: Aspect, include_exact: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {
        "p1": asp.point1,
        "p2": asp.point2,
        "asp": asp.aspect_type,
        "orb": asp.orb,
        "apply": asp.applying,
    }
    if include_exact and asp.exact_date:
        d["exact"] = asp.exact_date
    return {k: v for k, v in d.items() if v is not None}


def serialize_house(hc: HouseCusp, degree_format: str = "dms") -> dict[str, Any]:
    sign, sign_lon = _lon_to_sign(hc.lon_decimal)
    if degree_format == "dms":
        cusp_str = decimal_to_dms(sign_lon) + sign
    else:
        cusp_str = str(round(hc.lon_decimal, 2))
    d: dict[str, Any] = {
        "n": hc.number,
        "cusp": cusp_str,
        "sign": hc.sign,
        "ruler": hc.ruler,
    }
    if hc.modern_ruler:
        d["mod_ruler"] = hc.modern_ruler
    return d


def _lon_to_sign(lon: float) -> tuple[str, float]:
    lon = lon % 360
    idx = int(lon // 30)
    return SIGNS[idx], lon % 30


# ---------------------------------------------------------------------------
# Full chart serialisation
# ---------------------------------------------------------------------------

def serialize_natal(
    meta: dict[str, Any],
    planets: dict[str, ChartPoint],
    angles: dict[str, ChartPoint],
    houses: list[HouseCusp],
    aspects: list[Aspect],
    degree_format: str = "dms",
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
