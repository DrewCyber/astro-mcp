"""Cache failures retain their category and process writes merge safely."""

import json
from concurrent.futures import ProcessPoolExecutor

import pytest
from geopy.exc import GeocoderTimedOut

from astro_mcp.core import geocoding
from astro_mcp.core.errors import AstroError
from astro_mcp.core.models import GeoLocation


def _write_location(path, key):
    from astro_mcp.core import geocoding as geo
    geo.settings.geocode_cache_path = path
    geo._disk_cache = {}
    geo._cache_put(key, GeoLocation(1, 2, "UTC", key))


def test_process_writers_preserve_both_entries(tmp_path):
    path = str(tmp_path / "cache.json")
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_write_location, path, str(i)) for i in range(4)]
        for future in futures:
            future.result()
    assert set(json.loads((tmp_path / "cache.json").read_text())) == {"0", "1", "2", "3"}


def test_timeout_is_cached_as_timeout_not_city_missing(monkeypatch):
    geocoding.clear_geocode_cache()
    monkeypatch.setattr(geocoding, "_cache_get", lambda key: None)
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise GeocoderTimedOut("offline")
    monkeypatch.setattr(geocoding, "_geocoder", fail)
    try:
        for name in ("Test Place", "test place"):
            with pytest.raises(AstroError, match="service unavailable"):
                geocoding.geocode(name)
        assert len(calls) == 1
    finally:
        geocoding.clear_geocode_cache()


def test_negative_cache_is_bounded_and_expires_globally(monkeypatch):
    geocoding.clear_geocode_cache()
    monkeypatch.setattr(geocoding, "NEGATIVE_CACHE_MAXSIZE", 3)
    monkeypatch.setattr(geocoding.time, "monotonic", lambda: 1.0)
    try:
        for i in range(10):
            geocoding._negative_record(str(i), AstroError("TIMEZONE_UNKNOWN", "timezone"))
        assert len(geocoding._negative_failures) == 3
        assert geocoding._negative_hit("9").code == "TIMEZONE_UNKNOWN"
        monkeypatch.setattr(geocoding.time, "monotonic", lambda: 302.0)
        assert geocoding._negative_hit("unrelated") is None
        assert not geocoding._negative_failures
    finally:
        geocoding.clear_geocode_cache()
