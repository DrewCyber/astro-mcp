"""Internal precision survives until explicit output formatting."""

import pytest

from astro_mcp.core.ephemeris_provider import build_chart_point, build_house_cusps, find_aspects
from astro_mcp.core.formatters import serialize_aspect, serialize_house, serialize_point


def test_point_and_house_retain_precision():
    longitude = 29.9999998765
    speed = -0.0000123456
    point = build_chart_point(longitude, speed)
    assert point.lon_decimal == longitude
    assert point.sign_lon == longitude
    assert point.speed == speed
    assert point.retrograde
    assert build_house_cusps([longitude + i * 30 for i in range(12)])[0].lon_decimal == longitude


def test_aspect_orb_is_unrounded_internally():
    aspects = find_aspects({"Su": build_chart_point(0, 1)},
                           {"Mo": build_chart_point(3.004, 13)})
    aspect = next(a for a in aspects if a.aspect_type == "Cnj")
    assert aspect.orb == pytest.approx(3.004)
    assert aspect.orb > 3
    assert serialize_aspect(aspect)["orb"] == 3.0


@pytest.mark.parametrize("longitude,expected_sign,expected_degree", [
    (359.9999999, "Ari", 0.0), (29.9999999, "Tau", 30.0),
])
def test_serialization_carries_longitude_and_sign_together(longitude, expected_sign, expected_degree):
    result = serialize_point(build_chart_point(longitude, 1))
    assert result["sign"] == expected_sign
    assert result["deg"] == expected_degree
    house = serialize_house(build_house_cusps([longitude + i * 30 for i in range(12)])[0])
    assert house["sign"] == expected_sign
    assert float(house["cusp"]) == expected_degree
    assert "mod_ruler" not in house
    for output in (serialize_point(build_chart_point(longitude, 1), "dms"),
                   serialize_house(build_house_cusps([longitude])[0], "dms")):
        assert output["sign"] == expected_sign
        assert "00°00'00\"" in output.get("lon", output.get("cusp", ""))
