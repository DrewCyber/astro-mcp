"""Tools 4 & 6: calculate_solar_return and calculate_lunar_return."""

from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any

import swisseph as swe

from astro_mcp.core.ephemeris_provider import (
    PLANET_IDS,
    build_angles,
    build_house_cusps,
    calc_all_planets,
    calc_houses,
    calc_planet,
    find_aspects,
    jd_to_iso,
    to_jd,
)
from astro_mcp.core.formatters import serialize_house, serialize_point
from astro_mcp.core.geocoding import resolve_location
from astro_mcp.tools.transits import _natal_to_points


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
                if abs(d_mid) < 1e-6:
                    return jd_mid
                if d_mid * signed_diff(jd_lo) <= 0:
                    jd_hi = jd_mid
                else:
                    jd_lo = jd_mid
            return (jd_lo + jd_hi) / 2
        prev_d = curr_d
        jd += step

    raise ValueError("Return not found in search window.")


def calculate_solar_return(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    year: int = 0,
    return_location: str | dict | None = None,
    house_system: str = "P",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 4: Solar return chart for a given year."""
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    from astro_mcp.tools.natal import calculate_natal_chart
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    natal_sun_lon = natal["planets"]["Su"]["deg"]
    natal_date_str = natal["meta"]["dt"][:10]

    if not year:
        from datetime import datetime
        year = datetime.utcnow().year

    # Start search from approximate birthday in target year
    search_start_str = f"{year}-01-01T00:00:00Z"
    jd_start = to_jd(search_start_str)
    sr_jd = _find_return_jd(swe.SUN, natal_sun_lon, jd_start, search_days=400)

    # Return location
    rloc = resolve_location(return_location) if return_location else None
    geo = rloc if rloc else type("G", (), {
        "lat": natal["meta"]["loc"]["lat"],
        "lon": natal["meta"]["loc"]["lon"],
        "name": natal["meta"]["loc"].get("name", ""),
    })()

    cusps, ascmc = calc_houses(sr_jd, geo.lat, geo.lon, house_system)
    sr_planets = calc_all_planets(sr_jd, cusps, include_asteroids=False)
    sr_angles = build_angles(ascmc, cusps)
    sr_houses = build_house_cusps(cusps)

    natal_points = _natal_to_points(natal)
    from astro_mcp.core.models import ChartPoint
    sr_all: dict[str, ChartPoint] = {**sr_planets, **sr_angles}
    sr2n = find_aspects(sr_all, natal_points, angle_orb_keys={"Asc", "MC"})

    return {
        "return_dt": jd_to_iso(sr_jd),
        "return_loc": {"lat": geo.lat, "lon": geo.lon, "name": getattr(geo, "name", "")},
        "sr_planets": {k: serialize_point(v, degree_format) for k, v in sr_planets.items()},
        "sr_angles": {k: serialize_point(v, degree_format, include_house=False) for k, v in sr_angles.items()},
        "sr_houses": [serialize_house(h, degree_format) for h in sr_houses],
        "sr_to_natal_aspects": [
            {"sp": a.point1, "np": a.point2, "asp": a.aspect_type, "orb": a.orb}
            for a in sr2n
        ],
    }


def calculate_lunar_return(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    from_date: str | None = None,
    count: int = 1,
    return_location: str | dict | None = None,
    house_system: str = "P",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 6: Lunar return chart(s)."""
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    from astro_mcp.tools.natal import calculate_natal_chart
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    natal_moon_lon = natal["planets"]["Mo"]["deg"]
    count = min(count, 12)

    from datetime import datetime
    start_str = from_date or datetime.utcnow().strftime("%Y-%m-%d")
    jd_search = to_jd(f"{start_str}T00:00:00Z")

    rloc = resolve_location(return_location) if return_location else None
    geo_lat = rloc.lat if rloc else natal["meta"]["loc"]["lat"]
    geo_lon = rloc.lon if rloc else natal["meta"]["loc"]["lon"]

    returns = []
    for _ in range(count):
        lr_jd = _find_return_jd(swe.MOON, natal_moon_lon, jd_search, search_days=35)
        cusps, ascmc = calc_houses(lr_jd, geo_lat, geo_lon, house_system)
        lr_planets = calc_all_planets(lr_jd, cusps, include_asteroids=False)
        lr_angles = build_angles(ascmc, cusps)
        lr_houses = build_house_cusps(cusps)

        returns.append({
            "return_dt": jd_to_iso(lr_jd),
            "return_loc": {"lat": geo_lat, "lon": geo_lon},
            "lr_planets": {k: serialize_point(v, degree_format) for k, v in lr_planets.items()},
            "lr_angles": {k: serialize_point(v, degree_format, include_house=False) for k, v in lr_angles.items()},
            "lr_houses": [serialize_house(h, degree_format) for h in lr_houses],
        })
        jd_search = lr_jd + 27.0  # advance past this return

    return {"returns": returns}
