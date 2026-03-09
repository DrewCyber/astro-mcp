"""Tests for calculate_transits."""

import pytest

BIRTH = {"birth_date": "1990-03-15", "birth_time": "14:30",
          "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}}


def test_transits_basic_structure():
    from astro_mcp.tools.transits import calculate_transits
    result = calculate_transits(**BIRTH, transit_date="2024-06-15")
    assert "date" in result
    assert "transit_planets" in result
    assert "aspects" in result


def test_transit_planets_present():
    from astro_mcp.tools.transits import calculate_transits
    result = calculate_transits(**BIRTH, transit_date="2024-06-15")
    # At least the main planets should be present
    assert "Su" in result["transit_planets"]
    assert "Mo" in result["transit_planets"]


def test_transit_aspects_have_required_fields():
    from astro_mcp.tools.transits import calculate_transits
    result = calculate_transits(**BIRTH, transit_date="2024-06-15")
    for asp in result["aspects"]:
        assert "tp" in asp
        assert "np" in asp
        assert "asp" in asp
        assert "orb" in asp


def test_transit_fast_planets_only():
    from astro_mcp.tools.transits import calculate_transits
    result = calculate_transits(**BIRTH, transit_date="2024-06-15",
                                fast_planets_only=True)
    planets = set(result["transit_planets"].keys())
    slow_planets = {"Ju", "Sa", "Ur", "Ne", "Pl"}
    assert not planets.intersection(slow_planets), "Slow planets should not appear with fast_planets_only=True"
