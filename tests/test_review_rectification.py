"""Rectification consumes unrounded internal points and only sensitive targets."""

from astro_mcp.tools.rectification import TIME_SENSITIVE_POINTS, calculate_rectification_hints

BIRTH = {"birth_date": "1990-01-01", "birth_time": "12:00",
         "birth_location": {"lat": 40.7, "lon": -74, "tz": "UTC"},
         "events": [{"date": "2010-01-01"}, {"date": "2015-01-01"},
                    {"date": "2020-01-01"}]}


def test_progression_only_never_calls_wire_tool_or_transit_builder(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unneeded serialized or transit computation")
    monkeypatch.setattr("astro_mcp.tools.progressions.calculate_secondary_progressions", forbidden)
    monkeypatch.setattr("astro_mcp.tools.rectification._transit_charts_for_events", forbidden)
    result = calculate_rectification_hints(**BIRTH, techniques=["progressions"])
    assert result["correlations"]
    assert all(indicator["point"] in TIME_SENSITIVE_POINTS
               for row in result["correlations"] for indicator in row["indicators"])


def test_profections_have_no_synthetic_cusp_targets():
    result = calculate_rectification_hints(**BIRTH, techniques=["profections"])
    assert all(indicator["point"] in TIME_SENSITIVE_POINTS
               for row in result["correlations"] for indicator in row["indicators"])
