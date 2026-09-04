"""Geocoding and timezone resolution."""

from __future__ import annotations

import functools
import json
import logging
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from geopy.exc import GeocoderRateLimited, GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from astro_mcp.config import settings
from astro_mcp.core.errors import AstroError
from astro_mcp.core.models import GeoLocation

logger = logging.getLogger(__name__)

_tf = TimezoneFinder()


def _make_geocoder() -> Any:
    """Uniform geocode callable: ``(query, timeout=..., **kwargs) -> Location | None``."""
    if settings.geocoding_provider == "opencage":
        if settings.opencage_api_key:
            from geopy.geocoders import OpenCage
            return OpenCage(api_key=settings.opencage_api_key).geocode
        # A misconfigured deployment must not run on the wrong service
        # indefinitely without a trace.
        logger.warning(
            "GEOCODING_PROVIDER=opencage but OPENCAGE_API_KEY is empty; "
            "falling back to Nominatim."
        )
    from geopy.extra.rate_limiter import RateLimiter

    # Nominatim's usage policy caps anonymous traffic at 1 request/second;
    # bursty MCP clients otherwise risk 403 blocks of the shared user agent.
    # The limiter must wrap the *bound* .geocode method (the documented geopy
    # pattern): wrapping the geolocator object leaves the limiter without a
    # .geocode attribute, and every string lookup then died as an opaque
    # INTERNAL_ERROR.
    return RateLimiter(
        Nominatim(user_agent=settings.geocoding_user_agent).geocode,
        min_delay_seconds=1.0,
        max_retries=0,
    )


_geocoder = _make_geocoder()

# ---------------------------------------------------------------------------
# Persistent geocode cache
# ---------------------------------------------------------------------------
# The LRU below only lives as long as the process, and an MCP server is
# restarted every time the editor restarts. Without a disk layer the same
# handful of cities is re-fetched from Nominatim at the start of every session,
# putting a network round-trip in front of the first chart. Only public
# geographic data is stored: the city string and its coordinates, never dates
# or times. Set GEOCODE_CACHE_PATH="" to disable.

_cache_lock = threading.Lock()
_disk_cache: dict[str, dict[str, Any]] | None = None


def _cache_path() -> Path | None:
    raw = settings.geocode_cache_path.strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _load_disk_cache() -> dict[str, dict[str, Any]]:
    global _disk_cache
    if _disk_cache is not None:
        return _disk_cache
    path = _cache_path()
    _disk_cache = {}
    if path is not None and path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                _disk_cache = {k: v for k, v in loaded.items() if isinstance(v, dict)}
        except (OSError, ValueError) as exc:
            # A corrupt or unreadable cache must never break a lookup.
            logger.warning("Ignoring unreadable geocode cache at %s: %s", path, exc)
    return _disk_cache


def _cache_get(key: str) -> GeoLocation | None:
    with _cache_lock:
        entry = _load_disk_cache().get(key)
    if entry is None:
        return None
    try:
        return GeoLocation(**entry)
    except (TypeError, ValueError):
        return None


