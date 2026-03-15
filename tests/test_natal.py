"""Tests for calculate_natal_chart."""

import pytest


def test_natal_structure(modern_natal):
    """Natal chart should have meta, planets, angles, houses, aspects."""
    chart = modern_natal
    assert "meta" in chart
    assert "planets" in chart
    assert "angles" in chart
    assert "houses" in chart
    assert "aspects" in chart


def test_ten_planets_present(modern_natal):
    """All 10 main planets must be present."""
    required = {"Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa", "Ur", "Ne", "Pl"}
    assert required.issubset(set(modern_natal["planets"].keys()))


def test_four_angles(modern_natal):
    """Asc, MC, Dsc, IC must be present."""
    assert set(modern_natal["angles"].keys()) == {"Asc", "MC", "Dsc", "IC"}


def test_twelve_houses(modern_natal):
    """Exactly 12 houses."""
    assert len(modern_natal["houses"]) == 12


def test_meta_fields(modern_natal):
    meta = modern_natal["meta"]
    assert "dt" in meta
    assert "loc" in meta
    assert "hs" in meta
    assert "jd" in meta
    assert meta["hs"] == "P"


def test_planet_sign_field(modern_natal):
    for pcode, pdata in modern_natal["planets"].items():
        assert "sign" in pdata, f"Planet {pcode} missing 'sign'"
        assert "deg" in pdata, f"Planet {pcode} missing 'deg'"
        assert 0 <= pdata["deg"] < 360, f"Planet {pcode} deg out of range"


def test_aspects_sorted_by_orb(modern_natal):
    orbs = [a["orb"] for a in modern_natal["aspects"]]
    assert orbs == sorted(orbs), "Aspects should be sorted by orb (ascending)"


def test_no_duplicate_aspects(modern_natal):
    seen = set()
    for asp in modern_natal["aspects"]:
        key = frozenset([asp["p1"], asp["p2"]])
        assert key not in seen, f"Duplicate aspect: {asp}"
        seen.add(key)


def test_einstein_sun_pisces(einstein_natal):
    """Einstein's Sun should be in Pisces."""
    assert einstein_natal["planets"]["Su"]["sign"] == "Pis"


def test_einstein_asc_cancer(einstein_natal):
    """Einstein's Ascendant should be in Cancer."""
    assert einstein_natal["angles"]["Asc"]["sign"] == "Can"


def test_whole_sign_system():
    from astro_mcp.tools.natal import calculate_natal_chart
    chart = calculate_natal_chart(
        birth_date="1990-03-15", birth_time="14:30",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
        house_system="W",
    )
    assert chart["meta"]["hs"] == "W"
    assert len(chart["houses"]) == 12


def test_polar_location_switches_to_whole_sign():
    """Placidus fails above 66.5° — should auto-switch to Whole Sign."""
    from astro_mcp.tools.natal import calculate_natal_chart
    chart = calculate_natal_chart(
        birth_date="1990-06-15", birth_time="12:00",
        birth_location={"lat": 70.0, "lon": 25.0, "tz": "Europe/Oslo"},
        house_system="P",
    )
    # Should have switched to W
    assert chart["meta"]["hs"] == "W"
