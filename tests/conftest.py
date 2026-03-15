"""Shared test fixtures for astro-mcp."""

import json
import os
import pytest


# Known natal data: Albert Einstein, 14 Mar 1879, 11:30 LMT, Ulm, Germany
EINSTEIN_BIRTH = {
    "birth_date": "1879-03-14",
    "birth_time": "11:30",
    "birth_location": {"lat": 48.4011, "lon": 9.9876, "tz": "Europe/Berlin"},
}

# Simple contemporary chart for fast testing
MODERN_BIRTH = {
    "birth_date": "1990-03-15",
    "birth_time": "14:30",
    "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
}


@pytest.fixture(scope="session")
def einstein_natal():
    """Pre-computed Einstein natal chart (session-scoped for speed)."""
    from astro_mcp.tools.natal import calculate_natal_chart
    return calculate_natal_chart(**EINSTEIN_BIRTH)


@pytest.fixture(scope="session")
def modern_natal():
    from astro_mcp.tools.natal import calculate_natal_chart
    return calculate_natal_chart(**MODERN_BIRTH)
