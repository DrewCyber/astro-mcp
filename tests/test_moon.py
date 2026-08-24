"""Tests for lunar phase, void-of-course, and the transit event body set."""

from __future__ import annotations

import pytest

from astro_mcp.core.ephemeris_provider import calc_planet, to_jd
from astro_mcp.core.models import PLANET_IDS
from astro_mcp.core.moon import PHASE_NAMES, moon_phase, moon_void_of_course
from astro_mcp.tools.natal import calculate_natal_chart
from astro_mcp.tools.transits import MOON_EVENT_MAX_DAYS, calculate_transits

LOC = {"lat": 41.61689, "lon": 41.607043, "tz": "Asia/Tbilisi"}
BIRTH = {"birth_date": "1990-03-15", "birth_time": "14:30", "birth_location": LOC}
ASTEROIDS = {"Ce", "Pa", "Jun", "Ves"}


# ---------------------------------------------------------------------------
# Moon phase
# ---------------------------------------------------------------------------


def test_the_misreported_case_is_waning() -> None:
    """Bug log 2026-07-07: the agent called this waxing. Sun leads the Moon by
    267 degrees, so the Moon is waning."""
    phase = moon_phase(to_jd("2026-07-07T15:30:00Z"))
    assert phase["waxing"] is False
    assert phase["elongation"] > 180


def test_elongation_is_measured_from_the_sun_to_the_moon() -> None:
    for iso in ("2026-01-09T00:00:00Z", "2026-07-07T15:30:00Z", "2026-11-30T06:00:00Z"):
        jd = to_jd(iso)
        sun = calc_planet(jd, PLANET_IDS["Su"])[0]
        moon = calc_planet(jd, PLANET_IDS["Mo"])[0]
        expected = (moon - sun) % 360
        assert moon_phase(jd)["elongation"] == pytest.approx(expected, abs=0.02)


def test_waxing_flag_matches_the_elongation_hemisphere() -> None:
    """Sweep a whole lunation; the flag must never contradict the angle."""
    for day in range(30):
        jd = to_jd("2026-07-01T00:00:00Z") + day
        phase = moon_phase(jd)
        assert phase["waxing"] == (phase["elongation"] < 180.0)


def test_illumination_tracks_the_phase() -> None:
    for day in range(30):
        jd = to_jd("2026-07-01T00:00:00Z") + day
        phase = moon_phase(jd)
        assert 0.0 <= phase["illum_pct"] <= 100.0
        # New is dark, Full is lit; check the two extremes behave.
        if phase["elongation"] < 5 or phase["elongation"] > 355:
            assert phase["illum_pct"] < 2.0
        if 175 < phase["elongation"] < 185:
            assert phase["illum_pct"] > 98.0


