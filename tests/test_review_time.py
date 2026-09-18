"""UTC input precision regression."""

import pytest

from astro_mcp.core.ephemeris_provider import to_jd


def test_fractional_seconds_are_preserved():
    delta = to_jd("2000-01-01T12:00:00.9Z") - to_jd("2000-01-01T12:00:00Z")
    assert delta * 86400 == pytest.approx(0.9, abs=0.00005)
