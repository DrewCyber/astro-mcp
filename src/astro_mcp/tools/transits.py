"""Tool 2: calculate_transits."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    aspect_delta,
    calc_all_planets,
    calc_houses,
    calc_planet,
    find_aspects,
    find_exact_aspect_jd,
    jd_to_iso,
    resolve_house_system,
    to_jd,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_point, strip_nulls
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import ANGLE_KEYS, ASPECT_ANGLES, PLANET_IDS, ChartPoint
from astro_mcp.tools.natal import compute_natal

# Upper bound on a scanned window.  The day-by-day scan below evaluates every
# transiting body against every natal point for every aspect, so the cost is
# linear in the number of days; 366 keeps the worst case comfortably
# sub-second while still covering the "next year" question users actually ask.
MAX_PERIOD_DAYS = 366

FAST_KEYS = frozenset({"Mo", "Me", "Ve", "Ma", "Su"})

# How far either side of the queried moment to look for the exact hit of an
# aspect that is currently within orb.  Slow outer-planet aspects can stay in
# orb for months, so a symmetric window is used rather than the previous
# lopsided -10/+30 days.
EXACT_SEARCH_DAYS = 200


def _transit_snapshot(
    jd: float,
    lat: float,
    lon: float,
    house_system: str,
    fast_planets_only: bool,
) -> dict[str, ChartPoint]:
    cusps, _ = calc_houses(jd, lat, lon, house_system)
    planets = calc_all_planets(jd, cusps, include_asteroids=False)
    if fast_planets_only:
        planets = {k: v for k, v in planets.items() if k in FAST_KEYS}
    return planets


def _find_exact_near(
    tp_code: str,
    natal_lon: float,
    asp_angle: float,
    jd: float,
) -> str | None:
    """Locate the exact date of an in-orb aspect by bracketing around ``jd``.

    Walks outwards in half-window steps so the nearest perfection is found
    rather than an arbitrary one inside a wide bracket.
    """
    pid = PLANET_IDS[tp_code]
    for half in (5.0, 20.0, 60.0, EXACT_SEARCH_DAYS):
        ex_jd = find_exact_aspect_jd(
            pid, None, asp_angle, jd - half, jd + half, natal_lon2=natal_lon
        )
        if ex_jd:
            return jd_to_iso(ex_jd)[:10]
    return None


def _scan_aspect_events(
    natal_points: dict[str, ChartPoint],
    jd_start: float,
    days: int,
    fast_planets_only: bool,
) -> list[dict[str, Any]]:
    """Find every transit-to-natal aspect that perfects inside the window.

    ``jd_start`` is midnight UTC on the first day, and the window covers
    ``days`` whole calendar days from there. Anchoring on midnight rather than
    on the transit moment keeps this consistent with
    :func:`~astro_mcp.tools.ephemeris.find_aspect_exact_dates`, which reports
    the same perfections for the same date range.

    Samples once per day, watching for a sign change in :func:`aspect_delta`,
    then bisects the bracketing day for the exact moment.
    """
    transit_keys = [k for k in PLANET_IDS if k != "NN_m"]
    if fast_planets_only:
        transit_keys = [k for k in transit_keys if k in FAST_KEYS]

    jd_end = jd_start + days

    # Cache one longitude sample per body per day; the scan reuses each sample
    # across all natal points and aspect angles.
    samples: list[tuple[float, dict[str, float]]] = []
    for day in range(days + 1):
        jd = jd_start + day
        samples.append((jd, {k: calc_planet(jd, PLANET_IDS[k])[0] for k in transit_keys}))

    events: list[dict[str, Any]] = []
    for tp in transit_keys:
        for np_code, np_point in natal_points.items():
            natal_lon = np_point.lon_decimal
            for asp_code, asp_angle in ASPECT_ANGLES.items():
                prev_delta: float | None = None
                for jd, lons in samples:
                    delta = aspect_delta(lons[tp], natal_lon, asp_angle)
                    # The second condition guards against the discontinuity that
                    # a full wrap would introduce between two daily samples.
                    if (prev_delta is not None and prev_delta * delta < 0
                            and abs(prev_delta - delta) < 180):
                        ex_jd = find_exact_aspect_jd(
                            PLANET_IDS[tp], None, asp_angle,
                            jd - 1, jd, natal_lon2=natal_lon,
                        )
                        if ex_jd is not None and jd_start <= ex_jd < jd_end:
                            _, speed = calc_planet(ex_jd, PLANET_IDS[tp])
                            events.append({
                                "tp": tp,
                                "np": np_code,
                                "asp": asp_code,
                                "exact": jd_to_iso(ex_jd)[:10],
                                "retro": speed < 0,
                            })
                    prev_delta = delta

    events.sort(key=lambda e: e["exact"])
    return events


def calculate_transits(
    transit_date: str = "",
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    transit_time: str | None = None,
    period_days: int = 1,
    transit_location: str | dict[str, Any] | None = None,
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
    period_days: When greater than 1, an ``aspect_events`` list is returned
        covering every transit-to-natal aspect that perfects within
        ``[transit_date, transit_date + period_days]``.
    """
    if not transit_date:
        raise AstroError("INPUT_ERROR", "transit_date is required.")
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    if period_days < 1 or period_days > MAX_PERIOD_DAYS:
        raise AstroError(
            "RANGE_TOO_LONG",
            f"period_days must be between 1 and {MAX_PERIOD_DAYS}.",
        )

    chart = compute_natal(birth_date, birth_time, birth_location, house_system)
    natal_points = chart.all_points

    # Transit geo — resolve fully so we have the timezone
    if transit_location:
        tgeo = resolve_location(transit_location)
    else:
        tgeo = chart.geo
    transit_hs, hs_warning = resolve_house_system(house_system, tgeo.lat)

    try:
        Date.fromisoformat(transit_date)
    except ValueError as exc:
        raise AstroError(
            "INVALID_DATE", f"transit_date '{transit_date}' is not a valid YYYY-MM-DD date."
        ) from exc

    utc_str, _ = local_to_utc(transit_date, transit_time or "12:00", tgeo.tz)
    jd = to_jd(utc_str)

    transit_planets = _transit_snapshot(
        jd, tgeo.lat, tgeo.lon, transit_hs, fast_planets_only
    )

    raw_aspects = find_aspects(
        transit_planets,
        natal_points,
        custom_orbs=orbs,
        angle_orb_keys=set(ANGLE_KEYS),
    )

    aspects_out: list[dict[str, Any]] = []
    for asp in raw_aspects:
        if max_orb is not None and asp.orb > max_orb:
            continue
        exact = None
        if asp.point1 in PLANET_IDS and asp.point2 in natal_points:
            exact = _find_exact_near(
                asp.point1,
                natal_points[asp.point2].lon_decimal,
                ASPECT_ANGLES[asp.aspect_type],
                jd,
            )
        aspects_out.append(strip_nulls({
            "tp": asp.point1,
            "np": asp.point2,
            "asp": asp.aspect_type,
            "orb": asp.orb,
            "apply": asp.applying,
            "exact": exact,
        }))
    aspects_out.sort(key=lambda a: a["orb"])

    result: dict[str, Any] = {
        "date": transit_date,
        "dt": utc_str,
        "period_days": period_days,
        "transit_planets": {
            k: serialize_point(v, degree_format) for k, v in transit_planets.items()
        },
        "aspects": aspects_out,
    }
    if hs_warning:
        result["house_system_warning"] = hs_warning

    if period_days > 1:
        # Events are reported for whole calendar days (UTC) starting on
        # transit_date, not for a window hanging off the transit moment.
        result["aspect_events"] = _scan_aspect_events(
            natal_points, to_jd(f"{transit_date}T00:00:00Z"), period_days, fast_planets_only
        )

    return result
