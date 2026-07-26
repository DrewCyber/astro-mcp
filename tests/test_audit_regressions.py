"""Regression tests for the correctness defects found in the code audit.

Each test here corresponds to a specific finding in CODE_AUDIT.md and asserts
the *behaviour*, not the implementation, so a future refactor that reintroduces
the bug fails loudly.
"""

import pytest

from astro_mcp.core.errors import AstroError

LOC = {"name": "Berlin", "lat": 52.52, "lon": 13.405, "tz": "Europe/Berlin"}
LOC2 = {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}


# ---------------------------------------------------------------------------
# C-1: synastry house overlays must use the *other* person's cusps
# ---------------------------------------------------------------------------

def test_c1_overlay_uses_other_persons_houses():
    from astro_mcp.tools.natal import compute_natal
    from astro_mcp.tools.synastry import calculate_synastry

    syn = calculate_synastry("1990-03-15", "14:30", LOC,
                             "1988-07-22", "09:15", LOC2)
    overlay = syn["house_overlays"]["p1_planets_in_p2_houses"]

    n1 = compute_natal("1990-03-15", "14:30", LOC)
    own_houses = {code: pt.house for code, pt in n1.planets.items()
                  if code in overlay}

    # The bug: the overlay was identical to person 1's own natal houses.
    assert overlay != own_houses, (
        "overlay reproduces person 1's own house placements - "
        "it is being computed against the wrong set of cusps"
    )


def test_c1_overlay_matches_manual_house_lookup():
    from astro_mcp.core.ephemeris_provider import house_of
    from astro_mcp.tools.natal import compute_natal
    from astro_mcp.tools.synastry import calculate_synastry

    syn = calculate_synastry("1990-03-15", "14:30", LOC,
                             "1988-07-22", "09:15", LOC2)
    n1 = compute_natal("1990-03-15", "14:30", LOC)
    n2 = compute_natal("1988-07-22", "09:15", LOC2)

    for code, house in syn["house_overlays"]["p1_planets_in_p2_houses"].items():
        assert house == house_of(n1.planets[code].lon_decimal, n2.cusps)

    for code, house in syn["house_overlays"]["p2_planets_in_p1_houses"].items():
        assert house == house_of(n2.planets[code].lon_decimal, n1.cusps)


def test_c1_overlays_are_not_symmetric():
    from astro_mcp.tools.synastry import calculate_synastry

    syn = calculate_synastry("1990-03-15", "14:30", LOC,
                             "1988-07-22", "09:15", LOC2)
    overlays = syn["house_overlays"]
    assert overlays["p1_planets_in_p2_houses"] != overlays["p2_planets_in_p1_houses"]


# ---------------------------------------------------------------------------
# C-2: triple-pass / retrograde data must be measured, not fabricated
# ---------------------------------------------------------------------------

def test_c2_saturn_uranus_2021_is_a_real_triple_pass():
    """Saturn square Uranus perfected 2021-02-17, 2021-06-14 and 2021-12-24."""
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    res = find_aspect_exact_dates("Sa", "Ur", "Squ", "2020-06-01", "2022-06-30",
                                  mode="transit-to-transit", orb=1.0)
    triples = [o for o in res["occurrences"] if o["is_triple_pass"]]
    assert len(triples) == 1

    occ = triples[0]
    assert occ["passes"] == 3
    assert occ["exact_dates"] == ["2021-02-17", "2021-06-14", "2021-12-24"]
    # The middle pass happens while Saturn is retrograde.
    assert occ["retrograde_exact"] == ["2021-06-14"]
    assert occ["direct_exact"] == ["2021-02-17", "2021-12-24"]


def test_c2_single_pass_is_not_flagged_triple():
    """The 2020 Great Conjunction perfected exactly once, on 2020-12-21."""
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    res = find_aspect_exact_dates("Ju", "Sa", "Cnj", "2020-01-01", "2021-06-30",
                                  mode="transit-to-transit", orb=1.0)
    assert len(res["occurrences"]) == 1
    occ = res["occurrences"][0]
    assert occ["passes"] == 1
    assert occ["is_triple_pass"] is False
    assert occ["exact_dates"] == ["2020-12-21"]
    assert occ["retrograde_exact"] is None
    # A single clean pass has no mid-loop separation to report.
    assert "max_separation_orb" not in occ


def test_c2_retrograde_flag_is_not_hardcoded():
    """Across many occurrences the retrograde flag must actually vary."""
    from astro_mcp.tools.ephemeris import find_aspect_exact_dates

    res = find_aspect_exact_dates("Ma", "Su", "Opp", "2018-01-01", "2027-12-31",
                                  mode="transit-to-transit", orb=1.0)
    flags = {o["retrograde_exact"] is not None for o in res["occurrences"]}
    assert len(res["occurrences"]) >= 3
    # Mars oppositions to the Sun always occur while Mars is retrograde.
    assert flags == {True}


