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
