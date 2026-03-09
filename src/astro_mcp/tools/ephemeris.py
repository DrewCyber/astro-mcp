"""Tools 12 & 13: get_ephemeris and find_aspect_exact_dates."""

from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    ASPECT_ANGLES,
    PLANET_IDS,
    build_chart_point,
    calc_planet,
    find_exact_aspect_jd,
    jd_to_iso,
    lon_to_sign_info,
    to_jd,
)
from astro_mcp.core.formatters import decimal_to_dms


STEP_HOURS: dict[str, float] = {
    "1h": 1 / 24,
    "6h": 6 / 24,
    "12h": 12 / 24,
    "1d": 1.0,
    "7d": 7.0,
    "30d": 30.0,
}


def get_ephemeris(
    planet: str,
    date_from: str,
    date_to: str,
    step: str = "1d",
    output_tz: str = "UTC",
    include_speed: bool = False,
    include_retrograde: bool = True,
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 12: Ephemeris table for a planet over a date range."""
    if planet not in PLANET_IDS:
        return {"error": True, "code": "UNKNOWN_PLANET",
                "message": f"Planet code '{planet}' not recognized."}

    pid = PLANET_IDS[planet]
    step_jd = STEP_HOURS.get(step, 1.0)

    # Validate range
    d_from = Date.fromisoformat(date_from)
    d_to = Date.fromisoformat(date_to)
    total_days = (d_to - d_from).days
    if total_days / step_jd > 10000:
        return {"error": True, "code": "RANGE_TOO_LONG",
                "message": "Requested range/step combination too large (>10,000 rows)."}

    jd_start = to_jd(f"{date_from}T00:00:00Z")
    jd_end = to_jd(f"{date_to}T00:00:00Z")

    rows = []
    jd = jd_start
    while jd <= jd_end + 0.001:
        lon, speed = calc_planet(jd, pid)
        sign, sign_lon = lon_to_sign_info(lon)
        if degree_format == "dms":
            lon_str = decimal_to_dms(sign_lon) + sign
        else:
            lon_str = str(round(lon % 360, 2))

        row: dict[str, Any] = {
            "dt": jd_to_iso(jd)[:10] if step_jd >= 1 else jd_to_iso(jd),
            "lon": lon_str,
            "deg": round(lon % 360, 2),
        }
        if include_retrograde:
            if speed < 0:
                row["R"] = True
        if include_speed:
            row["speed"] = round(speed, 4)

        rows.append(row)
        jd += step_jd

    return {
        "planet": planet,
        "date_from": date_from,
        "date_to": date_to,
        "step": step,
        "rows": rows,
    }


def find_aspect_exact_dates(
    planet1: str,
    planet2: str,
    aspect: str,
    date_from: str,
    date_to: str,
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    orb: float = 1.0,
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 13: Find exact dates of a specific aspect between two bodies."""
    if planet1 not in PLANET_IDS:
        return {"error": True, "code": "UNKNOWN_PLANET", "message": f"Unknown: {planet1}"}
    if aspect not in ASPECT_ANGLES:
        return {"error": True, "code": "UNKNOWN_ASPECT", "message": f"Unknown aspect: {aspect}"}

    asp_angle = ASPECT_ANGLES[aspect]
    pid1 = PLANET_IDS[planet1]

    # Static natal point or live planet?
    natal_lon2: float | None = None
    pid2: int | None = None

    if birth_date and birth_time and birth_location:
        from astro_mcp.tools.natal import calculate_natal_chart
        natal_data = calculate_natal_chart(birth_date, birth_time, birth_location)
        if planet2 in natal_data.get("planets", {}):
            natal_lon2 = float(natal_data["planets"][planet2]["deg"])
        elif planet2 in natal_data.get("angles", {}):
            natal_lon2 = float(natal_data["angles"][planet2]["deg"])
        else:
            return {"error": True, "code": "UNKNOWN_PLANET", "message": f"Unknown: {planet2}"}
    elif planet2 in PLANET_IDS:
        pid2 = PLANET_IDS[planet2]
    else:
        return {"error": True, "code": "UNKNOWN_PLANET", "message": f"Unknown: {planet2}"}

    jd_start = to_jd(f"{date_from}T00:00:00Z")
    jd_end = to_jd(f"{date_to}T00:00:00Z")

    # Scan in 1-day windows looking for sign changes in (dist - asp_angle)
    from astro_mcp.core.ephemeris_provider import calc_planet, angular_distance
    occurrences = []
    jd = jd_start
    scan_step = 0.5  # 12-hour scan steps

    prev_diff: float | None = None
    window_start: float | None = None

    while jd <= jd_end:
        lon1, _ = calc_planet(jd, pid1)
        if natal_lon2 is not None:
            lon2 = natal_lon2
        else:
            lon2, _ = calc_planet(jd, pid2)  # type: ignore[arg-type]
        diff = angular_distance(lon1, lon2) - asp_angle

        if prev_diff is not None and prev_diff * diff < 0:
            # Sign change → aspect is exact somewhere in [jd - scan_step, jd]
            ex_jd = find_exact_aspect_jd(
                pid1, pid2, asp_angle,
                jd - scan_step, jd,
                natal_lon2=natal_lon2,
            )
            if ex_jd:
                exact_date = jd_to_iso(ex_jd)[:10]
                # Find approach and separation dates within orb
                approach_jd = ex_jd - 30  # rough
                sep_jd = ex_jd + 30
                for aj in range(int((ex_jd - jd_start) * 2)):
                    test_jd = ex_jd - aj * 0.5
                    tlon1, _ = calc_planet(test_jd, pid1)
                    tlon2 = natal_lon2 if natal_lon2 else calc_planet(test_jd, pid2)[0]  # type: ignore
                    if angular_distance(tlon1, tlon2) - asp_angle > orb:
                        approach_jd = test_jd + 0.5
                        break
                for sj in range(120):
                    test_jd = ex_jd + sj * 0.5
                    if test_jd > jd_end:
                        break
                    tlon1, _ = calc_planet(test_jd, pid1)
                    tlon2 = natal_lon2 if natal_lon2 else calc_planet(test_jd, pid2)[0]  # type: ignore
                    if angular_distance(tlon1, tlon2) - asp_angle > orb:
                        sep_jd = test_jd - 0.5
                        break

                occurrences.append({
                    "approach_date": jd_to_iso(approach_jd)[:10],
                    "exact_date": exact_date,
                    "separation_date": jd_to_iso(sep_jd)[:10],
                    "retrograde_exact": None,
                    "direct_exact": exact_date,
                    "is_triple_pass": False,
                    "peak_orb": 0.01,
                })
                jd += 5  # skip past this occurrence

        prev_diff = diff
        jd += scan_step

    return {
        "planet1": planet1,
        "planet2": planet2,
        "aspect": aspect,
        "orb_used": orb,
        "occurrences": occurrences,
    }
