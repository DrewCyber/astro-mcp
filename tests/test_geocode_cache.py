"""The geocode cache must survive a server restart without re-hitting the network."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from geopy.exc import GeocoderRateLimited

from astro_mcp.config import settings
from astro_mcp.core import geocoding
from astro_mcp.core.errors import AstroError


class _FakeGeocoder:
    """Stands in for the geocode callable and counts how often it is consulted."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, city: str, timeout: int = 10, **kwargs: Any) -> Any:
        self.calls += 1
        if kwargs.get("exactly_one") is False:
            return [
                SimpleNamespace(latitude=41.6, longitude=41.6, address="Batumi, Adjara, Georgia"),
                SimpleNamespace(latitude=41.5, longitude=41.5, address="Batumi Station, Georgia"),
            ]
        return SimpleNamespace(
            latitude=41.61689, longitude=41.607043, address="Batumi, Georgia"
        )


@pytest.fixture
def isolated_cache(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> _FakeGeocoder:
    fake = _FakeGeocoder()
    monkeypatch.setattr(settings, "geocode_cache_path", str(tmp_path / "geocode.json"))
    monkeypatch.setattr(geocoding, "_geocoder", fake)
    monkeypatch.setattr(geocoding, "_disk_cache", None)
    geocoding.clear_geocode_cache()
    return fake


def _restart_server() -> None:
    """Simulate a fresh process: both in-memory layers go away, the file stays."""
    geocoding.clear_geocode_cache()


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


# --- R-9 hardening -----------------------------------------------------------

def test_lru_is_keyed_on_normalized_name(isolated_cache: _FakeGeocoder) -> None:
    """'moscow' vs 'Moscow' must not be two LRU entries / two network calls."""
    geocoding.geocode("  Batumi,   GEORGIA ")
    geocoding.geocode("batumi, georgia")
    assert isolated_cache.calls == 1


class _NotFoundGeocoder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, city: str, timeout: int = 10, **kwargs: Any) -> Any:
        self.calls += 1
        return None


def _isolate(fake: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "geocode_cache_path", str(tmp_path / "geocode.json"))
    monkeypatch.setattr(geocoding, "_geocoder", fake)
    monkeypatch.setattr(geocoding, "_disk_cache", None)
    geocoding.clear_geocode_cache()


def test_failed_lookup_is_negatively_cached(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _NotFoundGeocoder()
    _isolate(fake, tmp_path, monkeypatch)

    for _ in range(3):
        with pytest.raises(AstroError) as exc:
            geocoding.geocode("Nowhereville")
        assert exc.value.code == "GEOCODE_FAILED"
    assert fake.calls == 1, "retries inside the TTL must not hit the provider"

    # TTL expiry lets it try again.
    with monkeypatch.context() as m:
        m.setattr(geocoding, "NEGATIVE_TTL_SECONDS", -1.0)
        with pytest.raises(AstroError):
            geocoding.geocode("Nowhereville")
    assert fake.calls == 2


def test_successful_lookup_clears_negative_memory(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FlakyThenFound:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, city: str, timeout: int = 10, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                return None
            return SimpleNamespace(
                latitude=41.61689, longitude=41.607043, address="Batumi, Georgia"
            )

    fake = FlakyThenFound()
    _isolate(fake, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "geocode_cache_path", "")  # disk layer off

    with pytest.raises(AstroError):
        geocoding.geocode("Batumi")
    with monkeypatch.context() as m:
        m.setattr(geocoding, "NEGATIVE_TTL_SECONDS", -1.0)
        assert geocoding.geocode("Batumi").tz == "Asia/Tbilisi"
    assert fake.calls == 2


def test_normalize_place_key():
    assert geocoding.normalize_place_key("  Ulm,   Germany ") == "ulm, germany"
    assert geocoding.normalize_place_key("ULM") == geocoding.normalize_place_key("ulm")


# --- 1.2.0 error clarity -----------------------------------------------------

def test_rate_limit_gets_its_own_message(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RateLimited:
        def __call__(self, city: str, timeout: int = 10, **kwargs: Any) -> Any:
            raise GeocoderRateLimited("HTTP 429")

    _isolate(RateLimited(), tmp_path, monkeypatch)
    with pytest.raises(AstroError) as exc:
        geocoding.geocode("Moscow")
    assert exc.value.code == "GEOCODE_FAILED"
    assert "rate-limited" in exc.value.message
    assert "lat" in exc.value.hint


def test_garbage_response_is_geocode_failed_not_input_error(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Garbage:
        def __call__(self, city: str, timeout: int = 10, **kwargs: Any) -> Any:
            raise ValueError("could not convert string to float: 'NaN-ish'")

    _isolate(Garbage(), tmp_path, monkeypatch)
    with pytest.raises(AstroError) as exc:
        geocoding.geocode("Moscow")
    assert exc.value.code == "GEOCODE_FAILED"
    assert "invalid response" in exc.value.message


def test_not_found_offers_fuzzy_suggestions(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Suggesting:
        def __init__(self) -> None:
            self.suggestion_calls = 0

        def __call__(self, city: str, timeout: int = 10, **kwargs: Any) -> Any:
            if kwargs.get("exactly_one") is False:
                self.suggestion_calls += 1
                return [
                    SimpleNamespace(latitude=54.6, longitude=87.2, address="Osinniki, Kemerovo, Russia"),
                    SimpleNamespace(latitude=54.7, longitude=87.1, address="Osinniki District, Russia"),
                ]
            return None  # the full query matches nothing

    fake = Suggesting()
    _isolate(fake, tmp_path, monkeypatch)
    with pytest.raises(AstroError) as exc:
        geocoding.geocode("Osinniki, Russia")
    assert exc.value.code == "GEOCODE_FAILED"
    assert fake.suggestion_calls == 1
    assert "Did you mean: Osinniki / Osinniki District" in exc.value.hint


def test_error_message_echoes_the_callers_spelling(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(_NotFoundGeocoder(), tmp_path, monkeypatch)
    with pytest.raises(AstroError) as exc:
        geocoding.geocode("  Osinniki, Russia ")
    assert "Osinniki, Russia" in exc.value.message
    assert "osinniki, russia" not in exc.value.message
