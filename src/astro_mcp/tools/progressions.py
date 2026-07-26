"""Tool 3: calculate_secondary_progressions."""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    calc_all_planets,
    calc_houses,
    find_aspects,
    lon_to_sign_info,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.models import ANGLE_KEYS, ChartPoint
from astro_mcp.tools.natal import compute_natal, dedupe_aspects


def calculate_secondary_progressions(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
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
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    if not progression_date:
        raise AstroError("INPUT_ERROR", "progression_date is required.")

    chart = compute_natal(birth_date, birth_time, birth_location, house_system)

    # Age is measured from the *local* birth date the caller supplied; the UTC
    # timestamp can land on the neighbouring day for births near midnight.
    try:
        b_date = Date.fromisoformat(birth_date)
        p_date = Date.fromisoformat(progression_date)
    except ValueError as exc:
        raise AstroError(
            "INVALID_DATE", "birth_date and progression_date must be YYYY-MM-DD."
        ) from exc

    age_days = (p_date - b_date).days
    age_years = age_days / 365.25

    # Day-for-a-year: advance the ephemeris one day per year of life.
    prog_jd = chart.jd + age_years
    prog_day_str = (b_date + timedelta(days=age_years)).isoformat()

    cusps, ascmc = calc_houses(
        prog_jd, chart.geo.lat, chart.geo.lon, chart.house_system
    )
    prog_planets = calc_all_planets(prog_jd, cusps, include_asteroids=False)
    prog_angles = build_angles(ascmc, cusps)

    natal_points = chart.all_points

    # Prog -> Natal aspects
    prog_all: dict[str, ChartPoint] = {**prog_planets, **prog_angles}
    p2n = find_aspects(prog_all, natal_points, angle_orb_keys=set(ANGLE_KEYS))

    # Prog -> Prog aspects
    p2p = dedupe_aspects(find_aspects(prog_planets, prog_planets, angle_orb_keys=set()))

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
        solar_arc = (prog_planets["Su"].lon_decimal - chart.planets["Su"].lon_decimal) % 360
        sa_planets = {}
        for k, pt in natal_points.items():
            sa_lon = (pt.lon_decimal + solar_arc) % 360
            sign, sign_lon = lon_to_sign_info(sa_lon)
            sa_pt = ChartPoint(sa_lon, sign, sign_lon, None, False, 0.0)
            sa_planets[k] = serialize_point(sa_pt, degree_format, include_house=False)
        result["solar_arc"] = {"arc_deg": round(solar_arc, 2), "sa_planets": sa_planets}

    return result
