"""Tests for calculate_synastry and calculate_composite_chart."""

import pytest

PERSON1 = {"birth_date": "1990-03-15", "birth_time": "14:30",
           "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}}
PERSON2 = {"birth_date": "1988-07-22", "birth_time": "09:00",
           "birth_location": {"lat": 59.93, "lon": 30.32, "tz": "Europe/Moscow"}}


def test_synastry_structure():
    from astro_mcp.tools.synastry import calculate_synastry
    result = calculate_synastry(
        person1_date=PERSON1["birth_date"],
        person1_time=PERSON1["birth_time"],
        person1_location=PERSON1["birth_location"],
        person2_date=PERSON2["birth_date"],
        person2_time=PERSON2["birth_time"],
        person2_location=PERSON2["birth_location"],
    )
    assert "aspects" in result
    assert "house_overlays" in result
    assert "compatibility_indicators" in result
    assert "davison_dt" in result


def test_synastry_aspects_are_list():
    from astro_mcp.tools.synastry import calculate_synastry
    result = calculate_synastry(
        person1_date=PERSON1["birth_date"], person1_time=PERSON1["birth_time"],
        person1_location=PERSON1["birth_location"],
        person2_date=PERSON2["birth_date"], person2_time=PERSON2["birth_time"],
        person2_location=PERSON2["birth_location"],
    )
    assert isinstance(result["aspects"], list)


def test_composite_midpoint_structure():
    from astro_mcp.tools.synastry import calculate_composite_chart
    result = calculate_composite_chart(
        person1_date=PERSON1["birth_date"], person1_time=PERSON1["birth_time"],
        person1_location=PERSON1["birth_location"],
        person2_date=PERSON2["birth_date"], person2_time=PERSON2["birth_time"],
        person2_location=PERSON2["birth_location"],
        method="midpoint",
    )
    assert result["method"] == "midpoint"
    assert "comp_planets" in result
    assert "comp_aspects" in result
    assert "comp_houses" in result


def test_composite_davison_structure():
    from astro_mcp.tools.synastry import calculate_composite_chart
    result = calculate_composite_chart(
        person1_date=PERSON1["birth_date"], person1_time=PERSON1["birth_time"],
        person1_location=PERSON1["birth_location"],
        person2_date=PERSON2["birth_date"], person2_time=PERSON2["birth_time"],
        person2_location=PERSON2["birth_location"],
        method="davison",
    )
    assert result["method"] == "davison"
    assert "Su" in result["comp_planets"]
