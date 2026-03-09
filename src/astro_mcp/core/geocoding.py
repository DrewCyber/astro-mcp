"""Geocoding and timezone resolution."""

from __future__ import annotations

import functools
import logging
from zoneinfo import ZoneInfo

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from timezonefinder import TimezoneFinder

from astro_mcp.config import settings
from astro_mcp.core.models import GeoLocation

logger = logging.getLogger(__name__)

_tf = TimezoneFinder()


def _make_geocoder():
    if settings.geocoding_provider == "opencage" and settings.opencage_api_key:
        from geopy.geocoders import OpenCage
        return OpenCage(api_key=settings.opencage_api_key)
    return Nominatim(user_agent=settings.geocoding_user_agent)


_geocoder = _make_geocoder()


@functools.lru_cache(maxsize=settings.geocode_cache_size)
def geocode(city: str) -> GeoLocation:
    """Geocode a city string to (lat, lon, tz, name). Uses LRU cache."""
    try:
        location = _geocoder.geocode(city, timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        raise ValueError(f"GEOCODE_FAILED: {exc}") from exc
    if location is None:
        raise ValueError(
            f"GEOCODE_FAILED: City '{city}' not found. "
            "Please provide full city name or coordinates."
        )
    tz = _tf.timezone_at(lat=location.latitude, lng=location.longitude)
    if tz is None:
        raise ValueError(
            f"TIMEZONE_UNKNOWN: Cannot determine timezone for '{city}'. "
            "Please provide tz explicitly."
        )
    return GeoLocation(
        lat=round(location.latitude, 6),
        lon=round(location.longitude, 6),
        tz=tz,
        name=location.address.split(",")[0].strip(),
    )


def resolve_location(location: str | dict) -> GeoLocation:
    """
    Resolve a location which is either a city string or {'lat', 'lon', 'tz'} dict.
    """
    if isinstance(location, str):
        return geocode(location)
    lat = float(location["lat"])
    lon = float(location["lon"])
    tz_str: str | None = location.get("tz")
    if tz_str is None:
        tz_str = _tf.timezone_at(lat=lat, lng=lon)
    if tz_str is None:
        raise ValueError("TIMEZONE_UNKNOWN: provide tz in location object.")
    return GeoLocation(lat=lat, lon=lon, tz=tz_str)


def local_to_utc(
    date_str: str,
    time_str: str,
    tz_str: str,
) -> tuple[str, str | None]:
    """Convert local date+time to (UTC ISO-8601 string, dst_warning).

    ``datetime.replace(tzinfo=...)`` always uses ``fold=0``, which silently
    chooses the DST (summer) interpretation when a local time is ambiguous
    during a fall-back transition.  This function detects both DST edge cases
    and resolves them predictably:

    * **Normal time** – unique mapping; returns ``(utc_str, None)``.
    * **Fall-back fold** – the same clock time occurs twice (once in summer
      time, once in standard time).  ``fold=0`` (summer/DST) is the default
      behaviour, but standard time is the safer assumption for birth records
      because the transition typically happens in the small hours.  We pick
      ``fold=1`` (standard/winter time, second occurrence) and set
      ``dst_warning = "fall_back_fold"``.
    * **Spring-forward gap** – the clock time does not exist (skipped).  We
      keep ``fold=0`` (pre-transition offset, the conventional interpretation)
      and set ``dst_warning = "spring_forward_gap"``.

    Callers should propagate ``dst_warning`` to the output so users know their
    input time fell in a DST transition window.

    Args:
        date_str: ``'YYYY-MM-DD'``
        time_str: ``'HH:MM'`` or ``'HH:MM:SS'``
        tz_str:   IANA timezone string, e.g. ``'Europe/Moscow'``

    Returns:
        ``(utc_iso_string, dst_warning_or_None)``
    """
    from datetime import datetime

    fmt = "%Y-%m-%d %H:%M:%S" if time_str.count(":") == 2 else "%Y-%m-%d %H:%M"
    naive_dt = datetime.strptime(f"{date_str} {time_str}", fmt)
    tz = ZoneInfo(tz_str)
    utc_zone = ZoneInfo("UTC")

    # Resolve both possible folds
    aware_f0 = naive_dt.replace(tzinfo=tz, fold=0)
    aware_f1 = naive_dt.replace(tzinfo=tz, fold=1)
    utc_f0 = aware_f0.astimezone(utc_zone)
    utc_f1 = aware_f1.astimezone(utc_zone)

    if utc_f0 == utc_f1:
        # Unambiguous time — no DST edge case
        return utc_f0.strftime("%Y-%m-%dT%H:%M:%SZ"), None

    # The two folds yield different UTC moments → edge case.
    # Determine which kind by round-tripping each UTC back to local time.
    rt_f0 = utc_f0.astimezone(tz).replace(tzinfo=None)
    rt_f1 = utc_f1.astimezone(tz).replace(tzinfo=None)

    both_valid = (rt_f0 == naive_dt) and (rt_f1 == naive_dt)

    if both_valid:
        # Fall-back fold: the local time exists twice.
        # Default to fold=1 (standard/winter time, second occurrence) — the
        # post-transition clock reading, which is the more common record for
        # births written after the clock has been set back.
        return utc_f1.strftime("%Y-%m-%dT%H:%M:%SZ"), "fall_back_fold"

    # Spring-forward gap: the local time does not exist at all.
    # Keep fold=0 (pre-transition offset) — the conventional interpretation.
    return utc_f0.strftime("%Y-%m-%dT%H:%M:%SZ"), "spring_forward_gap"
