"""Tool 11: calculate_arabic_parts."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.models import ChartPoint, SIGNS
from astro_mcp.core.ephemeris_provider import build_chart_point, house_of
from astro_mcp.tools.natal import calculate_natal_chart


# ---------------------------------------------------------------------------
# Arabic Part formulas: (name, day_formula_tokens, night_formula_tokens)
# Each formula token: planet/angle code or "8th_cusp" etc.
# Format: (A, B, C) where result = A + B - C
# ---------------------------------------------------------------------------

PART_FORMULAS: dict[str, tuple[str, str, str, str, str, str]] = {
    # code: (day_A, day_B, day_C, night_A, night_B, night_C)
    "FortPt":   ("Asc", "Mo",        "Su",  "Asc", "Su",        "Mo"),
    "SpiritPt": ("Asc", "Su",        "Mo",  "Asc", "Mo",        "Su"),
    "MarriagePt":("Asc","Dsc",       "Ve",  "Asc", "Dsc",       "Ve"),
    "DeathPt":  ("Asc", "8th_cusp",  "Mo",  "Asc", "8th_cusp",  "Sa"),
    "ChildrenPt":("Asc","Ju",        "Sa",  "Asc", "Sa",        "Ju"),
    "CareerPt": ("MC",  "Mo",        "Su",  "MC",  "Su",        "Mo"),
    "TravelPt": ("Asc", "9th_cusp",  "Ju",  "Asc", "9th_cusp",  "Sa"),
}


def _get_lon(
    code: str,
    planets: dict[str, Any],
    angles: dict[str, Any],
    houses: list[Any],
) -> float:
    """Resolve a planet/angle/house-cusp code to decimal longitude."""
    def _extract_lon(obj: Any) -> float:
        """Works for both ChartPoint objects and serialised dicts."""
        if hasattr(obj, "lon_decimal"):
            return obj.lon_decimal
        return obj["deg"]

    if code in planets:
        return _extract_lon(planets[code])
    if code in angles:
        return _extract_lon(angles[code])
    # house cusp
    house_map = {
        "1st_cusp": 1, "2nd_cusp": 2, "3rd_cusp": 3, "4th_cusp": 4,
        "5th_cusp": 5, "6th_cusp": 6, "7th_cusp": 7, "8th_cusp": 8,
        "9th_cusp": 9, "10th_cusp": 10, "11th_cusp": 11, "12th_cusp": 12,
    }
    if code in house_map:
        idx = house_map[code] - 1
        if idx < len(houses):
            # houses[idx]["lon_decimal"] or parse from cusp string
            hc = houses[idx]
            if hasattr(hc, "lon_decimal"):
                return hc.lon_decimal
            # Serialised house dict — reconstruct from sign + DMS
            return hc.get("lon_decimal", idx * 30.0)
    raise KeyError(f"Unknown chart point: {code}")


def _compute_parts(
    planets: dict[str, Any],
    angles: dict[str, Any],
    houses,
    degree_format: str = "dms",
    parts: list[str] | None = None,
) -> dict[str, Any]:
    """Internal: compute Arabic parts from serialised planets/angles/houses."""
    # Determine day/night (Sun above horizon = house 7-12 below horizon; Su in houses 7-12 = night)
    _su = planets.get("Su")
    if _su is None:
        su_house = 1
    elif hasattr(_su, "house"):
        su_house = _su.house or 1
    else:
        su_house = _su.get("house", 1)
    is_day = su_house not in (7, 8, 9, 10, 11, 12)

    result: dict[str, Any] = {}
    requested = parts if parts and "all" not in parts else list(PART_FORMULAS.keys())

    for code in requested:
        if code not in PART_FORMULAS:
            continue
        da, db, dc, na, nb, nc = PART_FORMULAS[code]
        a_code, b_code, c_code = (da, db, dc) if is_day else (na, nb, nc)
        try:
            lon_a = _get_lon(a_code, planets, angles, houses)
            lon_b = _get_lon(b_code, planets, angles, houses)
            lon_c = _get_lon(c_code, planets, angles, houses)
            part_lon = (lon_a + lon_b - lon_c) % 360
        except KeyError:
            continue

        sign_idx = int(part_lon // 30)
        sign = SIGNS[sign_idx]
        sign_lon = part_lon % 30
        pt = ChartPoint(part_lon, sign, sign_lon, None, False, 0.0)
        result[code] = serialize_point(pt, degree_format, include_house=False)

    return result


def calculate_arabic_parts(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    parts: list[str] | None = None,
    house_system: str = "P",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 11: Arabic (Hermetic) Parts / Lots."""
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    su_house = natal["planets"].get("Su", {}).get("house", 1)
    is_day = su_house not in (7, 8, 9, 10, 11, 12)
    chart_type = "day" if is_day else "night"

    result_parts = _compute_parts(
        natal["planets"],
        natal["angles"],
        natal["houses"],
        degree_format,
        parts,
    )

    return {
        "chart_type": chart_type,
        "parts": result_parts,
    }
