"""The geocode cache must survive a server restart without re-hitting the network."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from astro_mcp.config import settings
from astro_mcp.core import geocoding


class _FakeGeocoder:
    """Stands in for Nominatim and counts how often it is consulted."""

    def __init__(self) -> None:
        self.calls = 0

    def geocode(self, city: str, timeout: int = 10) -> Any:
        self.calls += 1
        return SimpleNamespace(
            latitude=41.61689, longitude=41.607043, address="Batumi, Georgia"
        )


@pytest.fixture
def isolated_cache(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> _FakeGeocoder:
    fake = _FakeGeocoder()
    monkeypatch.setattr(settings, "geocode_cache_path", str(tmp_path / "geocode.json"))
    monkeypatch.setattr(geocoding, "_geocoder", fake)
    monkeypatch.setattr(geocoding, "_disk_cache", None)
    geocoding.geocode.cache_clear()
    return fake


def _restart_server() -> None:
    """Simulate a fresh process: both in-memory layers go away, the file stays."""
    geocoding.geocode.cache_clear()
    geocoding._disk_cache = None


def test_lookup_is_cached_across_a_restart(isolated_cache: _FakeGeocoder) -> None:
    first = geocoding.geocode("Batumi, Georgia")
    assert isolated_cache.calls == 1

    _restart_server()

    second = geocoding.geocode("Batumi, Georgia")
    assert isolated_cache.calls == 1, "restart should not re-hit the geocoder"
    assert (second.lat, second.lon, second.tz) == (first.lat, first.lon, first.tz)


def test_cache_key_ignores_case_and_padding(isolated_cache: _FakeGeocoder) -> None:
    geocoding.geocode("Batumi, Georgia")
    _restart_server()
    geocoding.geocode("  batumi, GEORGIA  ")
    assert isolated_cache.calls == 1


def test_a_corrupt_cache_file_is_ignored(
    isolated_cache: _FakeGeocoder, tmp_path: Any
) -> None:
    (tmp_path / "geocode.json").write_text("{not json", encoding="utf-8")
    _restart_server()
    geo = geocoding.geocode("Batumi, Georgia")
    assert geo.tz == "Asia/Tbilisi"


def test_cache_can_be_disabled(
    isolated_cache: _FakeGeocoder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "geocode_cache_path", "")
    _restart_server()
    geocoding.geocode("Batumi, Georgia")
    _restart_server()
    geocoding.geocode("Batumi, Georgia")
    assert isolated_cache.calls == 2


def test_nothing_but_public_geography_is_written(
    isolated_cache: _FakeGeocoder, tmp_path: Any
) -> None:
    """Guards the promise that no birth date or time reaches the disk."""
    import json

    geocoding.geocode("Batumi, Georgia")
    stored = json.loads((tmp_path / "geocode.json").read_text(encoding="utf-8"))
    assert list(stored) == ["batumi, georgia"]
    assert set(stored["batumi, georgia"]) == {"lat", "lon", "tz", "name"}
