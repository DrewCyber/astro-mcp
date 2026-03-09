"""Tool 3: calculate_secondary_progressions."""

from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    build_chart_point,
    calc_all_planets,
    calc_houses,
    find_aspects,
    to_jd,
)
from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import ChartPoint


def calculate_secondary_progressions(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    progression_date: str = "",
    include_solar_arc: bool = False,
    house_system: str = "P",
    degree_format: str = "dms",
    max_orb: float | None = 3.0,
) -> dict[str, Any]:
    """
    Secondary progressions: each day after birth = one year of life.
    Returns progressed planets, angles, and aspects to natal positions.
    """
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    from astro_mcp.tools.natal import calculate_natal_chart
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    # Parse natal birth datetime
    natal_dt_str = natal["meta"]["dt"]  # UTC ISO
    natal_date_str = natal_dt_str[:10]
    natal_jd = to_jd(natal_dt_str)
    geo_data = natal["meta"]["loc"]

    # Calculate age in years at progression_date
    b_date = Date.fromisoformat(natal_date_str)
    p_date = Date.fromisoformat(progression_date)
    age_days = (p_date - b_date).days
    age_years = age_days / 365.25

    # Progressed day = natal_date + age_years days (day-for-a-year)
    prog_jd = natal_jd + age_years
    prog_date_obj = b_date + timedelta(days=age_years)
    prog_day_str = prog_date_obj.isoformat()

    geo_lat = geo_data["lat"]
    geo_lon = geo_data["lon"]
    cusps, ascmc = calc_houses(prog_jd, geo_lat, geo_lon, house_system)
    prog_planets = calc_all_planets(prog_jd, cusps, include_asteroids=False)
    prog_angles = build_angles(ascmc, cusps)

    # Natal points for aspect comparison
    from astro_mcp.tools.transits import _natal_to_points
    natal_points = _natal_to_points(natal)

    # Prog → Natal aspects
    prog_all: dict[str, ChartPoint] = {**prog_planets, **prog_angles}
    p2n = find_aspects(prog_all, natal_points, angle_orb_keys={"Asc", "MC", "Dsc", "IC"})

    # Prog → Prog aspects
    p2p_raw = find_aspects(prog_planets, prog_planets, angle_orb_keys=set())
    seen: set[frozenset[str]] = set()
    p2p = []
    for a in p2p_raw:
        k = frozenset([a.point1, a.point2])
        if k not in seen:
            seen.add(k)
            p2p.append(a)

    prog_planets_out = {k: serialize_point(v, degree_format) for k, v in prog_planets.items()}
    prog_planets_out["Asc"] = serialize_point(prog_angles["Asc"], degree_format, include_house=False)
    prog_planets_out["MC"] = serialize_point(prog_angles["MC"], degree_format, include_house=False)

    result: dict[str, Any] = {
        "prog_date": progression_date,
        "prog_age": round(age_years, 2),
        "prog_day": prog_day_str,
        "prog_planets": prog_planets_out,
        "prog_to_natal_aspects": sorted(
            (
                {"pp": a.point1, "np": a.point2, "asp": a.aspect_type, "orb": a.orb, "apply": a.applying}
                for a in p2n
                if max_orb is None or a.orb <= max_orb
            ),
            key=lambda a: a["orb"],
        ),
        "prog_to_prog_aspects": sorted(
            (
                {"p1": a.point1, "p2": a.point2, "asp": a.aspect_type, "orb": a.orb}
                for a in p2p
                if max_orb is None or a.orb <= max_orb
            ),
            key=lambda a: a["orb"],
        ),
    }

    if include_solar_arc:
        natal_sun_lon = natal["planets"]["Su"]["deg"]
        prog_sun_lon = prog_planets["Su"].lon_decimal
        solar_arc = (prog_sun_lon - natal_sun_lon) % 360
        sa_planets = {}
        for k, pt in natal_points.items():
            sa_lon = (pt.lon_decimal + solar_arc) % 360
            from astro_mcp.core.models import SIGNS
            sign_idx = int(sa_lon // 30)
            sign = SIGNS[sign_idx]
            sign_lon = sa_lon % 30
            sa_pt = ChartPoint(sa_lon, sign, sign_lon, None, False, 0.0)
            sa_planets[k] = serialize_point(sa_pt, degree_format, include_house=False)
        result["solar_arc"] = {"arc_deg": round(solar_arc, 2), "sa_planets": sa_planets}

    return result
