"""Tests for ephemeris coverage detection (R-5).

The .se1 files cover 1800-2400. A query outside that span used to be
misreported as "the .se1 data files are missing", sending users to
re-download files they already had.
"""

import pytest

from astro_mcp.core.errors import AstroError


def test_coverage_detected_from_installed_files():
    from astro_mcp.core.ephemeris_provider import ephemeris_covered_years

    covered = ephemeris_covered_years()
    assert covered is not None
    lo, hi = covered
    assert lo <= 1800 <= hi


def test_out_of_range_date_raises_range_error_not_missing_files():
    from astro_mcp.core.ephemeris_provider import (
        calc_planet,
        ephemeris_covered_years,
        to_jd,
    )

    jd = to_jd("2500-06-15T12:00:00Z")
    with pytest.raises(AstroError) as exc:
        calc_planet(jd, 0)  # Sun
    assert exc.value.code == "EPHEMERIS_OUT_OF_RANGE"
    message = f"{exc.value.message} {exc.value.hint or ''}"
    # Must name the actual covered span instead of blaming missing files.
    lo, hi = ephemeris_covered_years() or (1800, 2399)
    assert f"{lo}-{hi}" in message
    assert "download_ephe.sh" in message  # points at extended-range files


def test_in_range_date_does_not_raise():
    from astro_mcp.core.ephemeris_provider import calc_planet, to_jd

    lon, speed = calc_planet(to_jd("2026-01-01T00:00:00Z"), 0)
    assert 0 <= lon < 360


def test_solar_return_schema_bounds_year_to_coverage():
    from pydantic import ValidationError

    from astro_mcp.schemas import SolarReturnInput

    with pytest.raises(ValidationError):
        SolarReturnInput(
            birth_date="1990-06-15", birth_time="12:00",
            birth_location={"lat": 55.75, "lon": 37.62}, year=2500,
        )
    with pytest.raises(ValidationError):
        SolarReturnInput(
            birth_date="1990-06-15", birth_time="12:00",
            birth_location={"lat": 55.75, "lon": 37.62}, year=1700,
        )
    ok = SolarReturnInput(
        birth_date="1990-06-15", birth_time="12:00",
        birth_location={"lat": 55.75, "lon": 37.62}, year=2026,
    )
    assert ok.year == 2026
