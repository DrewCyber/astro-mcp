"""Regression tests for the review fixes: aspect modes and bisection.

Two independent classes so the fixes can be committed separately:

* ``TestFindAspectsModes`` — the ``cross_chart`` / ``fixed_target`` keyword
  modes of :func:`find_aspects` (same-key cross-chart contacts, frozen-target
  applying) and their caller wiring in synastry/transits/progressions.
* ``TestBisectionDiscontinuity`` — residual validation in
  :func:`find_exact_aspect_jd` against false roots at the 180-degree
  discontinuity and endpoint exactness.
"""

from __future__ import annotations

import inspect

from astro_mcp.core.ephemeris_provider import (
    angular_distance,
    aspect_delta,
    build_chart_point,
    calc_planet,
    find_aspects,
    find_exact_aspect_jd,
    pid_for,
    to_jd,
)
from astro_mcp.core.models import ASPECT_ANGLES, ChartPoint
from astro_mcp.tools.natal import compute_natal

# Simple contemporary chart (same data as tests/conftest.py, restated here so
# this module imports standalone).
MODERN_BIRTH = {
    "birth_date": "1990-03-15",
    "birth_time": "14:30",
    "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
}

# An epoch in 2023; the Moon is always direct, so its separation from a
# static target grows monotonically and wraps predictably.
JD0 = 2460000.0


def _pt(lon: float, speed: float) -> ChartPoint:
    return build_chart_point(lon, speed)