def _cache_put(key: str, geo: GeoLocation) -> None:
    path = _cache_path()
    if path is None:
        return
    with _cache_lock:
        cache = _load_disk_cache()
        cache[key] = {"lat": geo.lat, "lon": geo.lon, "tz": geo.tz, "name": geo.name}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-replace so an interrupted write cannot truncate the
            # existing cache.
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(cache), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.warning("Could not write geocode cache to %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Negative cache
# ---------------------------------------------------------------------------
# A city that just failed lookup will fail again on immediate retry; without a
# short-TTL memory every retry goes back out to the (rate-limited) provider
# and can wedge a session. Failures are remembered only briefly so transient
# outages self-heal.

NEGATIVE_TTL_SECONDS = 300.0

_negative_lock = threading.Lock()
_negative_failures: dict[str, float] = {}


def _negative_hit(key: str) -> bool:
    now = time.monotonic()
    with _negative_lock:
        failed_at = _negative_failures.get(key)
        if failed_at is None:
            return False
        if now - failed_at >= NEGATIVE_TTL_SECONDS:
            del _negative_failures[key]
            return False
        return True


def _negative_record(key: str) -> None:
    with _negative_lock:
        _negative_failures[key] = time.monotonic()


def _ascii_fold(text: str) -> str:
    """Best-effort transliteration: 'Köln' -> 'Koln'."""
    return " ".join(
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().split()
    )


def _suggest_similar(key: str) -> list[str]:
    """Nearest matches for a query that returned nothing, best-effort.

    Retries once with the leading comma-segment, ASCII-folded: "Osinniki,
    Russia" becomes "Osinniki", "Köln, Deutschland" becomes "Koln".
    Suggestions are surfaced in the error hint and never auto-accepted — for
    a birth chart a confidently wrong city is worse than a clear failure.
    """
    simplified = _ascii_fold(key.split(",")[0])
    if not simplified or simplified == key:
        return []
    try:
        candidates = _geocoder(simplified, timeout=10, exactly_one=False, limit=3)
    except Exception:  # noqa: BLE001 - suggestions must never mask the real error
        return []
    names: list[str] = []
    for cand in candidates or []:
        name = (getattr(cand, "address", "") or "").split(",")[0].strip()
        if name and name not in names:
            names.append(name)
    return names[:3]


@functools.lru_cache(maxsize=settings.geocode_cache_size)
def _geocode_lru(key: str) -> GeoLocation:
    """Network-backed geocode for an already-normalized key.

    The LRU is keyed on the *normalized* string: caching on raw input made
    'moscow' and 'Moscow' two separate entries and two network round-trips.
    """
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if _negative_hit(key):
        raise AstroError(
            "GEOCODE_FAILED",
            f"City '{key}' not found (recently looked up).",
            hint="Correct the name, or pass explicit {lat, lon, tz} coordinates.",
        )
    try:
        location = _geocoder(key, timeout=10)
    except GeocoderRateLimited as exc:
        raise AstroError(
            "GEOCODE_FAILED",
            f"Geocoding provider is rate-limited while looking up '{key}'.",
            hint="Retry in a minute, or pass explicit {lat, lon, tz} coordinates.",
        ) from exc
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        raise AstroError(
            "GEOCODE_FAILED",
            f"Geocoding service unavailable while looking up '{key}'.",
            hint="Retry, or pass explicit {lat, lon, tz} coordinates instead.",
        ) from exc
    except ValueError as exc:
        # geopy parses result coordinates with float(); a 200-response
        # carrying garbage numbers raises a bare ValueError that used to
        # escape as INPUT_ERROR — a misleading code for input that was fine.
        raise AstroError(
            "GEOCODE_FAILED",
            f"Geocoding server returned an invalid response for '{key}'.",
            hint="Retry later, or pass explicit {lat, lon, tz} coordinates.",
        ) from exc
    if location is None:
        suggestions = _suggest_similar(key)
        _negative_record(key)
        hint = "Provide the full city name (e.g. 'Ulm, Germany') or coordinates."
        if suggestions:
            hint = (
                f"Did you mean: {' / '.join(suggestions)}? "
                "Otherwise pass explicit {lat, lon, tz} coordinates."
            )
        raise AstroError(
            "GEOCODE_FAILED",
            f"City '{key}' not found.",
            hint=hint,
        )
    tz = _tf.timezone_at(lat=location.latitude, lng=location.longitude)
    if tz is None:
        raise AstroError(
            "TIMEZONE_UNKNOWN",
            f"Cannot determine the timezone for '{key}'.",
            hint="Pass tz explicitly in the location object.",
        )
    geo = GeoLocation(
        lat=round(location.latitude, 6),
        lon=round(location.longitude, 6),
        tz=tz,
        name=location.address.split(",")[0].strip(),
    )
    _cache_put(key, geo)
    return geo


def normalize_place_key(city: str) -> str:
    """Canonical cache/LRU key for a place string."""
    return " ".join(city.split()).casefold()


def geocode(city: str) -> GeoLocation:
    """Geocode a city string to (lat, lon, tz, name).

    Backed by an in-process LRU keyed on the normalized name and, unless
    disabled, a small JSON file so lookups survive server restarts. Failed
    lookups are negatively-cached for :data:`NEGATIVE_TTL_SECONDS`.
    """
    key = normalize_place_key(city)
    try:
        return _geocode_lru(key)
    except AstroError as exc:
        # Messages are built inside the LRU on the normalized key; the caller
        # should see the string they actually typed.
        if city != key and key in exc.message:
            exc.message = exc.message.replace(key, city)
        raise


def clear_geocode_cache() -> None:
    """Drop all in-memory lookup state (LRU and negative cache)."""
    _geocode_lru.cache_clear()
    with _negative_lock:
        _negative_failures.clear()


def resolve_location(location: str | dict[str, Any]) -> GeoLocation:
    """
    Resolve a location which is either a city string or {'lat', 'lon', 'tz'} dict.
    """
    if isinstance(location, str):
        return geocode(location)
    if not isinstance(location, dict):
        raise AstroError(
            "INPUT_ERROR",
            "location must be a city name or an object with lat/lon.",
        )
    try:
        lat = float(location["lat"])
        lon = float(location["lon"])
    except KeyError as exc:
        raise AstroError(
            "INVALID_COORDINATES",
            "location object requires both 'lat' and 'lon'.",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise AstroError(
            "INVALID_COORDINATES",
            "location 'lat' and 'lon' must be numbers.",
        ) from exc

    # Guard the ranges here: out-of-range values otherwise reach swe.houses,
    # which fails with an opaque generic error far from the actual cause.
    if not -90.0 <= lat <= 90.0:
        raise AstroError("INVALID_COORDINATES", f"Latitude {lat} is outside [-90, 90].")
    if not -180.0 <= lon <= 180.0:
        raise AstroError("INVALID_COORDINATES", f"Longitude {lon} is outside [-180, 180].")

    tz_str: str | None = location.get("tz")
    if tz_str is None:
        tz_str = _tf.timezone_at(lat=lat, lng=lon)
    if tz_str is None:
        raise AstroError(
            "TIMEZONE_UNKNOWN",
            f"Cannot determine the timezone for lat={lat}, lon={lon}.",
            hint="Pass tz explicitly in the location object.",
        )
    try:
        ZoneInfo(tz_str)
    except Exception as exc:
        raise AstroError(
            "TIMEZONE_UNKNOWN",
            f"'{tz_str}' is not a valid IANA timezone.",
            hint="Use a name such as 'Europe/Berlin'.",
        ) from exc
    return GeoLocation(lat=lat, lon=lon, tz=tz_str, name=str(location.get("name", "")))


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
    fmt = "%Y-%m-%d %H:%M:%S" if time_str.count(":") == 2 else "%Y-%m-%d %H:%M"
    try:
        naive_dt = datetime.strptime(f"{date_str} {time_str}", fmt)
    except ValueError as exc:
        raise AstroError(
            "INVALID_TIME",
            f"Could not parse date '{date_str}' with time '{time_str}'.",
            hint="Expected date as YYYY-MM-DD and time as HH:MM or HH:MM:SS.",
        ) from exc
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
