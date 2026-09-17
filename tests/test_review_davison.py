"""Davison houses use the midpoint latitude, not either natal fallback."""

from astro_mcp.tools.synastry import calculate_composite_chart


def test_polar_midpoint_resolves_house_system():
    result = calculate_composite_chart(
        person1_date="1990-01-01", person1_time="12:00",
        person1_location={"lat": 60, "lon": -80, "tz": "UTC"},
        person2_date="1991-01-01", person2_time="12:00",
        person2_location={"lat": 60, "lon": 80, "tz": "UTC"},
        method="davison", house_system="P",
    )
    assert result["davison_location"]["lat"] > 80
    assert result["house_basis"] == "W"
    assert result["house_system_warning"]
    assert len(result["comp_houses"]) == 12
