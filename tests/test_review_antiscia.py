"""Mirrored coordinates stay unrounded until output serialization."""

import json
from types import SimpleNamespace

import pytest

from astro_mcp.core.ephemeris_provider import build_chart_point
from astro_mcp.tools.antiscia import calculate_antiscia


@pytest.mark.parametrize("degree_format", ["dec", "dms"])
@pytest.mark.parametrize("target,expected", [(13.003, True), (13.005, False)])
def test_raw_mirror_contacts_and_reversed_motion(monkeypatch, degree_format, target, expected):
    chart = SimpleNamespace(
        all_points={"Su": build_chart_point(169.996, 1.0),
                    "Mo": build_chart_point(target, -1.0)},
        cusps=[i * 30.0 for i in range(12)], house_system_warning=None,
    )
    monkeypatch.setattr("astro_mcp.tools.antiscia.compute_natal", lambda *args: chart)
    monkeypatch.setattr("astro_mcp.tools.antiscia.calc_all_planets",
                        lambda *args: {"Me": build_chart_point(target, 1.0)})
    result = calculate_antiscia("1990-01-01", "12:00", "test", orb=3.0,
                               degree_format=degree_format,
                               include_transits_date="2026-01-01")
    natal_hit = any(h["point"] == "Su" and h["contacts"] == "Mo"
                    and h["kind"] == "antiscion" for h in result["contacts"])
    transit_hit = any(h["contacts"] == "Su" and h["kind"] == "antiscion"
                      for h in result.get("transit_contacts", []))
    assert natal_hit is expected
    assert transit_hit is expected
    assert isinstance(result, dict)
    for key in ("antiscia", "contra_antiscia"):
        assert isinstance(result[key], dict)
        assert all(isinstance(point, dict) for point in result[key].values())
        assert result[key]["Su"]["R"] is True
        assert not result[key]["Mo"].get("R", False)
    json.dumps(result)