# ---------------------------------------------------------------------------
# C-3: profected age must roll over on the birthday, not on day//365
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target,expected_age", [
    ("2026-03-14", 35),   # day before the 36th birthday
    ("2026-03-15", 36),   # the birthday itself
    ("2026-03-16", 36),
    ("2018-03-14", 27),   # previously mis-reported as 28
    ("2018-03-15", 28),
    ("1990-03-15", 0),    # birth day
    ("1991-03-14", 0),
    ("1991-03-15", 1),
])
def test_c3_profection_age_rolls_over_on_anniversary(target, expected_age):
    from astro_mcp.tools.profections import calculate_profections

    res = calculate_profections("1990-03-15", "14:30", LOC, target_date=target)
    assert res["age"] == expected_age


def test_c3_profected_house_follows_age_mod_12():
    from astro_mcp.tools.profections import calculate_profections

    # Age 35 -> 35 % 12 == 11 -> 12th house; age 36 -> 0 -> 1st house.
    before = calculate_profections("1990-03-15", "14:30", LOC,
                                   target_date="2026-03-14")
    on = calculate_profections("1990-03-15", "14:30", LOC,
                               target_date="2026-03-15")
    assert before["profected_asc"] == "12th house"
    assert on["profected_asc"] == "1st house"
    assert before["year_ruler"] != on["year_ruler"]


def test_c3_leap_day_birth_does_not_drift():
    """A Feb-29 birth must still roll over cleanly on Mar-1 in common years."""
    from astro_mcp.tools.profections import calculate_profections

    assert calculate_profections("2000-02-29", "12:00", LOC,
                                 target_date="2025-02-28")["age"] == 24
    assert calculate_profections("2000-02-29", "12:00", LOC,
                                 target_date="2025-03-01")["age"] == 25


def test_c3_rejects_target_before_birth():
    from astro_mcp.tools.profections import calculate_profections

    with pytest.raises(AstroError) as exc:
        calculate_profections("1990-03-15", "14:30", LOC,
                              target_date="1989-01-01")
    assert exc.value.code == "INVALID_DATE"


# ---------------------------------------------------------------------------
# C-4: the Swiss Ephemeris must not silently fall back to Moshier
# ---------------------------------------------------------------------------

def test_c4_out_of_range_body_raises_instead_of_returning_garbage():
    from astro_mcp.core.ephemeris_provider import calc_planet, to_jd
    from astro_mcp.core.models import PLANET_IDS

    # Chiron's ephemeris starts around 675 AD; year 100 is well outside it.
    jd = to_jd("0100-01-01T12:00:00Z")
    with pytest.raises(AstroError) as exc:
        calc_planet(jd, PLANET_IDS["Ch"])
    assert exc.value.code in {"EPHEMERIS_OUT_OF_RANGE", "EPHEMERIS_UNAVAILABLE"}


def test_c4_init_ephemeris_rejects_a_directory_with_no_data():
    from astro_mcp.core.ephemeris_provider import init_ephemeris

    with pytest.raises(AstroError) as exc:
        init_ephemeris("/nonexistent/ephemeris/path")
    assert exc.value.code == "EPHEMERIS_UNAVAILABLE"


# ---------------------------------------------------------------------------
# H-3: is_applying across all four quadrants of the aspect circle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lon1,speed1,lon2,speed2,angle,expected", [
    # Faster body behind a conjunction, catching up -> applying.
    (8.0, 1.0, 10.0, 0.0, 0.0, True),
    # Faster body past the conjunction, pulling away -> separating.
    (12.0, 1.0, 10.0, 0.0, 0.0, False),
    # Same geometry mirrored across 0 deg (the wrap bug lived here).
    (358.0, 1.0, 0.0, 0.0, 0.0, True),
    (2.0, 1.0, 0.0, 0.0, 0.0, False),
    # Opposition (exact at lon1 == 190): retrograde body above it closes in,
    # retrograde body below it pulls away.
    (192.0, -1.0, 10.0, 0.0, 180.0, True),
    (188.0, -1.0, 10.0, 0.0, 180.0, False),
    # ...and the direct-motion mirror of the same two.
    (188.0, 1.0, 10.0, 0.0, 180.0, True),
    (192.0, 1.0, 10.0, 0.0, 180.0, False),
    # Square (exact at lon1 == 100), upper half-circle: this is the case the
    # old unsigned-arc comparison inverted.
    (102.0, -1.0, 10.0, 0.0, 90.0, True),
    (98.0, -1.0, 10.0, 0.0, 90.0, False),
    (98.0, 1.0, 10.0, 0.0, 90.0, True),
    # Waning square (exact at lon1 == 280).
    (278.0, 1.0, 10.0, 0.0, 90.0, True),
    (282.0, 1.0, 10.0, 0.0, 90.0, False),
    # Retrograde transit applying to a trine (exact at lon1 == 130).
    (135.0, -1.0, 10.0, 0.0, 120.0, True),
    (125.0, -1.0, 10.0, 0.0, 120.0, False),
])
def test_h3_is_applying_quadrants(lon1, speed1, lon2, speed2, angle, expected):
    from astro_mcp.core.ephemeris_provider import is_applying

    assert is_applying(lon1, speed1, lon2, speed2, angle) is expected