class TestFindAspectsModes:
    """Same-key contacts and fixed-target applying."""

    def test_same_key_omitted_by_default(self):
        pts = {"Su": _pt(0.0, 1.0), "Mo": _pt(179.5, 12.0)}
        pairs = {(a.point1, a.point2) for a in find_aspects(pts, pts)}
        assert ("Su", "Su") not in pairs
        assert ("Mo", "Mo") not in pairs
        # Intra-chart contact between different points still reported.
        assert any({"Su", "Mo"} == {p1, p2} for p1, p2 in pairs)

    def test_cross_chart_keeps_same_key_contacts(self):
        a = {"Su": _pt(0.0, 1.0)}
        b = {"Su": _pt(1.0, 1.0)}
        aspects = find_aspects(a, b, cross_chart=True)
        assert [(x.point1, x.point2, x.aspect_type) for x in aspects] == [
            ("Su", "Su", "Cnj")
        ]

    def test_new_modes_are_keyword_only(self):
        params = inspect.signature(find_aspects).parameters
        assert params["cross_chart"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["fixed_target"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["cross_chart"].default is False
        assert params["fixed_target"].default is False

    def test_fixed_target_applying_uses_moving_body_only(self):
        # Mover crawls toward the natal point, but the natal-speed target
        # recedes faster: with the natal speed the pair reads as separating,
        # against a frozen target it is applying.
        moving = {"Pl": _pt(10.0, 0.05)}
        frozen = {"Su": _pt(11.0, 1.0)}
        with_natal_speed = find_aspects(moving, frozen, cross_chart=True)
        assert all(not a.applying for a in with_natal_speed)
        fixed = find_aspects(moving, frozen, cross_chart=True, fixed_target=True)
        assert all(a.applying for a in fixed)

    def test_fixed_target_exact_conjunction_is_neither(self):
        moving = {"Ma": _pt(20.0, 0.5)}
        frozen = {"Su": _pt(20.0, 0.0)}
        aspects = find_aspects(moving, frozen, cross_chart=True, fixed_target=True)
        assert all(not a.applying for a in aspects)

    def test_synastry_identical_charts_include_same_key_aspects(self):
        from astro_mcp.tools.synastry import calculate_synastry
        result = calculate_synastry(
            person1_date=MODERN_BIRTH["birth_date"],
            person1_time=MODERN_BIRTH["birth_time"],
            person1_location=MODERN_BIRTH["birth_location"],
            person2_date=MODERN_BIRTH["birth_date"],
            person2_time=MODERN_BIRTH["birth_time"],
            person2_location=MODERN_BIRTH["birth_location"],
        )
        same_key = [a for a in result["aspects"] if a["p1_planet"] == a["p2_planet"]]
        # Identical charts: every point conjuncts its twin exactly. These rows
        # vanished entirely before cross_chart was passed by the caller.
        assert {"Su", "Mo"} <= {a["p1_planet"] for a in same_key}
        assert all(a["orb"] == 0.0 for a in same_key)

    def test_transits_include_same_key_contacts(self):
        from astro_mcp.tools.transits import calculate_transits
        # A snapshot at the birth moment reproduces the natal positions, so
        # Su-Su / Mo-Mo must appear (they were silently dropped before).
        result = calculate_transits(
            transit_date=MODERN_BIRTH["birth_date"],
            **MODERN_BIRTH,
            transit_time=MODERN_BIRTH["birth_time"],
            max_orb=None,
        )
        same_key = {a["tp"] for a in result["aspects"] if a["tp"] == a["np"]}
        assert {"Su", "Mo"} <= same_key

    def test_solar_return_sun_conjunct_natal_sun(self):
        from astro_mcp.tools.returns import calculate_solar_return
        sr = calculate_solar_return(
            birth_date=MODERN_BIRTH["birth_date"],
            birth_time=MODERN_BIRTH["birth_time"],
            birth_location=MODERN_BIRTH["birth_location"],
            year=2000,
        )
        sun_rows = [a for a in sr["sr_to_natal_aspects"]
                    if a["sp"] == "Su" and a["np"] == "Su"]
        assert sun_rows
        assert sun_rows[0]["asp"] == "Cnj"
        assert sun_rows[0]["orb"] == 0.0

    def test_progressions_report_prog_to_natal_rows(self):
        from astro_mcp.tools.progressions import calculate_secondary_progressions
        prog = calculate_secondary_progressions(
            birth_date=MODERN_BIRTH["birth_date"],
            birth_time=MODERN_BIRTH["birth_time"],
            birth_location=MODERN_BIRTH["birth_location"],
            progression_date="2000-03-15",
            max_orb=None,
        )
        assert prog["prog_to_natal_aspects"]
        # Every row carries an applying flag computed against the frozen
        # natal target (natal speed ignored), i.e. the fixed_target mode.
        assert all("apply" in row for row in prog["prog_to_natal_aspects"])

    def test_transit_events_window_still_scans(self):
        from astro_mcp.tools.transits import calculate_transits
        result = calculate_transits(
            transit_date="2000-03-15",
            **MODERN_BIRTH,
            period_days=3,
            moon_events="all",
        )
        events = result["aspect_events"]
        assert events
        # Events are date-stamped; each reported date must be inside the
        # scanned window and must contain a real perfection: sampled hourly
        # across that UTC day, the aspect delta must pass through ~0.
        chart = compute_natal(**MODERN_BIRTH)
        window_start = to_jd("2000-03-15T00:00:00Z")
        window_end = window_start + 3.0
        for ev in events:
            day0 = to_jd(f"{ev['exact']}T00:00:00Z")
            assert window_start <= day0 < window_end
            natal_lon = chart.all_points[ev["np"]].lon_decimal
            deltas = [
                abs(aspect_delta(
                    calc_planet(day0 + h / 24.0, pid_for(ev["tp"]))[0],
                    natal_lon,
                    ASPECT_ANGLES[ev["asp"]],
                ))
                for h in range(25)
            ]
            assert min(deltas) < 0.7, (ev, min(deltas))


class TestBisectionDiscontinuity:
    """False roots at the 180-degree branch cut and endpoint exactness."""

    def test_wrap_bracket_without_true_root_returns_none(self):
        # The Moon moves forward; place the target 180.5 deg AHEAD of it, so
        # the Moon is 179.5 deg ahead of the target and still advancing. The
        # signed conjunction delta wraps from ~+179.5 to ~-177 within hours --
        # a sign change with no perfection anywhere in the bracket.
        lon_moon, _ = calc_planet(JD0, pid_for("Mo"))
        target = (lon_moon + 180.5) % 360
        jd1 = JD0 + 0.3
        lon_moon1, _ = calc_planet(jd1, pid_for("Mo"))
        d0 = aspect_delta(lon_moon, target, 0.0)
        d1 = aspect_delta(lon_moon1, target, 0.0)
        assert d0 > 170 and d1 < -170, "test setup: bracket must contain the wrap"
        assert find_exact_aspect_jd(
            pid_for("Mo"), None, 0.0, JD0, jd1, natal_lon2=target,
        ) is None

    def test_endpoint_exactness_returns_the_endpoint(self):
        lon_sun, _ = calc_planet(JD0, pid_for("Su"))
        # Exact at the start of the bracket.
        assert find_exact_aspect_jd(
            pid_for("Su"), None, 0.0, JD0, JD0 + 5.0, natal_lon2=lon_sun,
        ) == JD0
        # Exact at the end of the bracket.
        assert find_exact_aspect_jd(
            pid_for("Su"), None, 0.0, JD0 - 5.0, JD0, natal_lon2=lon_sun,
        ) == JD0

    def test_true_conjunction_root_still_found(self):
        # Moon 6 deg behind a static target: a real conjunction ~11 hours on.
        lon_moon, _ = calc_planet(JD0, pid_for("Mo"))
        target = (lon_moon + 6.0) % 360
        root = find_exact_aspect_jd(
            pid_for("Mo"), None, 0.0, JD0, JD0 + 1.0, natal_lon2=target,
        )
        assert root is not None
        lon_at_root, _ = calc_planet(root, pid_for("Mo"))
        assert angular_distance(lon_at_root, target) < 1e-3

    def _first_crossing(self, pid1: int, pid2: int, asp_angle: float,
                        jd_start: float, days: int) -> float | None:
        """Daily scan (as the production scanners do) + bisection."""
        prev: float | None = None
        for day in range(days + 1):
            jd = jd_start + day
            lon1, _ = calc_planet(jd, pid1)
            lon2, _ = calc_planet(jd, pid2)
            delta = aspect_delta(lon1, lon2, asp_angle)
            if (prev is not None and prev * delta < 0
                    and abs(prev - delta) < 180):
                return find_exact_aspect_jd(
                    pid1, pid2, asp_angle, jd - 1.0, jd,
                )
            prev = delta
        return None

    def test_dynamic_pair_conjunction_is_a_real_synodic_hit(self):
        # Moon-Sun conjunction (New Moon) must occur within 30 days; the
        # residual validation must keep exactly that root, not a wrap artefact.
        root = self._first_crossing(pid_for("Mo"), pid_for("Su"), 0.0,
                                    JD0, 30)
        assert root is not None
        lon_moon, _ = calc_planet(root, pid_for("Mo"))
        lon_sun, _ = calc_planet(root, pid_for("Su"))
        assert angular_distance(lon_sun, lon_moon) < 1e-4

    def test_opposition_root_survives_validation(self):
        # A genuine 180-degree aspect must not be discarded by the new
        # residual check: bracket a real Moon-Sun opposition (Full Moon).
        root = self._first_crossing(pid_for("Mo"), pid_for("Su"), 180.0,
                                    JD0, 30)
        assert root is not None
        lon_moon, _ = calc_planet(root, pid_for("Mo"))
        lon_sun, _ = calc_planet(root, pid_for("Su"))
        assert abs(angular_distance(lon_sun, lon_moon) - 180.0) < 1e-4

    def test_no_crossing_returns_none(self):
        # The Sun drifts ~1 deg/day; a static target 90 deg ahead is never
        # reached inside one day, so there is no conjunction to find.
        lon_sun, _ = calc_planet(JD0, pid_for("Su"))
        target = (lon_sun + 90.0) % 360
        assert find_exact_aspect_jd(
            pid_for("Su"), None, 0.0, JD0, JD0 + 1.0, natal_lon2=target,
        ) is None
