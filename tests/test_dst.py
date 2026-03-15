"""Tests for DST edge-case handling in local_to_utc."""

import pytest
from astro_mcp.core.geocoding import local_to_utc


# ---------------------------------------------------------------------------
# Normal times — no warning expected
# ---------------------------------------------------------------------------

def test_normal_summer_time():
    """Regular summer time conversion — no DST edge case."""
    utc, warning = local_to_utc("1986-06-15", "14:30", "Europe/Moscow")
    assert utc == "1986-06-15T10:30:00Z"
    assert warning is None


def test_normal_winter_time():
    """Regular winter time conversion — no DST edge case."""
    utc, warning = local_to_utc("1986-01-15", "14:30", "Europe/Moscow")
    assert utc == "1986-01-15T11:30:00Z"
    assert warning is None


def test_normal_no_dst_timezone():
    """UTC timezone — never has DST issues."""
    utc, warning = local_to_utc("1986-07-01", "12:00", "UTC")
    assert utc == "1986-07-01T12:00:00Z"
    assert warning is None


# ---------------------------------------------------------------------------
# Fall-back fold — ambiguous time, must warn and default to standard time
# ---------------------------------------------------------------------------

def test_fall_back_fold_warning():
    """Moscow 1986 fall-back: 1986-09-28 02:30 is ambiguous (UTC+4 or UTC+3)."""
    utc, warning = local_to_utc("1986-09-28", "02:30", "Europe/Moscow")
    assert warning == "fall_back_fold"


def test_fall_back_fold_uses_standard_time():
    """Should default to standard time (fold=1, UTC+3) — the later/second occurrence.

    UTC+4 (summer) → 1986-09-27T22:30:00Z
    UTC+3 (standard) → 1986-09-27T23:30:00Z  ← expected
    """
    utc, warning = local_to_utc("1986-09-28", "02:30", "Europe/Moscow")
    assert utc == "1986-09-27T23:30:00Z", (
        f"Expected standard-time (UTC+3) interpretation 1986-09-27T23:30:00Z, got {utc}. "
        "fall_back_fold must not silently pick the DST/summer-time interpretation."
    )


def test_fall_back_fold_us_eastern():
    """US Eastern fall-back 2024: 2024-11-03 01:30 is ambiguous (EDT→EST)."""
    utc, warning = local_to_utc("2024-11-03", "01:30", "America/New_York")
    assert warning == "fall_back_fold"
    # fold=1 (EST, UTC-5) → 06:30Z;  fold=0 (EDT, UTC-4) → 05:30Z
    assert utc == "2024-11-03T06:30:00Z", (
        "Expected standard-time EST (UTC-5) → 06:30Z, "
        f"not DST EDT (UTC-4) → 05:30Z. Got: {utc}"
    )


# ---------------------------------------------------------------------------
# Spring-forward gap — non-existent time, must warn
# ---------------------------------------------------------------------------

def test_spring_forward_gap_warning():
    """Moscow 1986 spring-forward: 1986-03-30 02:30 does not exist."""
    utc, warning = local_to_utc("1986-03-30", "02:30", "Europe/Moscow")
    assert warning == "spring_forward_gap"


def test_spring_forward_gap_uses_pre_transition():
    """For a non-existent gap time, conventionally use the pre-transition (fold=0) offset.

    Pre-transition is UTC+3 → 1986-03-29T23:30:00Z
    """
    utc, warning = local_to_utc("1986-03-30", "02:30", "Europe/Moscow")
    assert utc == "1986-03-29T23:30:00Z"


def test_spring_forward_gap_us_eastern():
    """US Eastern spring-forward 2024: 2024-03-10 02:30 does not exist."""
    utc, warning = local_to_utc("2024-03-10", "02:30", "America/New_York")
    assert warning == "spring_forward_gap"


# ---------------------------------------------------------------------------
# DST warning propagates into natal chart meta
# ---------------------------------------------------------------------------

def test_natal_meta_includes_dst_warning(tmp_path, monkeypatch):
    """A birth time in a fall-back fold should surface dst_warning in the natal meta."""
    import os
    monkeypatch.setenv("EPHE_PATH", str(os.environ.get("EPHE_PATH", "./ephe")))

    from astro_mcp.tools.natal import calculate_natal_chart
    result = calculate_natal_chart(
        birth_date="1986-09-28",
        birth_time="02:30",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
        house_system="P",
    )
    assert "dst_warning" in result.get("meta", {}), (
        "Natal chart meta must contain dst_warning when birth time is in a DST fold"
    )
    assert result["meta"]["dst_warning"] == "fall_back_fold"


def test_natal_meta_no_dst_warning_for_normal_time():
    """A normal birth time must not have dst_warning in meta."""
    from astro_mcp.tools.natal import calculate_natal_chart
    result = calculate_natal_chart(
        birth_date="1986-06-15",
        birth_time="14:30",
        birth_location={"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
        house_system="P",
    )
    assert "dst_warning" not in result.get("meta", {}), (
        "Normal birth times must not pollute meta with dst_warning"
    )
