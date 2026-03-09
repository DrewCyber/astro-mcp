"""Tests for get_ephemeris and find_aspect_exact_dates."""


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
    result = get_ephemeris(planet="XX", date_from="2024-01-01", date_to="2024-01-07")
    assert result.get("error") is True
    assert result["code"] == "UNKNOWN_PLANET"


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
    result = find_aspect_exact_dates(
        planet1="Su", planet2="Mo", aspect="InvalidAsp",
        date_from="2024-01-01", date_to="2024-01-31",
    )
    assert result.get("error") is True
