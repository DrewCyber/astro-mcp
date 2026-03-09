"""Tool 2: calculate_transits."""

from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    ASPECT_ANGLES,
    PLANET_IDS,
    angular_distance,
    build_chart_point,
    calc_all_planets,
    calc_houses,
    calc_planet,
    find_aspects,
    find_exact_aspect_jd,
    jd_to_iso,
    to_jd,
)
from astro_mcp.core.formatters import serialize_point, strip_nulls
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import DEFAULT_ORBS, Aspect, ChartPoint
from astro_mcp.tools.natal import calculate_natal_chart


def _natal_to_points(natal: dict) -> dict[str, ChartPoint]:
    """Extract ChartPoint map from a full natal chart dict (by deserializing deg)."""
    points: dict[str, ChartPoint] = {}
    from astro_mcp.core.models import SIGNS
    for key in ("planets", "angles"):
        for pcode, pdata in natal.get(key, {}).items():
            lon = pdata.get("deg", 0.0)
            sign = pdata.get("sign", "Ari")
            sign_lon = lon % 30
            cp = ChartPoint(
                lon_decimal=lon % 360,
                sign=sign,
                sign_lon=sign_lon,
                house=pdata.get("house"),
                retrograde=pdata.get("R", False),
                speed=0.0,
            )
            points[pcode] = cp
    return points


def calculate_transits(
    transit_date: str = "",
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    transit_time: str | None = None,
    period_days: int = 1,
    transit_location: str | dict | None = None,
    orbs: dict[str, float] | None = None,
    fast_planets_only: bool = False,
    house_system: str = "P",
    degree_format: str = "dms",
    max_orb: float | None = 3.0,
) -> dict[str, Any]:
    """
    Calculate transit planets and their aspects to natal chart.
    birth_date, birth_time, birth_location are required.

    transit_time: Local time at the transit location (HH:MM). Defaults to
        noon local time.  Provide together with transit_location so the
        correct timezone is used for the conversion to UTC.
    """
    # Guard for missing transit_date
    if not transit_date:
        return {"error": True, "code": "TRANSIT_DATE_MISSING", "message": "transit_date is required."}

    # Resolve natal chart
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    natal_points = _natal_to_points(natal)

    # Transit geo — resolve fully so we have the timezone
    if transit_location:
        geo = resolve_location(transit_location)
        geo_lat = geo.lat
        geo_lon = geo.lon
        transit_tz = geo.tz
    else:
        loc = natal["meta"]["loc"]
        geo_lat = loc["lat"]
        geo_lon = loc["lon"]
        transit_tz = loc.get("tz", "UTC")

    # Build transit date range
    date_obj = Date.fromisoformat(transit_date)
    dates = [date_obj + timedelta(days=i) for i in range(max(1, period_days))]

    fast_keys = {"Mo", "Me", "Ve", "Ma", "Su"}
    all_results = []

    for d in dates[:1]:  # first date for single-day response; full for period
        # Convert local transit time → UTC using the transit location's timezone
        time_str = transit_time or "12:00"
        utc_str, _ = local_to_utc(d.isoformat(), time_str, transit_tz)
        jd = to_jd(utc_str)
        cusps, ascmc = calc_houses(jd, geo_lat, geo_lon, house_system)
        transit_planets = calc_all_planets(
            jd, cusps,
            include_asteroids=False,
            use_mean_node=True,
            include_lilith=True,
            include_chiron=True,
        )

        if fast_planets_only:
            transit_planets = {k: v for k, v in transit_planets.items() if k in fast_keys}

        # Find aspects
        custom_orbs = orbs
        raw_aspects = find_aspects(
            transit_planets,
            natal_points,
            custom_orbs=custom_orbs,
            angle_orb_keys={"Asc", "MC", "Dsc", "IC"},
        )

        # Compute exact dates via bisection
        aspects_out = []
        for asp in raw_aspects:
            exact = None
            tp_code = asp.point1
            np_code = asp.point2
            if tp_code in PLANET_IDS and np_code in natal_points:
                pid = PLANET_IDS[tp_code]
                natal_lon = natal_points[np_code].lon_decimal
                jd_search_end = jd + (period_days if period_days > 1 else 30)
                ex_jd = find_exact_aspect_jd(
                    pid, None, ASPECT_ANGLES[asp.aspect_type],
                    jd - 10, jd_search_end,
                    natal_lon2=natal_lon,
                )
                if ex_jd:
                    exact = jd_to_iso(ex_jd)[:10]  # date only
            aspects_out.append(strip_nulls({
                "tp": asp.point1,
                "np": asp.point2,
                "asp": asp.aspect_type,
                "orb": asp.orb,
                "apply": asp.applying,
                "exact": exact,
            }))

        aspects_out.sort(key=lambda a: a["orb"])
        if max_orb is not None:
            aspects_out = [a for a in aspects_out if a["orb"] <= max_orb]
        return {
            "date": transit_date,
            "transit_planets": {
                k: serialize_point(v, degree_format) for k, v in transit_planets.items()
            },
            "aspects": aspects_out,
        }

    return {}
