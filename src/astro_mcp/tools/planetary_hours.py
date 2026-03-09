"""Tool 10: get_planetary_hours."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from astro_mcp.core.ephemeris_provider import calc_rise_set, to_jd, jd_to_iso
from astro_mcp.core.geocoding import resolve_location
from astro_mcp.core.models import CHALDEAN_ORDER, WEEKDAY_TO_RULER


def _jd_to_local_time(jd: float, tz_str: str) -> str:
    """Convert JD to HH:MM local time string."""
    iso = jd_to_iso(jd)
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    local = dt.astimezone(ZoneInfo(tz_str))
    return local.strftime("%H:%M")


def get_planetary_hours(
    date: str,
    location: str | dict,
    tz_output: str | None = None,
) -> dict[str, Any]:
    """
    Tool 10: Calculate 24 planetary hours for a given day.
    Day hours = from sunrise to sunset (divided into 12 equal parts).
    Night hours = from sunset to next sunrise.
    """
    geo = resolve_location(location)
    tz = tz_output or geo.tz

    # Search from local midnight (00:00 local → UTC) so rise_trans always finds
    # today's sunrise and sunset regardless of the UTC offset.
    from zoneinfo import ZoneInfo as _ZI
    from datetime import datetime as _dt
    local_midnight = _dt.fromisoformat(f"{date}T00:00:00").replace(tzinfo=_ZI(tz))
    utc_midnight = local_midnight.astimezone(_ZI("UTC"))
    jd_start = to_jd(utc_midnight.strftime("%Y-%m-%dT%H:%M:%SZ"))

    jd_rise, jd_set = calc_rise_set(jd_start, geo.lat, geo.lon)

    # Weekday of the date (using local timezone)
    dt_local = datetime.fromisoformat(f"{date}T12:00:00").replace(tzinfo=ZoneInfo(tz))
    weekday = dt_local.weekday()  # Mon=0..Sun=6
    day_ruler = WEEKDAY_TO_RULER[weekday]

    # Starting planet for hour 1 of the day
    # Day ruler starts hour 1; subsequent hours follow Chaldean order
    start_idx = CHALDEAN_ORDER.index(day_ruler)

    # Day hours: 12 equal parts of day arc
    day_arc = (jd_set - jd_rise) / 12
    day_hours = []
    for i in range(12):
        planet = CHALDEAN_ORDER[(start_idx + i) % 7]
        h_start = jd_rise + i * day_arc
        h_end = jd_rise + (i + 1) * day_arc
        day_hours.append({
            "n": i + 1,
            "planet": planet,
            "start": _jd_to_local_time(h_start, tz),
            "end": _jd_to_local_time(h_end, tz),
        })

    # Next sunrise for night arc — search from sunset
    jd_rise_next, _ = calc_rise_set(jd_set + 0.01, geo.lat, geo.lon)
    night_arc = (jd_rise_next - jd_set) / 12
    # First night hour starts right after last day hour
    night_start_planet_idx = (start_idx + 12) % 7
    night_hours = []
    for i in range(12):
        planet = CHALDEAN_ORDER[(night_start_planet_idx + i) % 7]
        h_start = jd_set + i * night_arc
        h_end = jd_set + (i + 1) * night_arc
        night_hours.append({
            "n": i + 1,
            "planet": planet,
            "start": _jd_to_local_time(h_start, tz),
            "end": _jd_to_local_time(h_end, tz),
        })

    weekday_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    return {
        "date": date,
        "weekday": weekday_names[weekday],
        "day_ruler": day_ruler,
        "sunrise": _jd_to_local_time(jd_rise, tz),
        "sunset": _jd_to_local_time(jd_set, tz),
        "tz": tz,
        "day_hours": day_hours,
        "night_hours": night_hours,
    }