def test_phase_name_matches_the_45_degree_segment() -> None:
    for day in range(30):
        jd = to_jd("2026-07-01T00:00:00Z") + day
        phase = moon_phase(jd)
        assert phase["phase"] == PHASE_NAMES[int(phase["elongation"] // 45)]


def test_natal_chart_reports_the_moon_phase() -> None:
    result = calculate_natal_chart(**BIRTH)
    assert "moon" in result
    assert set(result["moon"]) >= {"phase", "elongation", "waxing", "illum_pct"}


# ---------------------------------------------------------------------------
# Void of course
# ---------------------------------------------------------------------------


def test_void_window_is_ordered_and_contains_the_flag() -> None:
    for day in range(14):
        jd = to_jd("2026-07-01T12:00:00Z") + day
        voc = moon_void_of_course(jd)
        assert voc["void_start"] <= voc["void_end"]
        assert isinstance(voc["void_of_course"], bool)


def test_void_period_is_shorter_than_a_sign_passage() -> None:
    """A void cannot outlast the Moon's stay in the sign (~2.5 days)."""
    from astro_mcp.core.ephemeris_provider import to_jd as _to_jd

    for day in range(10):
        jd = to_jd("2026-07-01T12:00:00Z") + day
        voc = moon_void_of_course(jd)
        span = _to_jd(voc["void_end"]) - _to_jd(voc["void_start"])
        assert 0 <= span <= 2.6, voc


def test_transits_report_void_of_course() -> None:
    result = calculate_transits(transit_date="2026-07-26", **BIRTH)
    assert "voc" in result["moon"]
    assert "void_of_course" in result["moon"]["voc"]


# ---------------------------------------------------------------------------
# Event body set: positions and events must agree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("include_asteroids", [False, True])
def test_every_event_body_also_has_a_reported_position(include_asteroids: bool) -> None:
    """The two halves of the result used to disagree: asteroid events were
    emitted for a chart whose transit_planets held no asteroids."""
    result = calculate_transits(
        transit_date="2026-07-26", period_days=30,
        include_asteroids=include_asteroids, **BIRTH,
    )
    positions = set(result["transit_planets"])
    bodies = {e["tp"] for e in result["aspect_events"]}
    assert bodies <= positions, f"events for unreported bodies: {bodies - positions}"


def test_asteroids_are_absent_unless_requested() -> None:
    result = calculate_transits(transit_date="2026-07-26", period_days=30, **BIRTH)
    assert not ASTEROIDS & set(result["transit_planets"])
    assert not ASTEROIDS & {e["tp"] for e in result["aspect_events"]}


def test_asteroids_use_unambiguous_codes() -> None:
    """Ju2/Ve2 were too easily read as Jupiter/Venus by the consuming model."""
    result = calculate_natal_chart(include_asteroids=True, **BIRTH)
    planets = set(result["planets"])
    assert {"Jun", "Ves"} <= planets
    assert not {"Ju2", "Ve2"} & planets


# ---------------------------------------------------------------------------
# Moon event filtering
# ---------------------------------------------------------------------------


def test_long_windows_drop_lunar_events_by_default() -> None:
    result = calculate_transits(transit_date="2026-07-26", period_days=90, **BIRTH)
    assert not [e for e in result["aspect_events"] if e["tp"] == "Mo"]
    assert "events_note" in result


def test_short_windows_keep_lunar_events() -> None:
    result = calculate_transits(
        transit_date="2026-07-26", period_days=MOON_EVENT_MAX_DAYS, **BIRTH
    )
    assert [e for e in result["aspect_events"] if e["tp"] == "Mo"]
    assert "events_note" not in result


def test_lunar_events_can_be_forced_on_a_long_window() -> None:
    result = calculate_transits(
        transit_date="2026-07-26", period_days=90, include_moon_events=True, **BIRTH
    )
    assert [e for e in result["aspect_events"] if e["tp"] == "Mo"]
    assert "events_note" not in result


def test_lunar_events_can_be_suppressed_on_a_short_window() -> None:
    result = calculate_transits(
        transit_date="2026-07-26", period_days=3, include_moon_events=False, **BIRTH
    )
    assert not [e for e in result["aspect_events"] if e["tp"] == "Mo"]


def test_dropping_lunar_events_does_not_disturb_the_others() -> None:
    """Filtering must remove Moon rows and change nothing else."""
    with_moon = calculate_transits(
        transit_date="2026-07-26", period_days=30, include_moon_events=True, **BIRTH
    )
    without = calculate_transits(
        transit_date="2026-07-26", period_days=30, include_moon_events=False, **BIRTH
    )
    expected = [e for e in with_moon["aspect_events"] if e["tp"] != "Mo"]
    assert without["aspect_events"] == expected


def test_lunar_filtering_makes_a_long_scan_substantially_cheaper() -> None:
    import json

    full = calculate_transits(
        transit_date="2026-07-26", period_days=90, include_moon_events=True, **BIRTH
    )
    lean = calculate_transits(transit_date="2026-07-26", period_days=90, **BIRTH)
    assert len(json.dumps(lean)) < len(json.dumps(full)) * 0.5
