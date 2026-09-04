"""Tools 4 & 6: calculate_solar_return and calculate_lunar_return."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import swisseph as swe

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    build_house_cusps,
    calc_all_planets,
    calc_houses,
    calc_planet,
    find_aspects,
    jd_to_iso,
    resolve_house_system,
    to_jd,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_house, serialize_point
from astro_mcp.core.geocoding import resolve_location
from astro_mcp.core.models import ChartPoint, GeoLocation, rank_aspects
from astro_mcp.tools.natal import compute_natal


def _find_return_jd(
    planet_id: int,
    natal_lon: float,
    jd_start: float,
    search_days: int = 400,
) -> float:
    """Find next JD when planet returns to its natal longitude (bisection).

    Uses crossing-detection: tracks the signed angular distance to natal_lon
    and bisects when the sign changes (planet has crossed the target degree).
    """
    step = 0.5 if planet_id == swe.MOON else 5.0
    jd = jd_start

    def signed_diff(jd_val: float) -> float:
        lon, _ = calc_planet(jd_val, planet_id)
        d = (lon - natal_lon) % 360
        if d > 180:
            d -= 360
        return d

    prev_d = signed_diff(jd)
    jd += step

    while jd <= jd_start + search_days:
        curr_d = signed_diff(jd)
        # Detect zero crossing (planet passed through natal_lon between prev and curr)
        if prev_d * curr_d <= 0 and abs(prev_d - curr_d) < 180:
            # Bisect within [jd - step, jd]
            jd_lo = jd - step
            jd_hi = jd
            for _ in range(60):
                jd_mid = (jd_lo + jd_hi) / 2
                d_mid = signed_diff(jd_mid)
                if abs(d_mid) < 1e-9:
                    return jd_mid
                if d_mid * signed_diff(jd_lo) <= 0:
                    jd_hi = jd_mid
                else:
                    jd_lo = jd_mid
            return (jd_lo + jd_hi) / 2
        prev_d = curr_d
        jd += step

    raise AstroError(
        "RETURN_NOT_FOUND",
        f"No return found within {search_days} days of the search start.",
    )


def _return_geo(
    return_location: str | dict[str, Any] | None,
    fallback: GeoLocation,
) -> GeoLocation:
    """Relocation target for the return chart, defaulting to the birth place."""
    if return_location:
        return resolve_location(return_location)
    return fallback


def calculate_solar_return(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    year: int = 0,
    return_location: str | dict[str, Any] | None = None,
    location: str | dict[str, Any] | None = None,
    house_system: str = "P",
    degree_format: str = "dec",
    min_significance: float | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    """Tool 4: Solar return chart for a given year."""
    # Accept 'location' as alias for 'return_location'
    if location and not return_location:
        return_location = location
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    chart = compute_natal(birth_date, birth_time, birth_location, house_system)

    if not year:
        year = datetime.now(UTC).year

    # The Sun returns to its natal degree once per year, so searching a full
    # year forward from 1 January always brackets exactly one return.
    jd_start = to_jd(f"{year}-01-01T00:00:00Z")
    sr_jd = _find_return_jd(
        swe.SUN, chart.planets["Su"].lon_decimal, jd_start, search_days=400
    )

    geo = _return_geo(return_location, chart.geo)
    hs, hs_warning = resolve_house_system(house_system, geo.lat)

    cusps, ascmc = calc_houses(sr_jd, geo.lat, geo.lon, hs)
    sr_planets = calc_all_planets(sr_jd, cusps, include_asteroids=False)
    sr_angles = build_angles(ascmc, cusps)
    sr_houses = build_house_cusps(cusps)

    sr_all: dict[str, ChartPoint] = {**sr_planets, **sr_angles}
    sr2n = find_aspects(sr_all, chart.all_points, angle_orb_keys={"Asc", "MC"})

    result: dict[str, Any] = {
        "return_dt": jd_to_iso(sr_jd),
        "return_loc": {"lat": geo.lat, "lon": geo.lon, "name": geo.name},
        "hs": hs,
        "sr_planets": {k: serialize_point(v, degree_format) for k, v in sr_planets.items()},
        "sr_angles": {k: serialize_point(v, degree_format, include_house=False)
                      for k, v in sr_angles.items()},
        "sr_houses": [serialize_house(h, degree_format) for h in sr_houses],
        "sr_to_natal_aspects": [
            {"sp": a.point1, "np": a.point2, "asp": a.aspect_type, "orb": a.orb,
             "sig": a.significance}
            for a in rank_aspects(sr2n, min_significance, top_n)
        ],
    }
    if hs_warning:
        result["house_system_warning"] = hs_warning
    return result


def calculate_lunar_return(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    from_date: str | None = None,
    count: int = 1,
    return_location: str | dict[str, Any] | None = None,
    house_system: str = "P",
    degree_format: str = "dec",
) -> dict[str, Any]:
    """Tool 6: Lunar return chart(s)."""
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    chart = compute_natal(birth_date, birth_time, birth_location, house_system)

    natal_moon_lon = chart.planets["Mo"].lon_decimal
    count = max(1, min(count, 12))

    start_str = from_date or datetime.now(UTC).strftime("%Y-%m-%d")
    jd_search = to_jd(f"{start_str}T00:00:00Z")

    geo = _return_geo(return_location, chart.geo)
    hs, hs_warning = resolve_house_system(house_system, geo.lat)

    returns = []
    for _ in range(count):
        lr_jd = _find_return_jd(swe.MOON, natal_moon_lon, jd_search, search_days=35)
        cusps, ascmc = calc_houses(lr_jd, geo.lat, geo.lon, hs)
        lr_planets = calc_all_planets(lr_jd, cusps, include_asteroids=False)
        lr_angles = build_angles(ascmc, cusps)
        lr_houses = build_house_cusps(cusps)

        returns.append({
            "return_dt": jd_to_iso(lr_jd),
            "return_loc": {"lat": geo.lat, "lon": geo.lon, "name": geo.name},
            "lr_planets": {k: serialize_point(v, degree_format) for k, v in lr_planets.items()},
            "lr_angles": {k: serialize_point(v, degree_format, include_house=False)
                          for k, v in lr_angles.items()},
            "lr_houses": [serialize_house(h, degree_format) for h in lr_houses],
        })
        jd_search = lr_jd + 20.0  # advance well past this return, before the next

    result: dict[str, Any] = {"hs": hs, "returns": returns}
    if hs_warning:
        result["house_system_warning"] = hs_warning
    return result
