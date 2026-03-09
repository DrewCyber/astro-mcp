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
    from astro_mcp.tools.arabic_parts import calculate_arabic_parts, PART_FORMULAS
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
