"""Tool 2: calculate_transits."""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    aspect_delta,
    calc_all_planets,
    calc_planet,
    find_aspects,
    find_exact_aspect_jd,
    jd_to_iso,
    pid_for,
    to_jd,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import build_legend, serialize_point, strip_nulls
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import (
    ANGLE_KEYS,
    ASPECT_ANGLES,
    PLANET_IDS,
    ChartPoint,
    aspect_significance,
    rank_aspects,
)
from astro_mcp.core.moon import moon_phase, moon_void_of_course, next_lunations
from astro_mcp.tools.natal import compute_natal

# Upper bound on a scanned window.  The day-by-day scan below evaluates every
# transiting body against every natal point for every aspect, so the cost is
# linear in the number of days; 366 keeps the worst case comfortably
# sub-second while still covering the "next year" question users actually ask.
MAX_PERIOD_DAYS = 366

FAST_KEYS = frozenset({"Mo", "Me", "Ve", "Ma", "Su"})

# Past a couple of weeks the Moon's events are noise: it aspects every natal
# point roughly once a month, so a 90-day scan produced 708 lunar events out of
# 948 -- 70% of the payload -- burying the slow contacts that actually carry a
# forecast.  Beyond this many days the default moon_events mode drops lunar
# contacts entirely unless asked for.
MOON_EVENT_MAX_DAYS = 14

# In "phases_void" mode only the Moon's own luminaries are events: transiting
# Moon conjunct the natal Sun is a New Moon, opposition a Full Moon. Phases,
# next lunations and void-of-course always live in the "moon" block instead.
LUNATION_ASPECTS = frozenset({"Cnj", "Opp"})

# How far either side of the queried moment to look for the exact hit of an
# aspect that is currently within orb.  Slow outer-planet aspects can stay in
# orb for months, so a symmetric window is used rather than the previous
# lopsided -10/+30 days.
EXACT_SEARCH_DAYS = 200


def _pid(key: str) -> int:
    """Deprecated alias; the canonical resolver lives in ephemeris_provider."""
    return pid_for(key)


