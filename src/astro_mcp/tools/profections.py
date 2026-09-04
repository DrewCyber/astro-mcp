"""Tool 9: calculate_profections."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from astro_mcp.core.ephemeris_provider import build_chart_point, calc_planet, pid_for, to_jd
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.models import RULERS, SIGNS
from astro_mcp.tools.natal import compute_natal

ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th",
            "9th", "10th", "11th", "12th"]


def _completed_years(birth: Date, target: Date) -> int:
    """Whole years elapsed, rolling over on the anniversary.

    Integer-dividing the day count by 365 (as this previously did) accumulates
    one extra day every leap year, so the profected year advanced up to several
    days *before* the actual birthday — putting the wrong sign, house and year
    lord on those dates.
    """
    return target.year - birth.year - ((target.month, target.day) < (birth.month, birth.day))


def calculate_profections(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    target_date: str = "",
    house_system: str = "P",
    degree_format: str = "dec",
) -> dict[str, Any]:
    """
    Tool 9: Annual profections — each year the Ascendant advances one house (30°).
    Returns the profected house, sign, year ruler, and activated planets.
    """
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    if not target_date:
        raise AstroError("INPUT_ERROR", "target_date is required.")

    chart = compute_natal(birth_date, birth_time, birth_location, house_system)

    # Age is measured against the caller's local birth date; the UTC timestamp
    # in meta can fall on the neighbouring day for births near midnight.
    try:
        b_date = Date.fromisoformat(birth_date)
        t_date = Date.fromisoformat(target_date)
    except ValueError as exc:
        raise AstroError(
            "INVALID_DATE", "birth_date and target_date must be YYYY-MM-DD."
        ) from exc
    if t_date < b_date:
        raise AstroError("INVALID_DATE", "target_date must be on or after birth_date.")

    age = _completed_years(b_date, t_date)

    prof_house_idx = age % 12          # 0-based
    prof_house_num = prof_house_idx + 1

    # Profected sign = natal ASC sign advanced one whole sign per year.
    asc_lon = chart.angles["Asc"].lon_decimal
    prof_sign_idx = (int(asc_lon // 30) + age) % 12
    prof_sign = SIGNS[prof_sign_idx]

    year_ruler, _ = RULERS[prof_sign]

    ruler_natal = (
        serialize_point(chart.planets[year_ruler], degree_format)
        if year_ruler in chart.planets else {}
    )

    jd_target = to_jd(f"{target_date}T12:00:00Z")
    lon, speed = calc_planet(jd_target, pid_for(year_ruler))
    transit_ruler_pos = serialize_point(
        build_chart_point(lon, speed), degree_format, include_house=False
    )

    # The profected house plus its square/opposition/square partners.
    activated_houses = [((prof_house_num - 1 + offset) % 12) + 1 for offset in (0, 3, 6, 9)]

    activated_planets: list[str] = []
    for h in activated_houses:
        sign = chart.houses[h - 1].sign
        ruler, _ = RULERS[sign]
        if ruler not in activated_planets:
            activated_planets.append(ruler)

    return {
        "age": age,
        "profected_asc": f"{ORDINALS[prof_house_idx]} house",
        "profected_sign": prof_sign,
        "year_ruler": year_ruler,
        "year_ruler_natal_pos": ruler_natal,
        "year_ruler_transit_pos": transit_ruler_pos,
        "activated_houses": activated_houses,
        "activated_planets": activated_planets,
        "note": (f"Year lord {year_ruler} rules the profected {ORDINALS[prof_house_idx]} "
                 f"house in {prof_sign}."),
    }
