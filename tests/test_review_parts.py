"""Raw lot contacts and explicit sect regressions."""

import inspect

from astro_mcp.core.ephemeris_provider import build_chart_point
from astro_mcp.tools import arabic_parts as parts

BIRTH = {"birth_date": "1990-01-01", "birth_time": "06:00",
         "birth_location": {"lat": 40.71, "lon": -74.01, "tz": "America/New_York"}}


def test_activation_uses_raw_longitudes(monkeypatch):
    monkeypatch.setattr(parts, "compute_part_points", lambda *a, **kw: {
        "FortPt": build_chart_point(10.004, 0.0),
    })
    monkeypatch.setattr(parts, "calc_all_planets", lambda jd: {
        "Su": build_chart_point(13.005, 1.0),
    })
    result = parts.calculate_arabic_parts(**BIRTH, include_transits_date="2026-01-01")
    assert "transit_activations" not in result
    monkeypatch.setattr(parts, "calc_all_planets", lambda jd: {
        "Su": build_chart_point(13.003, 1.0),
    })
    result = parts.calculate_arabic_parts(**BIRTH, include_transits_date="2026-01-01")
    assert result["transit_activations"]["FortPt"][0]["planet"] == "Su"


def test_sect_is_required():
    assert inspect.signature(parts.compute_parts).parameters["is_day"].default is inspect.Parameter.empty


def test_profection_rulers_follow_signs():
    from astro_mcp.core.models import RULERS, SIGNS
    from astro_mcp.tools.profections import calculate_profections
    result = calculate_profections(**BIRTH, target_date="1992-01-02")
    index = SIGNS.index(result["profected_sign"])
    expected = {RULERS[SIGNS[(index + offset) % 12]][0] for offset in (0, 3, 6, 9)}
    assert set(result["activated_planets"]) == expected
    assert result["year_ruler"] in expected
