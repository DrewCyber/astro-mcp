"""Cache entries are untrusted; provider failures must stay failures."""

import pytest
from geopy.exc import GeocoderTimedOut
from geopy.extra.rate_limiter import RateLimiter

from astro_mcp.core import geocoding as geo
from astro_mcp.core.errors import AstroError


@pytest.mark.parametrize("field,value", [("lat", "oops"), ("lat", 91), ("lat", float("nan")),
                                        ("lon", 181), ("tz", "bad/zone"), ("tz", None)])
def test_invalid_cached_locations_are_discarded(monkeypatch, field, value):
    entry = {"lat": 1.0, "lon": 2.0, "tz": "UTC", "name": "test"}
    entry[field] = value
    monkeypatch.setattr(geo, "_disk_cache", {"test": entry})
    assert geo._cache_get("test") is None


def test_timeout_through_actual_rate_limiter_is_not_not_found(monkeypatch):
    geo.clear_geocode_cache()
    monkeypatch.setattr(geo, "_cache_get", lambda key: None)
    limiter = geo._make_geocoder()
    assert isinstance(limiter, RateLimiter)
    def timeout(*args, **kwargs):
        raise GeocoderTimedOut("provider unavailable")
    limiter.func = timeout
    monkeypatch.setattr(geo, "_geocoder", limiter)
    with pytest.raises(AstroError, match="service unavailable"):
        geo.geocode("unique test city")
    geo.clear_geocode_cache()
