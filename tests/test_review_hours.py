"""Regression coverage for display-timezone-independent planetary hours."""

import pytest

from astro_mcp.tools.planetary_hours import get_planetary_hours


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


@pytest.mark.parametrize("output_tz,offset", [("UTC", -540), ("Pacific/Honolulu", -1140)])
def test_tokyo_output_timezone_only_changes_display(output_tz: str, offset: int) -> None:
    location = {"lat": 35.68, "lon": 139.69, "tz": "Asia/Tokyo"}
    local = get_planetary_hours("2026-09-17", location)
    converted = get_planetary_hours("2026-09-17", location, tz_output=output_tz)
    assert local["day_ruler"] == converted["day_ruler"]
    assert local["weekday"] == converted["weekday"]
    for key in ("day_hours", "night_hours"):
        for original, rendered in zip(local[key], converted[key], strict=True):
            assert original["planet"] == rendered["planet"]
            for boundary in ("start", "end"):
                assert _minutes(rendered[boundary]) == (_minutes(original[boundary]) + offset) % 1440
            duration = (_minutes(rendered["end"]) - _minutes(rendered["start"])) % 1440
            assert 20 < duration < 120
