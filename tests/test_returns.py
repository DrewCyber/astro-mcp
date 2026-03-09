"""Tests for calculate_solar_return and calculate_lunar_return."""

BIRTH = {"birth_date": "1990-03-15", "birth_time": "14:30",
          "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}}
NATAL_SUN_DEG = 354.75   # approximate Pisces Sun for this birth
NATAL_MOON_DEG = 18.55   # approximate Sag Moon for this birth


def test_solar_return_structure():
    from astro_mcp.tools.returns import calculate_solar_return
    result = calculate_solar_return(**BIRTH, year=2024)
    assert "return_dt" in result
    assert "sr_planets" in result
    assert "sr_houses" in result
    assert "sr_to_natal_aspects" in result


def test_solar_return_sun_near_natal_sun():
    """At solar return, SR Sun should be near natal Sun position."""
    from astro_mcp.tools.returns import calculate_solar_return
    from astro_mcp.tools.natal import calculate_natal_chart
    natal = calculate_natal_chart(date=BIRTH["birth_date"], time=BIRTH["birth_time"], location=BIRTH["birth_location"])
    result = calculate_solar_return(**BIRTH, year=2024)
    sr_sun = result["sr_planets"]["Su"]["deg"]
    natal_sun = natal["planets"]["Su"]["deg"]
    diff = abs(sr_sun - natal_sun) % 360
    if diff > 180:
        diff = 360 - diff
    assert diff < 0.1, f"SR Sun {sr_sun} not near natal Sun {natal_sun} (diff={diff})"


def test_lunar_return_structure():
    from astro_mcp.tools.returns import calculate_lunar_return
    result = calculate_lunar_return(**BIRTH, from_date="2024-06-01", count=1)
    assert "returns" in result
    assert len(result["returns"]) == 1
    lr = result["returns"][0]
    assert "return_dt" in lr
    assert "lr_planets" in lr
    assert "lr_houses" in lr


def test_lunar_return_moon_near_natal_moon():
    """At lunar return, LR Moon should be near natal Moon position."""
    from astro_mcp.tools.returns import calculate_lunar_return
    from astro_mcp.tools.natal import calculate_natal_chart
    natal = calculate_natal_chart(date=BIRTH["birth_date"], time=BIRTH["birth_time"], location=BIRTH["birth_location"])
    result = calculate_lunar_return(**BIRTH, from_date="2024-06-01", count=1)
    lr_moon = result["returns"][0]["lr_planets"]["Mo"]["deg"]
    natal_moon = natal["planets"]["Mo"]["deg"]
    diff = abs(lr_moon - natal_moon) % 360
    if diff > 180:
        diff = 360 - diff
    assert diff < 1.0, f"LR Moon {lr_moon} not near natal Moon {natal_moon} (diff={diff})"


def test_multiple_lunar_returns():
    from astro_mcp.tools.returns import calculate_lunar_return
    result = calculate_lunar_return(**BIRTH, from_date="2024-01-01", count=3)
    assert len(result["returns"]) == 3
    # Returns should be in chronological order
    dts = [r["return_dt"] for r in result["returns"]]
    assert dts == sorted(dts)
