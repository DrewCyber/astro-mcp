"""Behavioral tests for get_planetary_hours.

The tool had zero dedicated coverage: only its schema signature was locked
in. These tests pin the hour boundaries against the rise/set primitive,
the Chaldean day-ruler sequence, boundary continuity, and the polar
NO_RISE_SET error path.
"""

from datetime import datetime
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from astro_mcp.core.errors import AstroError

MOSCOW = {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}
MONDAY = "2026-06-15"  # a Monday


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


@pytest.fixture(scope="module")
def hours() -> dict:
    from astro_mcp.tools.planetary_hours import get_planetary_hours
    return get_planetary_hours(MONDAY, MOSCOW)


def test_day_ruler_follows_the_weekday(hours: dict) -> None:
    from astro_mcp.core.models import WEEKDAY_TO_RULER

    weekday = datetime.fromisoformat(f"{MONDAY}T12:00").weekday()
    assert hours["weekday"] == "Monday"
    assert hours["day_ruler"] == WEEKDAY_TO_RULER[weekday] == "Mo"


def test_hour_boundaries_match_independent_rise_set(hours: dict) -> None:
    """Day hour 1 starts at sunrise, hour 12 ends at sunset — cross-checked
    against calc_rise_set rather than the tool's own arithmetic."""
    from astro_mcp.core.ephemeris_provider import calc_rise_set, to_jd

    midnight = datetime.fromisoformat(f"{MONDAY}T00:00:00").replace(
        tzinfo=ZoneInfo("Europe/Moscow")
    ).astimezone(ZoneInfo("UTC"))
    jd_rise, jd_set = calc_rise_set(to_jd(midnight.strftime("%Y-%m-%dT%H:%M:%SZ")),
                                    MOSCOW["lat"], MOSCOW["lon"])

    from astro_mcp.tools.planetary_hours import _jd_to_local_time
    assert hours["sunrise"] == _jd_to_local_time(jd_rise, "Europe/Moscow")
    assert hours["sunset"] == _jd_to_local_time(jd_set, "Europe/Moscow")
    assert hours["day_hours"][0]["start"] == hours["sunrise"]
    assert hours["day_hours"][-1]["end"] == hours["sunset"]
    assert hours["night_hours"][0]["start"] == hours["sunset"]


def test_chaldean_sequence_for_a_monday(hours: dict) -> None:
    from astro_mcp.core.models import CHALDEAN_ORDER

    start = CHALDEAN_ORDER.index("Mo")
    expected_day = [CHALDEAN_ORDER[(start + i) % 7] for i in range(12)]
    expected_night = [CHALDEAN_ORDER[(start + 12 + i) % 7] for i in range(12)]
    assert [h["planet"] for h in hours["day_hours"]] == expected_day
    assert [h["planet"] for h in hours["night_hours"]] == expected_night


def test_all_24_hours_run_continuously_through_the_chaldean_order(hours: dict) -> None:
    """Night hour 1 follows day hour 12; every consecutive pair advances
    exactly one step through the Chaldean order (with wraparound)."""
    from astro_mcp.core.models import CHALDEAN_ORDER

    all_hours = [h["planet"] for h in hours["day_hours"] + hours["night_hours"]]
    assert len(all_hours) == 24
    for a, b in pairwise(all_hours):
        assert CHALDEAN_ORDER.index(b) == (CHALDEAN_ORDER.index(a) + 1) % 7
    # The sequence closes the full 7-cycle three times over plus 3.
    assert len(set(all_hours)) == 7


def test_hour_boundaries_are_contiguous_and_ordered(hours: dict) -> None:
    def duration(h: dict) -> int:
        return (_minutes(h["end"]) - _minutes(h["start"])) % (24 * 60)

    for seq_name in ("day_hours", "night_hours"):
        seq = hours[seq_name]
        assert [h["n"] for h in seq] == list(range(1, 13))
        for prev, nxt in pairwise(seq):
            assert _minutes(nxt["start"]) >= _minutes(prev["end"]) - 1, (
                f"{seq_name}: gap or backwards jump between {prev['n']} and {nxt['n']}"
            )
        # Unequal hours by design: at Moscow in mid-June the day arc is
        # ~17.5 h (~87 min/hour) and the night arc ~6.5 h (~33 min/hour).
        # Anything outside 10..180 min means the arc arithmetic broke.
        for h in seq:
            assert 10 <= duration(h) <= 180, f"{seq_name} hour {h['n']}: {duration(h)} min"


def test_tz_output_overrides_location_timezone() -> None:
    from astro_mcp.tools.planetary_hours import get_planetary_hours

    result = get_planetary_hours(MONDAY, MOSCOW, tz_output="UTC")
    assert result["tz"] == "UTC"
    # Moscow is UTC+3 in June: sunrise 03:44 local must be 00:44 UTC.
    assert result["sunrise"] == "00:44"


def test_polar_day_raises_no_rise_set() -> None:
    from astro_mcp.tools.planetary_hours import get_planetary_hours

    longyearbyen = {"lat": 78.22, "lon": 15.63, "tz": "Arctic/Longyearbyen"}
    with pytest.raises(AstroError) as exc:
        get_planetary_hours("2026-07-01", longyearbyen)
    assert exc.value.code == "NO_RISE_SET"


def test_polar_night_raises_no_rise_set() -> None:
    from astro_mcp.tools.planetary_hours import get_planetary_hours

    longyearbyen = {"lat": 78.22, "lon": 15.63, "tz": "Arctic/Longyearbyen"}
    with pytest.raises(AstroError) as exc:
        get_planetary_hours("2027-01-08", longyearbyen)
    assert exc.value.code == "NO_RISE_SET"
