"""Tests for calculate_secondary_progressions."""

BIRTH = {"birth_date": "1990-03-15", "birth_time": "14:30",
          "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}}


def test_progressions_structure():
    from astro_mcp.tools.progressions import calculate_secondary_progressions
    result = calculate_secondary_progressions(**BIRTH, progression_date="2024-06-15")
    assert "prog_date" in result
    assert "prog_age" in result
    assert "prog_day" in result
    assert "prog_planets" in result
    assert "prog_to_natal_aspects" in result
    assert "prog_to_prog_aspects" in result


def test_progression_age_calculation():
    """Age should be approximately 34 for someone born 1990 progressed to 2024."""
    from astro_mcp.tools.progressions import calculate_secondary_progressions
    result = calculate_secondary_progressions(**BIRTH, progression_date="2024-03-15")
    assert abs(result["prog_age"] - 34.0) < 0.5


def test_progressions_includes_solar_arc():
    from astro_mcp.tools.progressions import calculate_secondary_progressions
    result = calculate_secondary_progressions(**BIRTH,
                                              progression_date="2024-06-15",
                                              include_solar_arc=True)
    assert "solar_arc" in result
    assert "arc_deg" in result["solar_arc"]


def test_progressions_prog_planets_have_sign():
    from astro_mcp.tools.progressions import calculate_secondary_progressions
    result = calculate_secondary_progressions(**BIRTH, progression_date="2024-06-15")
    for k, v in result["prog_planets"].items():
        assert "sign" in v or "lon" in v, f"Progressed planet {k} missing position data"
