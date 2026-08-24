"""Tests for calculate_arabic_parts."""

BIRTH = {"birth_date": "1990-03-15", "birth_time": "14:30",
          "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}}


def test_arabic_parts_structure():
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    result = calculate_arabic_parts(**BIRTH)
    assert "chart_type" in result
    assert "parts" in result
    assert result["chart_type"] in ("day", "night")


def test_all_parts_present():
    from astro_mcp.tools.arabic_parts import PART_FORMULAS, calculate_arabic_parts
    result = calculate_arabic_parts(**BIRTH)
    for code in PART_FORMULAS:
        assert code in result["parts"], f"Missing part: {code}"


def test_selected_parts_only():
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    result = calculate_arabic_parts(**BIRTH, parts=["FortPt", "SpiritPt"])
    assert "FortPt" in result["parts"]
    assert "SpiritPt" in result["parts"]
    assert "MarriagePt" not in result["parts"]


def test_fortuna_degrees_in_range():
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    result = calculate_arabic_parts(**BIRTH)
    deg = result["parts"]["FortPt"]["deg"]
    assert 0 <= deg < 360


# --- Regression: R-1 day/night inversion ---------------------------------
# Houses 7-12 lie ABOVE the horizon, so a noon birth (Sun near MC, house 10)
# is a DAY chart and a midnight birth (Sun near IC, house 4) a NIGHT chart.
# The old `su_house not in (7..12)` test labelled both the opposite way.

def test_noon_birth_is_day_chart():
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    result = calculate_arabic_parts(
        birth_date="1990-06-15", birth_time="12:00",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
    )
    assert result["chart_type"] == "day"


def test_midnight_birth_is_night_chart():
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    result = calculate_arabic_parts(
        birth_date="1990-06-15", birth_time="00:00",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
    )
    assert result["chart_type"] == "night"


def _chart_longs(birth_time: str):
    """Full-precision Asc/Su/Mo longitudes for the Moscow test chart."""
    from astro_mcp.tools.natal import compute_natal
    chart = compute_natal("1990-06-15", birth_time,
                          {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"})
    return (
        chart.angles["Asc"].lon_decimal,
        chart.planets["Su"].lon_decimal,
        chart.planets["Mo"].lon_decimal,
        chart.is_day,
    )


def test_day_chart_uses_diurnal_fortune_formula():
    # Day sect: Fortune = Asc + Moon - Sun.
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    asc, su, mo, is_day = _chart_longs("12:00")
    assert is_day
    expected = round((asc + mo - su) % 360, 2)
    result = calculate_arabic_parts(
        birth_date="1990-06-15", birth_time="12:00",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
    )
    assert abs(result["parts"]["FortPt"]["deg"] - expected) < 0.01


def test_night_chart_swaps_fortune_and_spirit_formulas():
    # Night sect swaps sect lights: Fortune = Asc + Sun - Moon.
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts
    asc, su, mo, is_day = _chart_longs("00:00")
    assert not is_day
    expected = round((asc + su - mo) % 360, 2)
    result = calculate_arabic_parts(
        birth_date="1990-06-15", birth_time="00:00",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
    )
    assert abs(result["parts"]["FortPt"]["deg"] - expected) < 0.01
