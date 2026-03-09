"""Tool 9: calculate_profections."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from astro_mcp.core.models import RULERS, SIGNS
from astro_mcp.tools.natal import calculate_natal_chart
from astro_mcp.tools.transits import _natal_to_points
from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.ephemeris_provider import calc_planet, to_jd
from astro_mcp.core.models import PLANET_IDS
from astro_mcp.core.ephemeris_provider import build_chart_point


def calculate_profections(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    target_date: str = "",
    house_system: str = "P",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """
    Tool 9: Annual profections — each year the Ascendant advances one house (30°).
    Returns the profected house, sign, year ruler, and activated planets.
    """
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    natal_date_str = natal["meta"]["dt"][:10]
    b_date = Date.fromisoformat(natal_date_str)
    t_date = Date.fromisoformat(target_date)

    # Age in full years at target date
    age = (t_date - b_date).days // 365

    # Profected house: rotate ASC by 1 house per year
    prof_house_idx = age % 12  # 0-based
    prof_house_num = prof_house_idx + 1
    ordinals = ["1st","2nd","3rd","4th","5th","6th","7th","8th","9th","10th","11th","12th"]

    # Sign of profected house
    # Profected sign = natal ASC sign + age houses
    asc_lon = natal["angles"]["Asc"]["deg"]
    prof_lon = (asc_lon + age * 30) % 360
    prof_sign_idx = int(prof_lon // 30)
    prof_sign = SIGNS[prof_sign_idx]

    # Year ruler
    classic_ruler, _ = RULERS[prof_sign]
    year_ruler = classic_ruler

    # Natal position of the year ruler
    ruler_natal = natal["planets"].get(year_ruler, {})

    # Current transit position of year ruler
    from datetime import datetime
    jd_now = to_jd(f"{target_date}T12:00:00Z")
    pid = PLANET_IDS.get(year_ruler)
    transit_ruler_pos = None
    if pid is not None:
        lon, speed = calc_planet(jd_now, pid)
        pt = build_chart_point(lon, speed)
        transit_ruler_pos = serialize_point(pt, degree_format, include_house=False)

    # Activated houses (profected house + 5th and 9th from it, etc. — simplified: just trine/square)
    activated_houses = [
        prof_house_num,
        (prof_house_num + 3 - 1) % 12 + 1,   # +3
        (prof_house_num + 6 - 1) % 12 + 1,   # +6 (opposition)
        (prof_house_num + 9 - 1) % 12 + 1,   # +9
    ]

    # Activated planets (rulers of activated houses)
    activated_planets: list[str] = []
    for h in activated_houses:
        if h <= len(natal["houses"]):
            sign = natal["houses"][h - 1]["sign"]
            ruler, _ = RULERS[sign]
            if ruler not in activated_planets:
                activated_planets.append(ruler)

    return {
        "age": age,
        "profected_asc": f"{ordinals[prof_house_idx]} house",
        "profected_sign": prof_sign,
        "year_ruler": year_ruler,
        "year_ruler_natal_pos": ruler_natal,
        "year_ruler_transit_pos": transit_ruler_pos,
        "activated_houses": activated_houses,
        "activated_planets": activated_planets,
        "note": (f"Year lord {year_ruler} is activated. "
                 f"Themes: house {prof_house_num} topics."),
    }
