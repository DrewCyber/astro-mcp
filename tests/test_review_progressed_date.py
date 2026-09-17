"""Progressed dates must describe the instant used by the ephemeris."""

from datetime import date

import pytest

from astro_mcp.core.ephemeris_provider import jd_to_iso
from astro_mcp.tools.natal import compute_natal
from astro_mcp.tools.progressions import calculate_secondary_progressions


@pytest.mark.parametrize("birth_time,timezone", [("23:30", "UTC"), ("00:30", "Asia/Tokyo")])
def test_progressed_day_matches_computed_julian_day(birth_time, timezone):
    birth_date = "1990-01-01"
    target = "2026-09-17"
    chart = compute_natal(birth_date, birth_time,
                          {"lat": 35.7, "lon": 139.7, "tz": timezone})
    age = (date.fromisoformat(target) - date.fromisoformat(birth_date)).days / 365.25
    expected = jd_to_iso(chart.jd + age)
    result = calculate_secondary_progressions(birth_date=birth_date,
                                              progression_date=target, chart=chart)
    assert result["prog_day"] == expected[:10]
    assert result["prog_datetime_utc"] == expected
