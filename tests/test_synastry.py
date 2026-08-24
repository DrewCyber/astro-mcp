"""Tests for calculate_synastry and calculate_composite_chart."""


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


# --- Regression: R-12 Davison midpoint across the antimeridian --------------

def test_geographic_midpoint_handles_antimeridian():
    from astro_mcp.tools.synastry import _geographic_midpoint

    # Tokyo (139.7E) x Los Angeles (118.2W): the naive average lands near
    # 11E (Chad); the great-circle midpoint must be in the northern Pacific.
    lat, lon = _geographic_midpoint(35.68, 139.69, 34.05, -118.24)
    assert lon > 150 or lon < -130, f"midpoint fell in the wrong hemisphere: {lon}"
    assert 30 <= lat <= 70
    # Same pair expressed with an equivalent wrap of the Tokyo longitude
    lat2, lon2 = _geographic_midpoint(35.68, 139.69 - 360, 34.05, -118.24)
    assert abs(lat - lat2) < 0.01 and abs(lon - lon2) < 0.01


def test_geographic_midpoint_simple_and_antipodal():
    from astro_mcp.tools.synastry import _geographic_midpoint

    # Same hemisphere: great-circle midpoint ~= naive average.
    lat, lon = _geographic_midpoint(50.0, 10.0, 52.0, 14.0)
    assert abs(lat - 51.0) < 0.3 and abs(lon - 12.0) < 0.3
    # Exactly antipodal: deterministic equatorial point instead of a crash.
    lat, lon = _geographic_midpoint(40.0, 30.0, -40.0, -150.0)
    assert lat == 0.0
    assert -180 <= lon < 180


def test_davison_composite_warns_on_cross_hemisphere_pair():
    from astro_mcp.tools.synastry import calculate_composite_chart

    tokyo = {"lat": 35.68, "lon": 139.69, "tz": "Asia/Tokyo"}
    los_angeles = {"lat": 34.05, "lon": -118.24, "tz": "America/Los_Angeles"}
    result = calculate_composite_chart(
        person1_date="1990-06-15", person1_time="12:00",
        person1_location=tokyo,
        person2_date="1990-06-15", person2_time="12:00",
        person2_location=los_angeles,
        method="davison",
    )
    loc = result.get("davison_location")
    assert loc is not None
    assert loc["lon"] > 150 or loc["lon"] < -130
    assert "great-circle midpoint" in loc.get("note", "")
