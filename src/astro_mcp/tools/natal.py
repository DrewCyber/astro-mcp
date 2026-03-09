"""Tool 1: calculate_natal_chart."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    build_house_cusps,
    calc_all_planets,
    calc_houses,
    find_aspects,
    to_jd,
)
from astro_mcp.core.formatters import serialize_natal, strip_nulls, to_compact_json
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import ChartPoint


def calculate_natal_chart(
    date: str,
    time: str,
    location: str | dict,
    house_system: str = "P",
    degree_format: str = "dms",
    include_asteroids: bool = False,
    include_arabic_parts: bool = False,
) -> dict[str, Any]:
    """
    Compute a full natal chart.
    Returns compact JSON-ready dict.
    """
    # Polar latitude check — Placidus fails above 66.5°
    geo = resolve_location(location)
    if abs(geo.lat) > 66.5 and house_system == "P":
        house_system = "W"

    # Resolve local time → UTC; detect DST edge cases
    utc_str, dst_warning = local_to_utc(date, time, geo.tz)
    jd = to_jd(utc_str)

    # Houses & angles
    cusps, ascmc = calc_houses(jd, geo.lat, geo.lon, house_system)
    angles = build_angles(ascmc, cusps)
    house_cusps = build_house_cusps(cusps)

    # Planets
    planets = calc_all_planets(jd, cusps, include_asteroids)

    # Aspects (planets + angles against each other)
    angle_keys = {"Asc", "MC", "Dsc", "IC"}
    all_points: dict[str, ChartPoint] = {**planets, **angles}
    raw_aspects = find_aspects(
        all_points,
        all_points,
        angle_orb_keys=angle_keys,
    )
    # Deduplicate (A-B == B-A)
    seen: set[frozenset[str]] = set()
    aspects = []
    for asp in raw_aspects:
        key = frozenset([asp.point1, asp.point2])
        if key not in seen:
            seen.add(key)
            aspects.append(asp)

    meta: dict = {
        "dt": utc_str,
        "birth_date": date,
        "loc": strip_nulls({
            "lat": geo.lat,
            "lon": geo.lon,
            "tz": geo.tz,
            "name": geo.name or None,
        }),
        "hs": house_system,
        "jd": round(jd, 5),
    }
    if dst_warning:
        meta["dst_warning"] = dst_warning

    result = serialize_natal(meta, planets, angles, house_cusps, aspects, degree_format)

    if include_arabic_parts:
        from astro_mcp.tools.arabic_parts import _compute_parts
        result["arabic_parts"] = _compute_parts(planets, angles, house_cusps, degree_format)

    return result
