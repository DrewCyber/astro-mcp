"""Regressions for defects reported in .github/agents/astrologer.mcp-bugreport.md.

Each test names the log entry it pins. All use explicit coordinates so no
network geocoding is needed.
"""

from __future__ import annotations

import pytest

from astro_mcp.core.errors import AstroError
from astro_mcp.tools.ephemeris import find_aspect_exact_dates, get_ephemeris
from astro_mcp.tools.transits import calculate_transits

BATUMI = {"lat": 41.61689, "lon": 41.607043, "tz": "Asia/Tbilisi"}
NATAL = {"birth_date": "1990-03-15", "birth_time": "14:30", "birth_location": BATUMI}

# Mo square natal Sa perfects at 2026-07-21T00:40:55Z for this chart -- 40
# minutes into the day, which is what made the exclusive end date visible.
KNOWN_EXACT = "2026-07-21"


# ---------------------------------------------------------------------------
# 2026-07-17: empty occurrences for Moon aspects inside a 1-3 day window
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        (KNOWN_EXACT, KNOWN_EXACT),      # single-day range
        ("2026-07-20", KNOWN_EXACT),     # perfection on the last requested day
        (KNOWN_EXACT, "2026-07-22"),     # perfection on the first requested day
        ("2026-07-19", "2026-07-23"),    # comfortably inside
    ],
)
def test_date_to_is_inclusive_for_aspect_search(date_from: str, date_to: str) -> None:
    res = find_aspect_exact_dates(
        planet1="Mo", planet2="Sa", aspect="Squ",
        date_from=date_from, date_to=date_to, mode="transit-to-natal",
        orb=1.0, **NATAL,
    )
    found = [d for o in res["occurrences"] for d in o["exact_dates"]]
    assert KNOWN_EXACT in found, f"{date_from}..{date_to} missed the perfection"


def test_perfection_outside_the_range_is_not_reported() -> None:
    """The inclusive end must not leak the following day's events."""
    res = find_aspect_exact_dates(
        planet1="Mo", planet2="Sa", aspect="Squ",
        date_from="2026-07-18", date_to="2026-07-20", mode="transit-to-natal",
        orb=1.0, **NATAL,
    )
    found = [d for o in res["occurrences"] for d in o["exact_dates"]]
    assert KNOWN_EXACT not in found


def test_moon_search_is_not_defeated_by_a_coarse_scan_step() -> None:
    """The Moon covers ~13 deg/day; every aspect it makes to a natal point must
    still be found across a full synodic cycle."""
    for aspect in ("Cnj", "Sex", "Squ", "Tri", "Opp"):
        res = find_aspect_exact_dates(
            planet1="Mo", planet2="Sa", aspect=aspect,
            date_from="2026-07-01", date_to="2026-07-31",
            mode="transit-to-natal", orb=1.0, **NATAL,
        )
        found = [d for o in res["occurrences"] for d in o["exact_dates"]]
        assert found, f"Mo {aspect} natal Sa found nothing in a whole month"


def test_the_two_timing_tools_agree_on_the_same_window() -> None:
    """The original complaint: calculate_transits reported exact dates that
    find_aspect_exact_dates then denied for an identical range."""
    start, end, days = "2026-07-17", "2026-07-19", 3
    tr = calculate_transits(transit_date=start, period_days=days, max_orb=1.0, **NATAL)
    events = tr["aspect_events"]
    assert events, "expected transit events in the window"

    missing = []
    for ev in events:
        res = find_aspect_exact_dates(
            planet1=ev["tp"], planet2=ev["np"], aspect=ev["asp"],
            date_from=start, date_to=end, mode="transit-to-natal",
            orb=1.0, **NATAL,
        )
        dates = [d for o in res["occurrences"] for d in o["exact_dates"]]
        if ev["exact"] not in dates:
            missing.append((ev["tp"], ev["asp"], ev["np"], ev["exact"], dates))
    assert not missing, f"find_aspect_exact_dates missed {missing}"


