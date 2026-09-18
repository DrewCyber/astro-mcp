"""Exact crossings are grouped only when they retrace one slow-pair branch."""

import pytest

from astro_mcp.core.ephemeris_provider import to_jd
from astro_mcp.tools import ephemeris


@pytest.mark.parametrize("planet,aspect,count", [("Me", "Cnj", 6), ("Mo", "Sex", 24)])
def test_fast_pair_crossings_are_independent(planet, aspect, count):
    result = ephemeris.find_aspect_exact_dates(planet, "Su", aspect,
                                              "2026-01-01", "2026-12-31")
    occurrences = result["occurrences"]
    assert len(occurrences) == count
    assert all(o["passes"] == 1 and not o["is_triple_pass"] for o in occurrences)


def test_real_saturn_uranus_triple_is_preserved():
    result = ephemeris.find_aspect_exact_dates("Sa", "Ur", "Squ",
                                              "2021-01-01", "2021-12-31")
    assert len(result["occurrences"]) == 1
    occurrence = result["occurrences"][0]
    assert occurrence["is_triple_pass"]
    assert occurrence["exact_dates"] == ["2021-02-17", "2021-06-14", "2021-12-24"]


def test_short_range_at_coverage_end_needs_no_future_samples():
    ephemeris.find_aspect_exact_dates("Sa", "Ur", "Cnj", "2399-12-01", "2399-12-02")


@pytest.mark.parametrize("offset", [0.0, 0.5, 1.0 - 1 / 86400])
def test_exact_samples_and_endpoints_are_included_without_outside_reads(monkeypatch, offset):
    start = to_jd("2026-01-01T00:00:00Z")
    end = to_jd("2026-01-01T23:59:59Z")
    root = start + offset
    def position(jd, pid):
        assert start <= jd <= end
        return ((jd - root) % 360, 1.0) if pid == ephemeris.pid_for("Sa") else (0.0, 0.0)
    monkeypatch.setattr(ephemeris, "calc_planet", position)
    monkeypatch.setattr("astro_mcp.core.ephemeris_provider.calc_planet", position)
    result = ephemeris.find_aspect_exact_dates("Sa", "Ur", "Cnj",
                                              "2026-01-01", "2026-01-01")
    assert sum(o["passes"] for o in result["occurrences"]) == 1