def _transit_snapshot(
    jd: float,
    natal_cusps: list[float],
    fast_planets_only: bool,
    include_asteroids: bool = False,
) -> dict[str, ChartPoint]:
    """Positions of the transiting bodies, housed against the NATAL cusps.

    The houses are deliberately the natal ones. This tool answers "what is
    transiting my chart", and the standard reading of a transiting planet's
    house is the natal house it is moving through -- "transiting Saturn is
    crossing your 7th". Housing them against a chart cast for the transit
    moment instead (which is what this did previously) disagreed with the natal
    house for essentially every body and made the field unusable for the one
    question it exists to answer.
    """
    planets = calc_all_planets(jd, natal_cusps, include_asteroids=include_asteroids)
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
    pid = _pid(tp_code)
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
    transit_keys: list[str],
) -> list[dict[str, Any]]:
    """Find every transit-to-natal aspect that perfects inside the window.

    ``jd_start`` is midnight UTC on the first day, and the window covers
    ``days`` whole calendar days from there. Anchoring on midnight rather than
    on the transit moment keeps this consistent with
    :func:`~astro_mcp.tools.ephemeris.find_aspect_exact_dates`, which reports
    the same perfections for the same date range.

    ``transit_keys`` is supplied by the caller so that the bodies producing
    events are exactly the bodies whose positions are also reported; deriving
    it independently here previously leaked asteroid events into a result whose
    ``transit_planets`` contained no asteroids.

    Samples once per day, watching for a sign change in :func:`aspect_delta`,
    then bisects the bracketing day for the exact moment.
    """
    jd_end = jd_start + days

    # Cache one longitude sample per body per day; the scan reuses each sample
    # across all natal points and aspect angles.
    samples: list[tuple[float, dict[str, float]]] = []
    for day in range(days + 1):
        jd = jd_start + day
        samples.append((jd, {k: calc_planet(jd, _pid(k))[0] for k in transit_keys}))

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
                            _pid(tp), None, asp_angle,
                            jd - 1, jd, natal_lon2=natal_lon,
                        )
                        if ex_jd is not None and jd_start <= ex_jd < jd_end:
                            _, speed = calc_planet(ex_jd, _pid(tp))
                            events.append({
                                "tp": tp,
                                "np": np_code,
                                "asp": asp_code,
                                "exact": jd_to_iso(ex_jd)[:10],
                                "retro": speed < 0,
                                # Exact at perfection: tightness is maximal by
                                # definition, so the score reflects bodies and
                                # aspect type only.
                                "sig": aspect_significance(tp, np_code, asp_code, 0.0, 1.0),
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
    include_asteroids: bool = False,
    moon_events: str | None = None,
    house_system: str = "P",
    degree_format: str = "dec",
    max_orb: float | None = 3.0,
    min_significance: float | None = None,
    top_n: int | None = None,
    include_legend: bool = False,
) -> dict[str, Any]:
    """
    Calculate transit planets and their aspects to natal chart.
    birth_date, birth_time, birth_location are required.

    transit_time: Local time at the transit location (HH:MM). Defaults to
        noon local time.  Provide together with transit_location so the
        correct timezone is used for the conversion to UTC.
    transit_location: Used only to resolve the timezone that ``transit_time``
        is expressed in. Houses are always the natal ones, so relocating does
        not move the transiting planets between houses.
    period_days: When greater than 1, an ``aspect_events`` list is returned
        covering every transit-to-natal aspect that perfects within
        ``[transit_date, transit_date + period_days]``.
    include_asteroids: Add Ceres, Pallas, Juno and Vesta to both the reported
        positions and the event scan.
    moon_events: Lunar contacts in ``aspect_events``: 'all', 'phases_void'
        (only New/Full Moon contacts with the natal Sun) or 'none'. Defaults
        to 'phases_void' for windows up to ``MOON_EVENT_MAX_DAYS`` days and
        'none' beyond, where full lunar output would swamp the slower
        contacts.
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

    # Transit geo is resolved only for its timezone: transit_time is a local
    # wall-clock time at that place.
    if transit_location:
        tgeo = resolve_location(transit_location)
    else:
        tgeo = chart.geo

    try:
        Date.fromisoformat(transit_date)
    except ValueError as exc:
        raise AstroError(
            "INVALID_DATE", f"transit_date '{transit_date}' is not a valid YYYY-MM-DD date."
        ) from exc

    utc_str, _ = local_to_utc(transit_date, transit_time or "12:00", tgeo.tz)
    jd = to_jd(utc_str)

    transit_planets = _transit_snapshot(
        jd, chart.cusps, fast_planets_only, include_asteroids
    )

    raw_aspects = find_aspects(
        transit_planets,
        natal_points,
        custom_orbs=orbs,
        angle_orb_keys=set(ANGLE_KEYS),
    )

    # max_orb is a relevance cut, so it runs before the significance ranking:
    # otherwise top_n could keep an out-of-orb aspect over an in-orb one.
    in_orb = [a for a in raw_aspects if max_orb is None or a.orb <= max_orb]
    aspects_out: list[dict[str, Any]] = []
    for asp in rank_aspects(in_orb, min_significance=min_significance, top_n=top_n):
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
            "sig": asp.significance,
            "exact": exact,
        }))

    result: dict[str, Any] = {
        "date": transit_date,
        "dt": utc_str,
        "period_days": period_days,
        "moon": {
            **moon_phase(jd),
            **next_lunations(jd),
            "voc": moon_void_of_course(jd),
        },
        "transit_planets": {
            k: serialize_point(v, degree_format) for k, v in transit_planets.items()
        },
        "aspects": aspects_out,
    }

    if include_legend:
        result["legend"] = build_legend()

    if period_days > 1:
        # Only bodies whose positions are reported may produce events, so the
        # two halves of the result can never disagree about what was scanned.
        # SN is excluded: it sits exactly opposite NN, so its events are the
        # same contacts with the aspect mirrored, and listing both doubles the
        # nodal rows for no extra information.
        event_keys = [k for k in transit_planets if k in PLANET_IDS and k != "SN"]
        mode = (
            moon_events
            if moon_events is not None
            else ("phases_void" if period_days <= MOON_EVENT_MAX_DAYS else "none")
        )
        if mode == "none":
            event_keys = [k for k in event_keys if k != "Mo"]
            # State the reason that actually applied: claiming the window was
            # too long when the caller asked for the omission invites the
            # reader to infer an automatic threshold that did not fire.
            result["events_note"] = (
                "Lunar events omitted at your request (moon_events='none')."
                if moon_events is not None
                else (
                    f"Lunar events omitted: beyond {MOON_EVENT_MAX_DAYS} days the Moon "
                    "contacts every natal point and would dominate the list. Pass "
                    "moon_events='all' (or 'phases_void'), or query a shorter period, "
                    "to see them."
                )
            )
        # Events are reported for whole calendar days (UTC) starting on
        # transit_date, not for a window hanging off the transit moment.
        events = _scan_aspect_events(
            natal_points, to_jd(f"{transit_date}T00:00:00Z"), period_days, event_keys
        )
        if mode == "phases_void":
            events = [
                e for e in events
                if e["tp"] != "Mo"
                or (e["np"] == "Su" and e["asp"] in LUNATION_ASPECTS)
            ]
        if min_significance is not None:
            events = [e for e in events if e["sig"] >= min_significance]
        result["aspect_events"] = events

    return result