def test_transit_events_stay_inside_the_requested_calendar_days() -> None:
    """period_days=3 from 2026-07-17 means the 17th, 18th and 19th -- the scan
    used to hang off the transit moment and spill into the 20th."""
    tr = calculate_transits(transit_date="2026-07-17", period_days=3, max_orb=1.0, **NATAL)
    dates = {e["exact"] for e in tr["aspect_events"]}
    assert dates <= {"2026-07-17", "2026-07-18", "2026-07-19"}, f"spilled outside: {dates}"


# ---------------------------------------------------------------------------
# 2026-07-05: get_ephemeris ignored output_tz
# ---------------------------------------------------------------------------


def test_ephemeris_applies_output_tz() -> None:
    res = get_ephemeris(planet="Mo", date_from="2026-07-06", date_to="2026-07-07",
                        interval_hours=6, output_tz="Asia/Tbilisi")
    assert res["timezone"] == "Asia/Tbilisi"
    # Asia/Tbilisi is UTC+4 year round, so a UTC-midnight sample is 04:00 local.
    assert res["rows"][0]["dt"].startswith("2026-07-06T04:00:00+04:00")
    assert all("+04:00" in row["dt"] for row in res["rows"])


def test_ephemeris_output_tz_shifts_relative_to_utc() -> None:
    local = get_ephemeris(planet="Su", date_from="2026-07-06", date_to="2026-07-06",
                          interval_hours=6, output_tz="Asia/Tbilisi")
    utc = get_ephemeris(planet="Su", date_from="2026-07-06", date_to="2026-07-06",
                        interval_hours=6, output_tz="UTC")
    assert [r["deg"] for r in local["rows"]] == [r["deg"] for r in utc["rows"]]
    assert [r["dt"] for r in local["rows"]] != [r["dt"] for r in utc["rows"]]


def test_ephemeris_rejects_an_unknown_timezone() -> None:
    with pytest.raises(AstroError) as exc:
        get_ephemeris(planet="Su", date_from="2026-07-06", date_to="2026-07-07",
                      output_tz="Europe/Tbilisi")
    assert exc.value.code == "INPUT_ERROR"


def test_ephemeris_covers_the_whole_final_day() -> None:
    res = get_ephemeris(planet="Su", date_from="2026-07-06", date_to="2026-07-07",
                        interval_hours=6)
    assert res["rows"][-1]["dt"].startswith("2026-07-07T18:00")


# ---------------------------------------------------------------------------
# 2026-06-20: Ma-Sa semisquare separation_date a month after exactness
# ---------------------------------------------------------------------------


def test_separation_date_is_close_to_exactness_for_a_fast_pair() -> None:
    from datetime import date as Date

    res = find_aspect_exact_dates(planet1="Ma", planet2="Sa", aspect="SSq",
                                  date_from="2026-06-01", date_to="2026-08-31",
                                  mode="transit-to-transit", orb=1.0)
    assert res["occurrences"], "expected a Ma-Sa semisquare in this range"
    for occ in res["occurrences"]:
        exact = Date.fromisoformat(occ["exact_date"])
        approach = Date.fromisoformat(occ["approach_date"])
        separation = Date.fromisoformat(occ["separation_date"])
        assert approach <= exact <= separation
        # Mars closes on Saturn at roughly half a degree a day, so a 1 degree
        # orb cannot stay open for anything like a month.
        assert (separation - exact).days <= 10, occ
        assert (exact - approach).days <= 10, occ


# ---------------------------------------------------------------------------
# 2026-06-19: a bad IANA zone surfaced as INTERNAL_ERROR
# ---------------------------------------------------------------------------


def test_unknown_timezone_is_a_structured_error_not_an_internal_one() -> None:
    bad = {"lat": 41.61689, "lon": 41.607043, "tz": "Europe/Tbilisi"}
    with pytest.raises(AstroError) as exc:
        calculate_transits(transit_date="2026-06-20", birth_date="1990-03-15",
                           birth_time="14:30", birth_location=bad)
    assert exc.value.code == "TIMEZONE_UNKNOWN"
    assert "Europe/Tbilisi" in str(exc.value)
