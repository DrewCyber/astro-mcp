"""Tool 11: calculate_arabic_parts."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.ephemeris_provider import angular_distance, calc_all_planets, to_jd
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.models import ASPECT_ANGLES, SIGNS, ChartPoint, HouseCusp
from astro_mcp.tools.natal import compute_natal

# ---------------------------------------------------------------------------
# Arabic Part formulas: (name, day_formula_tokens, night_formula_tokens)
# Each formula token: planet/angle code or "8th_cusp" etc.
# Format: (A, B, C) where result = A + B - C
# ---------------------------------------------------------------------------

PART_FORMULAS: dict[str, tuple[str, str, str, str, str, str]] = {
    # code: (day_A, day_B, day_C, night_A, night_B, night_C)
    "FortPt":    ("Asc", "Mo",       "Su",  "Asc", "Su",       "Mo"),
    "SpiritPt":  ("Asc", "Su",       "Mo",  "Asc", "Mo",       "Su"),
    "MarriagePt":("Asc", "Dsc",      "Ve",  "Asc", "Dsc",      "Ve"),
    "DeathPt":   ("Asc", "8th_cusp", "Mo",  "Asc", "8th_cusp", "Sa"),
    "ChildrenPt":("Asc", "Ju",       "Sa",  "Asc", "Sa",       "Ju"),
    "CareerPt":  ("MC",  "Mo",       "Su",  "MC",  "Su",       "Mo"),
    "TravelPt":  ("Asc", "9th_cusp", "Ju",  "Asc", "9th_cusp", "Sa"),
    # Health lots
    "IllnessPt": ("Asc", "Sa",       "Ma",  "Asc", "Ma",       "Sa"),
    "InjuryPt":  ("Asc", "Ma",       "Sa",  "Asc", "Sa",       "Ma"),
    # Additional classic lots
    "FatherPt":  ("Asc", "Su",       "Sa",  "Asc", "Sa",       "Su"),
    "MotherPt":  ("Asc", "Mo",       "Ve",  "Asc", "Ve",       "Mo"),
    "SaturnPt":  ("Asc", "Sa",       "Su",  "Asc", "Su",       "Sa"),
}


_HOUSE_CUSP_CODES: dict[str, int] = {
    "1st_cusp": 1, "2nd_cusp": 2, "3rd_cusp": 3, "4th_cusp": 4,
    "5th_cusp": 5, "6th_cusp": 6, "7th_cusp": 7, "8th_cusp": 8,
    "9th_cusp": 9, "10th_cusp": 10, "11th_cusp": 11, "12th_cusp": 12,
}


def _get_lon(
    code: str,
    planets: dict[str, ChartPoint],
    angles: dict[str, ChartPoint],
    houses: list[HouseCusp],
) -> float:
    """Resolve a planet/angle/house-cusp code to decimal longitude."""
    if code in planets:
        return planets[code].lon_decimal
    if code in angles:
        return angles[code].lon_decimal
    if code in _HOUSE_CUSP_CODES:
        idx = _HOUSE_CUSP_CODES[code] - 1
        if idx < len(houses):
            return houses[idx].lon_decimal
    raise KeyError(f"Unknown chart point: {code}")


def compute_part_points(
    planets: dict[str, ChartPoint],
    angles: dict[str, ChartPoint],
    houses: list[HouseCusp],
    parts: list[str] | None = None,
    *,
    is_day: bool,
) -> dict[str, ChartPoint]:
    """Compute Arabic parts from natal chart points.

    ``is_day`` selects the sect of each formula (diurnal vs nocturnal).  It
    must come from a single source of truth — ``NatalChart.is_day``, derived
    from solar altitude.
    """

    result: dict[str, ChartPoint] = {}
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
        result[code] = pt

    return result


def compute_parts(
    planets: dict[str, ChartPoint],
    angles: dict[str, ChartPoint],
    houses: list[HouseCusp],
    degree_format: str = "dec",
    parts: list[str] | None = None,
    *,
    is_day: bool,
) -> dict[str, Any]:
    points = compute_part_points(planets, angles, houses, parts, is_day=is_day)
    return {
        code: serialize_point(point, degree_format, include_house=False)
        for code, point in points.items()
    }


def calculate_arabic_parts(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    parts: list[str] | None = None,
    house_system: str = "P",
    degree_format: str = "dec",
    include_transits_date: str | None = None,
) -> dict[str, Any]:
    """Tool 11: Arabic (Hermetic) Parts / Lots."""
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    chart = compute_natal(birth_date, birth_time, birth_location, house_system)

    chart_type = "day" if chart.is_day else "night"

    result_parts = compute_part_points(
        chart.planets, chart.angles, chart.houses, parts, is_day=chart.is_day,
    )

    out: dict[str, Any] = {
        "chart_type": chart_type,
        "parts": {
            code: serialize_point(point, degree_format, include_house=False)
            for code, point in result_parts.items()
        },
    }

    if include_transits_date:
        jd_transit = to_jd(f"{include_transits_date}T12:00:00Z")
        tr_planets = calc_all_planets(jd_transit)
        transit_activations: dict[str, list[dict[str, Any]]] = {}
        for part_code, part_point in result_parts.items():
            activations: list[dict[str, Any]] = []
            for tp_code, tp_point in tr_planets.items():
                for asp_name, asp_angle in ASPECT_ANGLES.items():
                    o = abs(angular_distance(tp_point.lon_decimal, part_point.lon_decimal) - asp_angle)
                    if o <= 3.0:
                        activations.append({
                            "planet": tp_code,
                            "asp": asp_name,
                            "orb": round(o, 2),
                        })
            if activations:
                activations.sort(key=lambda x: float(x["orb"]))
                transit_activations[part_code] = activations
        if transit_activations:
            out["transit_activations"] = transit_activations
            out["transits_date"] = include_transits_date

    return out
