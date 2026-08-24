"""Tests for get_ephemeris and find_aspect_exact_dates."""

from datetime import date
from itertools import pairwise

import pytest

from astro_mcp.core.errors import AstroError


def test_ephemeris_basic():
    from astro_mcp.tools.ephemeris import get_ephemeris
    result = get_ephemeris(planet="Su", date_from="2024-01-01", date_to="2024-01-07", step="1d")
    assert "rows" in result
    assert len(result["rows"]) >= 7
    for row in result["rows"]:
        assert "lon" in row
        assert "deg" in row
        assert 0 <= row["deg"] < 360


def test_ephemeris_with_speed():
    from astro_mcp.tools.ephemeris import get_ephemeris
    result = get_ephemeris(planet="Mo", date_from="2024-03-01", date_to="2024-03-03",
                           step="1d", include_speed=True)
    for row in result["rows"]:
        assert "speed" in row


def test_ephemeris_unknown_planet():
    from astro_mcp.tools.ephemeris import get_ephemeris
    with pytest.raises(AstroError) as exc:
        get_ephemeris(planet="XX", date_from="2024-01-01", date_to="2024-01-07")
    assert exc.value.code == "UNKNOWN_PLANET"


def test_find_aspect_saturn_sun_conjunction_2024():
    """Saturn-Sun conjunction should occur around 2024-04-01."""
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates
    result = find_aspect_exact_dates(
        planet1="Sa", planet2="Su", aspect="Cnj",
        date_from="2024-01-01", date_to="2024-12-31",
    )
    assert "occurrences" in result
    # There may or may not be a conjunction in 2024 but structure must be correct
    for occ in result["occurrences"]:
        assert "exact_date" in occ
        assert "approach_date" in occ
        assert "separation_date" in occ


def test_find_aspect_unknown_aspect():
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates
    with pytest.raises(AstroError) as exc:
        find_aspect_exact_dates(
            planet1="Su", planet2="Mo", aspect="InvalidAsp",
            date_from="2024-01-01", date_to="2024-01-31",
        )
    assert exc.value.code == "UNKNOWN_ASPECT"


def test_find_aspect_new_moon_conjunction_detected():
    """Moon-Sun conjunction (new moon) should be found in Jan 2024 window."""
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    result = find_aspect_exact_dates(
        planet1="Mo",
        planet2="Su",
        aspect="Cnj",
        date_from="2024-01-05",
        date_to="2024-01-15",
        orb=2.0,
        mode="transit-to-transit",
    )
    assert "occurrences" in result
    assert len(result["occurrences"]) >= 1


# --- Regression: R-2 fabricated multi-pass grouping -----------------------
# Twelve lunations in 2026 are twelve INDEPENDENT conjunctions. The old
# 200-day grouping window merged all of them into one bogus "triple pass"
# claiming up to ~179 deg of mid-loop separation.

def test_lunations_are_not_grouped_into_a_triple_pass():
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    result = find_aspect_exact_dates(
        planet1="Mo", planet2="Su", aspect="Cnj",
        date_from="2026-01-01", date_to="2026-12-31",
        mode="transit-to-transit",
    )
    occs = result["occurrences"]
    assert len(occs) == 12
    for occ in occs:
        assert occ["is_triple_pass"] is False
        assert occ["passes"] == 1
        assert len(occ["exact_dates"]) == 1
        # max_separation_orb only makes sense between passes of one loop.
        assert "max_separation_orb" not in occ
    # Exact dates must be roughly one synodic month apart.
    dates = sorted(occ["exact_date"] for occ in occs)
    for a, b in pairwise(dates):
        gap = (date.fromisoformat(b) - date.fromisoformat(a)).days
        assert 24 <= gap <= 35, f"lunation gap {gap} days out of range"


def test_transit_to_natal_moon_hits_are_independent_occurrences():
    """Same defect class for transit-to-natal mode: monthly Moon hits over a
    natal point must not merge into one occurrence."""
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    result = find_aspect_exact_dates(
        planet1="Mo", planet2="Su", aspect="Cnj",
        date_from="2026-01-01", date_to="2026-06-30",
        birth_date="1990-06-15", birth_time="12:00",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
    )
    occs = result["occurrences"]
    assert len(occs) >= 5
    for occ in occs:
        assert occ["is_triple_pass"] is False


def test_find_aspect_mode_requires_natal_context():
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    with pytest.raises(AstroError) as exc:
        find_aspect_exact_dates(
            planet1="Sa",
            planet2="Su",
            aspect="Tri",
            date_from="2024-01-01",
            date_to="2024-12-31",
            mode="transit-to-natal",
        )
    assert exc.value.code == "INPUT_ERROR"


def test_ephemeris_multi_planet_and_custom_hour_step():
    from astro_mcp.tools.ephemeris import get_ephemeris

    result = get_ephemeris(
        planet=["Mo", "Su"],
        date_from="2024-03-01",
        date_to="2024-03-02",
        step="3h",
        output_tz="UTC",
    )
    assert "rows_by_planet" in result
    assert "Mo" in result["rows_by_planet"]
    assert "Su" in result["rows_by_planet"]
    assert len(result["rows_by_planet"]["Mo"]) >= 8
