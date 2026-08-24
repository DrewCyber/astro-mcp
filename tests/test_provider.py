"""Tests for core/ephemeris_provider helpers."""

import pytest

from astro_mcp.core.errors import AstroError


def test_house_of_places_longitude_in_expected_house():
    from astro_mcp.core.ephemeris_provider import house_of

    # Equal houses from 0° Aries: anything in [30, 60) is house 2.
    cusps = [float(30 * i) for i in range(12)]
    assert house_of(45.0, cusps) == 2
    assert house_of(0.0, cusps) == 1
    assert house_of(359.9, cusps) == 12


def test_house_of_rejects_malformed_cusp_lists():
    """R-17 regression: short cusp lists used to silently yield house 1."""
    from astro_mcp.core.ephemeris_provider import house_of

    for bad in ([], [100.0] * 6):
        with pytest.raises(AstroError) as exc:
            house_of(10.0, bad)
        assert exc.value.code == "HOUSE_CALC_FAILED"


# --- Property: house_of partitions the zodiac -------------------------------

def _reference_house(lon: float, cusps: list[float]) -> int:
    """Independent sector walk used as an oracle."""
    lon %= 360.0
    for i in range(12):
        start = cusps[i] % 360.0
        end = cusps[(i + 1) % 12] % 360.0
        if end > start:
            if start <= lon < end:
                return i + 1
        elif lon >= start or lon < end:
            return i + 1
    raise AssertionError("oracle failed to place longitude")  # pragma: no cover


def test_house_of_partitions_the_zodiac_for_arbitrary_cusp_sets():
    """For any well-formed cusp set (12 strictly-increasing cusps), every
    longitude maps to exactly one house, cusp starts are inclusive, and the
    result agrees with an independent sector walk."""
    import random

    from astro_mcp.core.ephemeris_provider import house_of

    rng = random.Random(20260824)  # seeded: reproducible failures
    for trial in range(50):
        # Random rotation + random gaps; normalize to strictly increasing.
        base = rng.uniform(0.0, 360.0)
        gaps = [rng.uniform(5.0, 55.0) for _ in range(12)]
        scale = 360.0 / sum(gaps)
        cusps = []
        acc = base
        for gap in gaps:
            cusps.append(acc % 360.0)
            acc += gap * scale

        for _ in range(200):
            lon = rng.uniform(0.0, 360.0)
            h = house_of(lon, cusps)
            assert h == _reference_house(lon, cusps)
            assert 1 <= h <= 12

        # Cusp longitudes themselves land on their own house (start-inclusive).
        for i, cusp_lon in enumerate(cusps):
            assert house_of(cusp_lon, cusps) == i + 1
