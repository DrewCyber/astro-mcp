"""Tools 7 & 8: calculate_synastry and calculate_composite_chart."""

from __future__ import annotations

import math
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    build_chart_point,
    build_house_cusps,
    calc_all_planets,
    calc_houses,
    find_aspects,
    house_of,
    jd_to_iso,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_house, serialize_point
from astro_mcp.core.models import ANGLE_KEYS, ChartPoint, NatalChart
from astro_mcp.tools.natal import compute_natal, dedupe_aspects

HARMONY_ASPECTS = frozenset({"Cnj", "Tri", "Sex"})

# Points excluded from house-overlay reporting: the angles are properties of
# the houses themselves, and the South Node is derived from the North Node.
_OVERLAY_EXCLUDED = ANGLE_KEYS | {"SN"}


def _resolve_natal(
    birth_date: str | None,
    birth_time: str | None,
    birth_location: str | dict[str, Any] | None,
    house_system: str,
    label: str,
) -> NatalChart:
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            f"{label}_date, {label}_time and {label}_location are required.",
        )
    return compute_natal(birth_date, birth_time, birth_location, house_system)


def _overlay(points: dict[str, ChartPoint], cusps: list[float]) -> dict[str, int]:
    """Which house of the *other* chart each of these points falls into."""
    return {
        code: house_of(pt.lon_decimal, cusps)
        for code, pt in points.items()
        if code not in _OVERLAY_EXCLUDED
    }


