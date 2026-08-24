"""Tool 1: calculate_natal_chart."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    build_house_cusps,
    calc_all_planets,
    calc_houses,
    find_aspects,
    is_day_chart,
    resolve_house_system,
    to_jd,
)
from astro_mcp.core.formatters import serialize_natal, strip_nulls
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import ANGLE_KEYS, Aspect, NatalChart
from astro_mcp.core.moon import moon_phase


def dedupe_aspects(raw: list[Aspect]) -> list[Aspect]:
    """Collapse the A-B / B-A duplicates produced by scanning a set against itself."""
    seen: set[frozenset[str]] = set()
    out: list[Aspect] = []
    for asp in raw:
        key = frozenset([asp.point1, asp.point2])
        if key not in seen:
            seen.add(key)
            out.append(asp)
    return out


def compute_natal(
    birth_date: str,
    birth_time: str,
    birth_location: str | dict[str, Any],
    house_system: str = "P",
    include_asteroids: bool = False,
) -> NatalChart:
    """Compute a natal chart at full precision.

    This is the internal entry point every other tool should use.  The public
    MCP tool below is a thin serialising wrapper around it.
    """
    geo = resolve_location(birth_location)
    house_system, hs_warning = resolve_house_system(house_system, geo.lat)

    # Resolve local time -> UTC; detect DST edge cases
    utc_str, dst_warning = local_to_utc(birth_date, birth_time, geo.tz)
    jd = to_jd(utc_str)

    cusps, ascmc = calc_houses(jd, geo.lat, geo.lon, house_system)
    angles = build_angles(ascmc, cusps)
    house_cusps = build_house_cusps(cusps)
    planets = calc_all_planets(jd, cusps, include_asteroids=include_asteroids)
    is_day = is_day_chart(jd, geo.lat, geo.lon)

    all_points = {**planets, **angles}
    aspects = dedupe_aspects(
        find_aspects(all_points, all_points, angle_orb_keys=set(ANGLE_KEYS))
    )

    meta: dict[str, Any] = {
        "dt": utc_str,
        "birth_date": birth_date,
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
    if hs_warning:
        meta["house_system_warning"] = hs_warning

    return NatalChart(
        meta=meta,
        planets=planets,
        angles=angles,
        cusps=cusps,
        houses=house_cusps,
        aspects=aspects,
        geo=geo,
        jd=jd,
        house_system=house_system,
        is_day=is_day,
        dst_warning=dst_warning,
        house_system_warning=hs_warning,
    )


def calculate_natal_chart(
    birth_date: str,
    birth_time: str,
    birth_location: str | dict[str, Any],
    house_system: str = "P",
    degree_format: str = "dms",
    include_asteroids: bool = False,
    include_arabic_parts: bool = False,
) -> dict[str, Any]:
    """
    Compute a full natal chart.
    Returns compact JSON-ready dict.
    """
    chart = compute_natal(
        birth_date, birth_time, birth_location, house_system, include_asteroids
    )

    result = serialize_natal(
        chart.meta, chart.planets, chart.angles, chart.houses, chart.aspects, degree_format
    )
    # Reported rather than left to the caller: deriving the phase from the two
    # longitudes is a classic source of waxing/waning errors.
    result["moon"] = moon_phase(chart.jd)

    if include_arabic_parts:
        from astro_mcp.tools.arabic_parts import compute_parts
        result["arabic_parts"] = compute_parts(
            chart.planets, chart.angles, chart.houses, degree_format,
            is_day=chart.is_day,
        )

    return result