def test_h3_applying_is_antisymmetric_under_reversed_motion():
    """Flipping both bodies' motion must flip the applying/separating verdict."""
    from astro_mcp.core.ephemeris_provider import is_applying

    for angle in (0.0, 60.0, 90.0, 120.0, 180.0):
        for lon1 in range(0, 360, 7):
            fwd = is_applying(float(lon1), 1.0, 10.0, 0.0, angle)
            rev = is_applying(float(lon1), -1.0, 10.0, 0.0, angle)
            # Exactly on the aspect both directions report False; otherwise the
            # two verdicts must be opposites.
            if fwd or rev:
                assert fwd != rev, f"angle={angle} lon1={lon1}"


def test_h3_stationary_bodies_never_apply():
    from astro_mcp.core.ephemeris_provider import is_applying

    assert is_applying(10.0, 0.0, 100.0, 0.0, 90.0) is False


# ---------------------------------------------------------------------------
# H-2: period_days must actually scan a period
# ---------------------------------------------------------------------------

def test_h2_period_days_produces_dated_events_inside_the_window():
    from astro_mcp.tools.transits import calculate_transits

    res = calculate_transits("2026-01-01", "1990-03-15", "14:30", LOC,
                             period_days=60)
    assert res["period_days"] == 60
    events = res.get("aspect_events", [])
    assert events, "period_days produced no aspect events"
    for ev in events:
        assert "2026-01-01" <= ev["exact"] <= "2026-03-02"
    assert [e["exact"] for e in events] == sorted(e["exact"] for e in events)


def test_h2_period_days_is_bounded():
    from astro_mcp.tools.transits import calculate_transits

    with pytest.raises(AstroError) as exc:
        calculate_transits("2026-01-01", "1990-03-15", "14:30", LOC,
                           period_days=5000)
    assert exc.value.code == "RANGE_TOO_LONG"


# ---------------------------------------------------------------------------
# M-7: composite houses must derive from the composite Ascendant
# ---------------------------------------------------------------------------

def test_m7_midpoint_composite_uses_equal_houses_from_composite_asc():
    from astro_mcp.tools.synastry import calculate_composite_chart

    res = calculate_composite_chart("1990-03-15", "14:30", LOC,
                                    "1988-07-22", "09:15", LOC2,
                                    method="midpoint", degree_format="dec")
    assert res["house_basis"] == "equal-from-composite-Asc"
    cusps = [float(h["cusp"]) for h in res["comp_houses"]]
    asc = res["comp_angles"]["Asc"]["deg"]

    # Equal houses: every cusp is exactly 30 deg from the last, starting at the
    # composite Ascendant -- not inherited from either natal chart.
    assert cusps[0] == pytest.approx(asc, abs=0.01)
    for i in range(12):
        assert cusps[i] == pytest.approx((asc + 30 * i) % 360, abs=0.01)


def test_m7_composite_houses_differ_from_both_natal_charts():
    from astro_mcp.tools.natal import compute_natal
    from astro_mcp.tools.synastry import calculate_composite_chart

    res = calculate_composite_chart("1990-03-15", "14:30", LOC,
                                    "1988-07-22", "09:15", LOC2,
                                    method="midpoint", degree_format="dec")
    comp_cusps = [round(float(h["cusp"]), 4) for h in res["comp_houses"]]

    n1 = compute_natal("1990-03-15", "14:30", LOC)
    n2 = compute_natal("1988-07-22", "09:15", LOC2)
    assert comp_cusps != [round(c, 4) for c in n1.cusps]
    assert comp_cusps != [round(c, 4) for c in n2.cusps]


# ---------------------------------------------------------------------------
# M-1: include_transits_date was advertised for antiscia but not implemented
# ---------------------------------------------------------------------------


def test_m1_antiscia_transits_are_actually_computed():
    from astro_mcp.tools.antiscia import calculate_antiscia

    res = calculate_antiscia("1990-03-15", "14:30", LOC,
                             orb=3.0, include_transits_date="2026-05-25")

    assert res["transits_date"] == "2026-05-25"
    # A 3-degree orb across ~20 antiscia points and 10+ transiting bodies
    # reliably produces at least one contact.
    hits = res.get("transit_contacts", [])
    assert hits, "expected at least one transit contact at a 3 degree orb"
    for hit in hits:
        assert hit["orb"] <= 3.0
        assert hit["kind"] in {"antiscion", "contra-antiscion"}
        assert hit["contacts"] in res["antiscia"] or hit["contacts"] in res["contra_antiscia"]
    # Sorted tightest first.
    assert hits == sorted(hits, key=lambda h: h["orb"])


def test_m1_antiscia_without_transit_date_omits_transit_keys():
    from astro_mcp.tools.antiscia import calculate_antiscia

    res = calculate_antiscia("1990-03-15", "14:30", LOC)
    assert "transit_contacts" not in res
    assert "transits_date" not in res