def calculate_synastry(
    person1_date: str | None = None,
    person1_time: str | None = None,
    person1_location: str | dict[str, Any] | None = None,
    person2_date: str | None = None,
    person2_time: str | None = None,
    person2_location: str | dict[str, Any] | None = None,
    house_system: str = "P",
    orbs: dict[str, float] | None = None,
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 7: Synastry — cross-aspects and house overlays between two charts."""
    n1 = _resolve_natal(person1_date, person1_time, person1_location, house_system, "person1")
    n2 = _resolve_natal(person2_date, person2_time, person2_location, house_system, "person2")

    pts1 = n1.all_points
    pts2 = n2.all_points

    # Default synastry orbs (slightly tighter)
    default_syn_orbs: dict[str, float] = {
        "Cnj": 7, "Opp": 7, "Tri": 6, "Squ": 6, "Sex": 4,
    }
    used_orbs = orbs or default_syn_orbs

    cross_aspects = find_aspects(
        pts1, pts2, custom_orbs=used_orbs, angle_orb_keys=set(ANGLE_KEYS)
    )

    aspects_out: list[dict[str, Any]] = [
        {
            "p1_planet": a.point1,
            "p2_planet": a.point2,
            "asp": a.aspect_type,
            "orb": a.orb,
            "harmony": a.aspect_type in HARMONY_ASPECTS,
        }
        for a in cross_aspects
    ]

    # House overlays: each person's planets located in the OTHER person's
    # houses.  This is the whole point of the technique, so the cusps must come
    # from the opposite chart.
    p1_in_p2 = _overlay(n1.planets, n2.cusps)
    p2_in_p1 = _overlay(n2.planets, n1.cusps)

    # Davison chart datetime (midpoint of two birth JDs)
    davison_jd = (n1.jd + n2.jd) / 2

    strong_links = [
        f"{a.point1}-{a.point2} {a.aspect_type}"
        for a in cross_aspects
        if a.aspect_type in HARMONY_ASPECTS and a.orb < 3
    ]
    challenges = [
        f"{a.point1}-{a.point2} {a.aspect_type}"
        for a in cross_aspects
        if a.aspect_type not in HARMONY_ASPECTS and a.orb < 3
    ]

    # Tightness-weighted totals: each aspect contributes (max_orb - orb), so a
    # partile aspect counts for much more than one at the edge of orb.  These
    # are relative indicators for comparing charts, not absolute percentages.
    harmony_score = round(
        sum(8 - a.orb for a in cross_aspects if a.aspect_type in HARMONY_ASPECTS), 1
    )
    tension_score = round(
        sum(8 - a.orb for a in cross_aspects if a.aspect_type not in HARMONY_ASPECTS), 1
    )

    return {
        "p1_label": "Person1",
        "p2_label": "Person2",
        "aspects": aspects_out,
        "house_overlays": {
            "p1_planets_in_p2_houses": p1_in_p2,
            "p2_planets_in_p1_houses": p2_in_p1,
        },
        "davison_dt": jd_to_iso(davison_jd),
        "compatibility_indicators": {
            "harmony_score": harmony_score,
            "tension_score": tension_score,
            "scale_note": "Relative tightness-weighted totals; compare across charts, not to 100.",
            "strong_links": strong_links[:5],
            "challenges": challenges[:5],
        },
    }


def _midpoint_lon(lon1: float, lon2: float) -> float:
    """Shorter-arc midpoint of two longitudes.

    The vector mean is undefined for exactly opposed points (atan2(0, 0)); in
    that case either midpoint is equally valid, so the one advancing from the
    first point is chosen deterministically instead of silently collapsing to
    0 degrees Aries.
    """
    r1, r2 = math.radians(lon1), math.radians(lon2)
    avg_sin = (math.sin(r1) + math.sin(r2)) / 2
    avg_cos = (math.cos(r1) + math.cos(r2)) / 2
    if abs(avg_sin) < 1e-12 and abs(avg_cos) < 1e-12:
        return (lon1 + 90.0) % 360
    return math.degrees(math.atan2(avg_sin, avg_cos)) % 360


def _geographic_midpoint(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> tuple[float, float]:
    """Great-circle geographic midpoint of two places.

    Averaging lat/long arithmetically breaks wherever the pair straddles the
    antimeridian (Tokyo x Los Angeles lands near Chad instead of the Arctic)
    or near the poles. Converting both places to unit vectors, averaging, and
    converting back yields the true great-circle midpoint in one shot.

    Exactly antipodal inputs have a whole great circle of valid midpoints;
    the equatorial point advancing from ``lon1`` is returned deterministically.
    """
    la1, lo1 = math.radians(lat1), math.radians(lon1)
    la2, lo2 = math.radians(lat2), math.radians(lon2)
    x1, y1, z1 = math.cos(la1) * math.cos(lo1), math.cos(la1) * math.sin(lo1), math.sin(la1)
    x2, y2, z2 = math.cos(la2) * math.cos(lo2), math.cos(la2) * math.sin(lo2), math.sin(la2)
    x, y, z = (x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2
    if abs(x) < 1e-12 and abs(y) < 1e-12 and abs(z) < 1e-12:
        delta = ((lon2 - lon1 + 540.0) % 360.0) - 180.0
        return 0.0, ((lon1 + delta / 2 + 180.0) % 360.0) - 180.0
    lon_mid = math.degrees(math.atan2(y, x))
    lat_mid = math.degrees(math.atan2(z, math.hypot(x, y)))
    return lat_mid, ((lon_mid + 180.0) % 360.0) - 180.0


def calculate_composite_chart(
    person1_date: str | None = None,
    person1_time: str | None = None,
    person1_location: str | dict[str, Any] | None = None,
    person2_date: str | None = None,
    person2_time: str | None = None,
    person2_location: str | dict[str, Any] | None = None,
    house_system: str = "P",
    method: str = "midpoint",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 8: Composite chart via midpoints or Davison."""
    if method not in {"midpoint", "davison"}:
        raise AstroError("INPUT_ERROR", "method must be 'midpoint' or 'davison'.")

    n1 = _resolve_natal(person1_date, person1_time, person1_location, house_system, "person1")
    n2 = _resolve_natal(person2_date, person2_time, person2_location, house_system, "person2")

    davison_location: dict[str, Any] | None = None
    if method == "davison":
        # Davison: a real chart cast for the midpoint in time and space.
        # The space midpoint is the great-circle one; naive averaging of
        # lat/long places e.g. Tokyo x Los Angeles in the wrong hemisphere.
        dav_jd = (n1.jd + n2.jd) / 2
        lat, lon = _geographic_midpoint(
            n1.geo.lat, n1.geo.lon, n2.geo.lat, n2.geo.lon
        )
        naive_lon = ((n1.geo.lon + n2.geo.lon) / 2 + 180.0) % 360.0 - 180.0
        naive_lat = (n1.geo.lat + n2.geo.lat) / 2
        cusps, ascmc = calc_houses(dav_jd, lat, lon, n1.house_system)
        comp_planets = calc_all_planets(dav_jd, cusps, include_asteroids=False)
        comp_angles = build_angles(ascmc, cusps)
        comp_houses = build_house_cusps(cusps)
        cusp_list = cusps
        davison_location = {
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "tz": "UTC",
        }
        if abs(lat - naive_lat) > 0.5 or abs(lon - naive_lon) > 0.5:
            davison_location["note"] = (
                "great-circle midpoint; differs from the naive coordinate "
                "average because the pair straddles the antimeridian or a pole"
            )
    else:
        # Midpoint composite: every point, including the angles, is the
        # midpoint of the corresponding pair.  Houses must then be derived from
        # the composite MC/Asc — deriving them from a Davison chart instead
        # (as this previously did) leaves the planets' house numbers
        # inconsistent with the composite angles they are reported alongside.
        comp_planets = {
            k: build_chart_point(_midpoint_lon(pt.lon_decimal, n2.planets[k].lon_decimal), 0.0)
            for k, pt in n1.planets.items()
            if k in n2.planets
        }
        comp_asc = _midpoint_lon(n1.angles["Asc"].lon_decimal, n2.angles["Asc"].lon_decimal)
        comp_mc = _midpoint_lon(n1.angles["MC"].lon_decimal, n2.angles["MC"].lon_decimal)
        comp_angles = {
            "Asc": build_chart_point(comp_asc, 0.0),
            "MC": build_chart_point(comp_mc, 0.0),
            "Dsc": build_chart_point((comp_asc + 180) % 360, 0.0),
            "IC": build_chart_point((comp_mc + 180) % 360, 0.0),
        }
        # Equal houses from the composite Ascendant keeps the cusps consistent
        # with the composite angles; quadrant systems are not defined for a
        # chart that has no single time or place.
        cusp_list = [(comp_asc + 30 * i) % 360 for i in range(12)]
        comp_houses = build_house_cusps(cusp_list)

    # Assign each composite planet to a composite house
    comp_planets = {
        k: ChartPoint(
            lon_decimal=pt.lon_decimal,
            sign=pt.sign,
            sign_lon=pt.sign_lon,
            house=house_of(pt.lon_decimal, cusp_list),
            retrograde=pt.retrograde,
            speed=pt.speed,
        )
        for k, pt in comp_planets.items()
    }

    all_comp: dict[str, ChartPoint] = {**comp_planets, **comp_angles}
    comp_aspects = dedupe_aspects(
        find_aspects(all_comp, all_comp, angle_orb_keys={"Asc", "MC"})
    )

    return {
        "method": method,
        "house_basis": "equal-from-composite-Asc" if method == "midpoint" else n1.house_system,
        "davison_location": davison_location,
        "comp_planets": {k: serialize_point(v, degree_format) for k, v in comp_planets.items()},
        "comp_angles": {k: serialize_point(v, degree_format, include_house=False)
                        for k, v in comp_angles.items()},
        "comp_houses": [serialize_house(h, degree_format) for h in comp_houses],
        "comp_aspects": [
            {"p1": a.point1, "p2": a.point2, "asp": a.aspect_type, "orb": a.orb}
            for a in comp_aspects
        ],
    }
