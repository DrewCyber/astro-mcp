"""Tools 12 & 13: get_ephemeris and find_aspect_exact_dates."""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from astro_mcp.core.ephemeris_provider import (
    aspect_delta,
    calc_planet,
    find_exact_aspect_jd,
    jd_to_iso,
    lon_to_sign_info,
    pid_for,
    to_jd,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import decimal_to_dms
from astro_mcp.core.models import ASPECT_ANGLES, PLANET_IDS

MAX_EPHEMERIS_ROWS = 10_000

STEP_HOURS: dict[str, float] = {
    "1h": 1 / 24,
    "2h": 2 / 24,
    "3h": 3 / 24,
    "6h": 6 / 24,
    "12h": 12 / 24,
    "1d": 1.0,
    "7d": 7.0,
    "30d": 30.0,
}

# A retrograde loop can carry a body back and forth across the same aspect at
# most three times, and the whole sequence fits inside roughly half a year even
# for the slowest pairings.
TRIPLE_PASS_WINDOW_DAYS = 200

# Two exact hits are only folded into one occurrence when their gap also fits
# inside half the pair's synodic cycle: within half a cycle the bodies cannot
# complete a full lap of each other, so hits that close together belong to one
# loop, while hits further apart are independent events (successive lunations,
# successive Mercury retrogrades, ...). Without this cap every Moon aspect in a
# year-long window collapsed into a single fabricated "triple pass".
SYNODIC_GROUP_FRACTION = 0.5

# The Moon covers ~13 degrees a day, so it can pass clean through an aspect --
# and back out of orb -- inside a single coarse scan step. Every other body is
# slow enough for the wide step.
FAST_SCAN_STEP_DAYS = 1 / 8      # 3 hours
DEFAULT_SCAN_STEP_DAYS = 0.5
FAST_BODIES = frozenset({"Mo"})

# Guard against a Moon scan over a decade at 3-hour resolution.
MAX_SCAN_SAMPLES = 200_000


def _end_of_day_jd(date_to: str) -> float:
    """Julian Day for the *end* of ``date_to``.

    ``date_to`` names a day, not an instant. Anchoring it at 00:00 silently
    excluded the whole of the final requested day, so an aspect perfecting at
    00:40 on ``date_to`` was reported as not happening at all.
    """
    return to_jd(f"{date_to}T23:59:59Z")


def _scan_step_days(moving: set[str]) -> float:
    """Scan resolution needed to avoid stepping over a perfection."""
    return FAST_SCAN_STEP_DAYS if moving & FAST_BODIES else DEFAULT_SCAN_STEP_DAYS


def _mean_daily_motion(jd: float, pid: int) -> float:
    """Average signed geocentric motion of a body over one year (deg/day).

    Longitude wraps, so the year cannot be measured as one delta: it is
    integrated from short arcs (5 days — under 180 degrees even for the Moon,
    so each arc's wrapped increment is unambiguous). Sampling a full year lets
    retrograde episodes cancel out, yielding the body's mean drift — exactly
    what the synodic-period estimate needs.
    """
    step = 5.0
    n = round(365.25 / step)
    total = 0.0
    jd_a = jd
    for _ in range(n):
        lon_a, _ = calc_planet(jd_a, pid)
        jd_b = jd_a + step
        lon_b, _ = calc_planet(jd_b, pid)
        total += (((lon_b - lon_a + 180.0) % 360.0) - 180.0)
        jd_a = jd_b
    return total / (n * step)


def _group_window_days(
    jd_start: float,
    pid1: int,
    pid2: int | None,
) -> float:
    """Max gap between consecutive exact hits treated as ONE retrograde loop.

    The 200-day window is only safe for slow pairs. For any faster pairing the
    loop cap is tightened to ``SYNODIC_GROUP_FRACTION`` of the pair's synodic
    cycle: hits closer than that cannot be separated by a complete lap, while
    hits further apart are independent events.
    """
    rel_speed = abs(_mean_daily_motion(jd_start, pid1))
    if pid2 is not None:
        rel_speed = abs(rel_speed - _mean_daily_motion(jd_start, pid2))
    if rel_speed < 1e-9:
        return TRIPLE_PASS_WINDOW_DAYS
    return min(TRIPLE_PASS_WINDOW_DAYS, SYNODIC_GROUP_FRACTION * 360.0 / rel_speed)


def _resolve_step_days(step: str, interval_days: int | None, interval_hours: int | None) -> float:
    if interval_hours is not None and interval_hours > 0:
        return float(interval_hours) / 24.0
    if interval_days is not None and interval_days > 0:
        return float(interval_days)
    return STEP_HOURS.get(step, 1.0)


def _parse_date(value: str, field: str) -> Date:
    try:
        return Date.fromisoformat(value)
    except ValueError as exc:
        raise AstroError(
            "INVALID_DATE", f"{field} '{value}' is not a valid YYYY-MM-DD date."
        ) from exc


def _format_dt_for_tz(jd: float, step_jd: float, output_tz: str) -> str:
    dt_utc = datetime.fromisoformat(jd_to_iso(jd).replace("Z", "+00:00"))
    dt_local = dt_utc.astimezone(ZoneInfo(output_tz))
    if step_jd >= 1:
        return dt_local.date().isoformat()
    return dt_local.isoformat()


def _build_ephemeris_rows(
    planet: str,
    date_from: str,
    date_to: str,
    step_jd: float,
    output_tz: str,
    include_speed: bool,
    include_retrograde: bool,
    degree_format: str,
) -> list[dict[str, Any]]:
    pid = pid_for(planet)
    jd_start = to_jd(f"{date_from}T00:00:00Z")
    jd_end = _end_of_day_jd(date_to)

    rows = []
    jd = jd_start
    # jd_end is the last instant of date_to, so no float fudge is needed to
    # include the final row -- and adding one would emit a row past midnight.
    while jd <= jd_end:
        lon, speed = calc_planet(jd, pid)
        sign, sign_lon = lon_to_sign_info(lon)
        if degree_format == "dms":
            lon_str = decimal_to_dms(sign_lon) + sign
        else:
            lon_str = str(round(lon % 360, 2))

        row: dict[str, Any] = {
            "dt": _format_dt_for_tz(jd, step_jd, output_tz),
            "lon": lon_str,
            "deg": round(lon % 360, 2),
        }
        if include_retrograde and speed < 0:
            row["R"] = True
        if include_speed:
            row["speed"] = round(speed, 4)

        rows.append(row)
        jd += step_jd
    return rows


def get_ephemeris(
    planet: str | list[str],
    date_from: str,
    date_to: str,
    step: str = "1d",
    interval_days: int | None = None,
    interval_hours: int | None = None,
    output_tz: str = "UTC",
    include_speed: bool = False,
    include_retrograde: bool = True,
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 12: Ephemeris table for a planet over a date range."""
    planets = [planet] if isinstance(planet, str) else list(planet)
    unknown = [p for p in planets if p not in PLANET_IDS]
    if unknown:
        raise AstroError(
            "UNKNOWN_PLANET",
            f"Planet code(s) not recognized: {', '.join(unknown)}",
            hint=f"Valid codes: {', '.join(sorted(PLANET_IDS))}",
        )

    step_jd = _resolve_step_days(step, interval_days, interval_hours)

    d_from = _parse_date(date_from, "date_from")
    d_to = _parse_date(date_to, "date_to")
    if d_to < d_from:
        raise AstroError("INVALID_DATE", "date_to must be on or after date_from.")

    # date_to is inclusive, so the span covers one more day than the difference.
    total_days = (d_to - d_from).days + 1
    if total_days / step_jd > MAX_EPHEMERIS_ROWS:
        raise AstroError(
            "RANGE_TOO_LONG",
            f"Requested range/step combination exceeds {MAX_EPHEMERIS_ROWS:,} rows.",
            hint="Shorten the date range or use a larger step.",
        )

    try:
        ZoneInfo(output_tz)
    except Exception as exc:
        raise AstroError(
            "INPUT_ERROR",
            f"'{output_tz}' is not a valid IANA timezone.",
            hint="Use a name such as 'UTC' or 'Europe/Berlin'.",
        ) from exc

    base_payload = {
        "date_from": date_from,
        "date_to": date_to,
        "step": f"{interval_hours}h" if interval_hours else (f"{interval_days}d" if interval_days else step),
        "timezone": output_tz,
    }

    if len(planets) == 1:
        p = planets[0]
        return {
            **base_payload,
            "planet": p,
            "rows": _build_ephemeris_rows(
                p, date_from, date_to, step_jd, output_tz,
                include_speed, include_retrograde, degree_format,
            ),
        }

    return {
        **base_payload,
        "planets": planets,
        "rows_by_planet": {
            p: _build_ephemeris_rows(
                p, date_from, date_to, step_jd, output_tz,
                include_speed, include_retrograde, degree_format,
            )
            for p in planets
        },
    }


def _lon_at(jd: float, pid1: int, pid2: int | None, natal_lon2: float | None) -> tuple[float, float]:
    lon1, _ = calc_planet(jd, pid1)
    lon2 = natal_lon2 if natal_lon2 is not None else calc_planet(jd, pid2)[0]  # type: ignore[arg-type]
    return lon1, lon2


def find_aspect_exact_dates(
    planet1: str,
    planet2: str,
    aspect: str,
    date_from: str,
    date_to: str,
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    orb: float = 1.0,
    mode: str = "auto",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 13: Find exact dates of a specific aspect between two bodies.

    Groups crossings that belong to the same retrograde loop into a single
    occurrence so ``is_triple_pass`` and ``peak_orb`` describe the real event
    rather than a placeholder. Grouping is synodic-aware: fast pairs (anything
    involving the Moon or Mercury, say) produce independent occurrences per
    crossing instead of one fabricated year-long "loop".
    """
    if planet1 not in PLANET_IDS:
        raise AstroError("UNKNOWN_PLANET", f"Unknown planet code: {planet1}")
    if aspect not in ASPECT_ANGLES:
        raise AstroError(
            "UNKNOWN_ASPECT",
            f"Unknown aspect: {aspect}",
            hint=f"Valid aspects: {', '.join(ASPECT_ANGLES)}",
        )
    if orb <= 0:
        raise AstroError("INPUT_ERROR", "orb must be greater than 0.")

    asp_angle = ASPECT_ANGLES[aspect]
    pid1 = pid_for(planet1)

    natal_lon2: float | None = None
    pid2: int | None = None

    mode_resolved = mode
    if mode_resolved == "auto":
        mode_resolved = (
            "transit-to-natal"
            if (birth_date and birth_time and birth_location)
            else "transit-to-transit"
        )

    if mode_resolved == "transit-to-natal":
        if not (birth_date and birth_time and birth_location):
            raise AstroError(
                "INPUT_ERROR",
                "birth_date, birth_time and birth_location are required in "
                "transit-to-natal mode.",
            )
        from astro_mcp.tools.natal import compute_natal
        chart = compute_natal(birth_date, birth_time, birth_location)
        point = chart.all_points.get(planet2)
        if point is None:
            raise AstroError("UNKNOWN_PLANET", f"Unknown natal point: {planet2}")
        natal_lon2 = point.lon_decimal
    elif planet2 in PLANET_IDS:
        pid2 = pid_for(planet2)
    else:
        raise AstroError("UNKNOWN_PLANET", f"Unknown planet code: {planet2}")

    d_from = _parse_date(date_from, "date_from")
    d_to = _parse_date(date_to, "date_to")
    if d_to < d_from:
        raise AstroError("INVALID_DATE", "date_to must be on or after date_from.")

    jd_start = to_jd(f"{date_from}T00:00:00Z")
    jd_end = _end_of_day_jd(date_to)

    # In transit-to-natal mode the natal point is fixed, so only the transiting
    # body's speed decides how finely the range must be sampled.
    moving = {planet1} if mode_resolved == "transit-to-natal" else {planet1, planet2}
    scan_step = _scan_step_days(moving)
    if (jd_end - jd_start) / scan_step > MAX_SCAN_SAMPLES:
        raise AstroError(
            "RANGE_TOO_LONG",
            f"Scanning {date_from}..{date_to} at the resolution needed for "
            f"{'/'.join(sorted(moving))} exceeds the sampling budget.",
            hint="Shorten the date range.",
        )

    # --- Pass 1: locate every exact crossing in the range -------------------
    crossings: list[tuple[float, bool]] = []   # (jd, retrograde_at_exactness)
    prev_delta: float | None = None
    jd = jd_start
    # Scan one step beyond the end so a perfection sitting in the final partial
    # interval is still bracketed; crossings past jd_end are discarded below.
    scan_limit = jd_end + scan_step
    while jd <= scan_limit:
        lon1, lon2 = _lon_at(jd, pid1, pid2, natal_lon2)
        delta = aspect_delta(lon1, lon2, asp_angle)
        if prev_delta is not None and prev_delta * delta < 0 and abs(prev_delta - delta) < 270:
            ex_jd = find_exact_aspect_jd(
                pid1, pid2, asp_angle, jd - scan_step, jd, natal_lon2=natal_lon2
            )
            if ex_jd is not None and jd_start <= ex_jd <= jd_end:
                _, speed1 = calc_planet(ex_jd, pid1)
                crossings.append((ex_jd, speed1 < 0))
        prev_delta = delta
        jd += scan_step

    # --- Pass 2: group crossings belonging to one retrograde loop -----------
    group_window = _group_window_days(jd_start, pid1, pid2)
    groups: list[list[tuple[float, bool]]] = []
    for crossing in crossings:
        if groups and crossing[0] - groups[-1][-1][0] <= group_window:
            groups[-1].append(crossing)
        else:
            groups.append([crossing])

    occurrences: list[dict[str, Any]] = []
    for group in groups:
        first_jd = group[0][0]
        last_jd = group[-1][0]

        approach_jd = _orb_window(
            first_jd, -1, orb, pid1, pid2, natal_lon2, jd_start, asp_angle, scan_step
        )
        separation_jd = _orb_window(
            last_jd, +1, orb, pid1, pid2, natal_lon2, jd_end, asp_angle, scan_step
        )

        retro_dates = [jd_to_iso(j)[:10] for j, retro in group if retro]
        direct_dates = [jd_to_iso(j)[:10] for j, retro in group if not retro]

        occ: dict[str, Any] = {
            "approach_date": jd_to_iso(approach_jd)[:10],
            "exact_date": jd_to_iso(first_jd)[:10],
            "exact_dates": [jd_to_iso(j)[:10] for j, _ in group],
            "separation_date": jd_to_iso(separation_jd)[:10],
            "retrograde_exact": retro_dates or None,
            "direct_exact": direct_dates or None,
            "passes": len(group),
            "is_triple_pass": len(group) >= 3,
        }
        # Only meaningful when the bodies back away and return: every entry in
        # ``group`` is an exact perfection, so a "tightest orb" would always be
        # zero and tell the caller nothing.
        if len(group) > 1:
            occ["max_separation_orb"] = _max_separation(
                group, pid1, pid2, natal_lon2, asp_angle
            )
        occurrences.append(occ)

    return {
        "planet1": planet1,
        "planet2": planet2,
        "mode": mode_resolved,
        "aspect": aspect,
        "orb_used": orb,
        "occurrences": occurrences,
    }


def _orb_window(
    ex_jd: float,
    direction: int,
    orb: float,
    pid1: int,
    pid2: int | None,
    natal_lon2: float | None,
    limit_jd: float,
    asp_angle: float,
    step: float = DEFAULT_SCAN_STEP_DAYS,
) -> float:
    """First/last JD at which the aspect is still within ``orb`` of exact.

    ``step`` must match the scan resolution: at 1 degree orb the Moon is only
    in aspect for about three hours, which a half-day walk cannot resolve.
    """
    jd = ex_jd
    while (limit_jd - jd) * direction > 0:
        nxt = jd + direction * step
        lon1, lon2 = _lon_at(nxt, pid1, pid2, natal_lon2)
        if abs(aspect_delta(lon1, lon2, asp_angle)) > orb:
            break
        jd = nxt
    return jd


def _max_separation(
    group: list[tuple[float, bool]],
    pid1: int,
    pid2: int | None,
    natal_lon2: float | None,
    asp_angle: float,
) -> float:
    """Widest orb reached *between* consecutive perfections in one loop.

    Tells the caller how far the bodies pulled apart mid-retrograde before
    coming back for the next pass.
    """
    widest = 0.0
    for (jd_a, _), (jd_b, _) in pairwise(group):
        steps = 24
        for i in range(1, steps):
            jd = jd_a + (jd_b - jd_a) * i / steps
            lon1, lon2 = _lon_at(jd, pid1, pid2, natal_lon2)
            widest = max(widest, abs(aspect_delta(lon1, lon2, asp_angle)))
    return round(widest, 3)
