"""The South Node as a first-class body.

SN has no Swiss Ephemeris id -- it is the north node opposed -- so it used to
fall through every id-based path with UNKNOWN_PLANET even though the tools
advertised it.
"""

from __future__ import annotations

import pytest

from astro_mcp.core.ephemeris_provider import calc_all_planets, calc_planet, to_jd
from astro_mcp.core.models import PLANET_IDS
from astro_mcp.tools.ephemeris import find_aspect_exact_dates, get_ephemeris
from astro_mcp.tools.transits import calculate_transits

LOC = {"lat": 41.61689, "lon": 41.607043, "tz": "Asia/Tbilisi"}
BIRTH = {"birth_date": "1990-03-15", "birth_time": "14:30", "birth_location": LOC}


def test_south_node_is_exactly_opposite_the_north_node() -> None:
    for iso in ("2026-01-01T00:00:00Z", "2026-07-26T12:00:00Z", "1990-03-15T10:30:00Z"):
        jd = to_jd(iso)
        nn, _ = calc_planet(jd, PLANET_IDS["NN"])
        sn, _ = calc_planet(jd, PLANET_IDS["SN"])
        assert (sn - nn) % 360 == pytest.approx(180.0, abs=1e-6)


def test_both_nodes_regress_together() -> None:
    """SN's speed used to be negated, reporting it direct while NN retrograded."""
    jd = to_jd("2026-07-26T12:00:00Z")
    _, nn_speed = calc_planet(jd, PLANET_IDS["NN"])
    _, sn_speed = calc_planet(jd, PLANET_IDS["SN"])
    assert sn_speed == pytest.approx(nn_speed)

    points = calc_all_planets(jd)
    assert points["SN"].retrograde == points["NN"].retrograde
    assert points["SN"].speed == pytest.approx(points["NN"].speed)


def test_south_node_is_accepted_as_a_transiting_body() -> None:
    """The reported failure: eclipse-season search returned UNKNOWN_PLANET."""
    result = find_aspect_exact_dates(
        planet1="Su", planet2="SN", aspect="Cnj",
        date_from="2026-01-01", date_to="2026-12-31",
        mode="transit-to-transit", orb=1.0,
    )
    assert result["occurrences"], "expected a Sun-South Node conjunction in 2026"


def test_conjunction_to_sn_equals_opposition_to_nn() -> None:
    """The two phrasings describe the same moment, so they must agree."""
    to_sn = find_aspect_exact_dates(
        planet1="Su", planet2="SN", aspect="Cnj",
        date_from="2026-01-01", date_to="2026-12-31",
        mode="transit-to-transit", orb=1.0,
    )
    to_nn = find_aspect_exact_dates(
        planet1="Su", planet2="NN", aspect="Opp",
        date_from="2026-01-01", date_to="2026-12-31",
        mode="transit-to-transit", orb=1.0,
    )
    assert ([o["exact_date"] for o in to_sn["occurrences"]]
            == [o["exact_date"] for o in to_nn["occurrences"]])


def test_south_node_works_as_the_first_body_too() -> None:
    result = find_aspect_exact_dates(
        planet1="SN", planet2="Su", aspect="Cnj",
        date_from="2026-01-01", date_to="2026-12-31",
        mode="transit-to-transit", orb=1.0,
    )
    assert result["occurrences"]


def test_south_node_works_against_a_natal_point() -> None:
    result = find_aspect_exact_dates(
        planet1="Ma", planet2="SN", aspect="Cnj",
        date_from="2026-01-01", date_to="2026-12-31",
        mode="transit-to-natal", orb=1.0, **BIRTH,
    )
    assert result["occurrences"]


def test_south_node_is_available_from_the_ephemeris() -> None:
    result = get_ephemeris(planet=["NN", "SN"], date_from="2026-07-26",
                           date_to="2026-07-26")
    rows = result["rows_by_planet"]
    assert rows["SN"][0]["deg"] == pytest.approx((rows["NN"][0]["deg"] + 180) % 360, abs=0.01)
    assert rows["SN"][0]["R"] == rows["NN"][0]["R"]


def test_transit_events_do_not_duplicate_the_nodal_axis() -> None:
    """SN contacts mirror NN contacts; listing both doubles the nodal rows."""
    result = calculate_transits(transit_date="2026-07-26", period_days=30, **BIRTH)
    assert "SN" in result["transit_planets"]
    assert "SN" not in {e["tp"] for e in result["aspect_events"]}
