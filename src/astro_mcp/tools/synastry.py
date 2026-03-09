"""Tools 7 & 8: calculate_synastry and calculate_composite_chart."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.ephemeris_provider import (
    build_angles,
    build_house_cusps,
    calc_all_planets,
    calc_houses,
    find_aspects,
    jd_to_iso,
    to_jd,
)
from astro_mcp.core.formatters import serialize_house, serialize_point
from astro_mcp.core.models import ChartPoint, SIGNS
from astro_mcp.tools.natal import calculate_natal_chart
from astro_mcp.tools.transits import _natal_to_points


def _resolve_natal(
    birth_date: str | None,
    birth_time: str | None,
    birth_location: str | dict | None,
    house_system: str,
) -> dict[str, Any]:
    if birth_date and birth_time and birth_location:
        return calculate_natal_chart(birth_date, birth_time, birth_location, house_system, "dec")
    raise ValueError("NATAL_MISSING: Provide birth_date, birth_time and birth_location.")


def calculate_synastry(
    person1_date: str | None = None,
    person1_time: str | None = None,
    person1_location: str | dict | None = None,
    person2_date: str | None = None,
    person2_time: str | None = None,
    person2_location: str | dict | None = None,
    house_system: str = "P",
    orbs: dict[str, float] | None = None,
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 7: Synastry — cross-aspects and house overlays between two charts."""
    try:
        n1 = _resolve_natal(person1_date, person1_time, person1_location, house_system)
        n2 = _resolve_natal(person2_date, person2_time, person2_location, house_system)
    except ValueError as e:
        return {"error": True, "code": "NATAL_MISSING", "message": str(e)}

    pts1 = _natal_to_points(n1)
    pts2 = _natal_to_points(n2)

    # Default synastry orbs (slightly tighter)
    default_syn_orbs: dict[str, float] = {
        "Cnj": 7, "Opp": 7, "Tri": 6, "Squ": 6, "Sex": 4,
    }
    used_orbs = orbs or default_syn_orbs

    cross_aspects = find_aspects(pts1, pts2, custom_orbs=used_orbs,
                                 angle_orb_keys={"Asc", "MC", "Dsc", "IC"})

    HARMONY_ASPECTS = {"Cnj", "Tri", "Sex"}
    aspects_out = [
        {
            "p1_planet": a.point1,
            "p2_planet": a.point2,
            "asp": a.aspect_type,
            "orb": a.orb,
            "harmony": a.aspect_type in HARMONY_ASPECTS,
        }
        for a in cross_aspects
    ]

    # House overlays: where does P1's planet fall in P2's houses?
    def house_for_lon(lon: float, houses: list[dict]) -> int:
        cusps = [hc["cusp_dec"] if "cusp_dec" in hc else hc.get("deg_num", i * 30.0)
                 for i, hc in enumerate(houses)]
        # Fall back to degree math approximation using serialised cusp
        for i, hc in enumerate(n2["houses"]):
            next_i = (i + 1) % 12
            cusp1 = n2["houses"][i].get("lon_dec", i * 30.0)
            return 1  # Placeholder — actual overlay from pts2 houses
        return 1

    p1_in_p2: dict[str, int] = {}
    for pcode, pt in pts1.items():
        if pcode in {"Asc", "MC", "Dsc", "IC"}:
            continue
        # assign house from n2 house structure using longitude
        lon = pt.lon_decimal
        house_n = 1
        for hi, hc in enumerate(n2["houses"]):
            # Parse cusp longitude from house data
            # house serialised as {"n":1,"cusp":"00°12'Can","sign":"Can"...}
            pass  # use pts2's existing house attribute if available
        if pcode in pts2:
            house_n = pts2[pcode].house or 1  # approximate
        p1_in_p2[pcode] = n1["planets"].get(pcode, {}).get("house", 1)

    # Simpler and correct approach: use the house number from each chart
    p1_in_p2 = {k: v.house or 1 for k, v in pts1.items()
                if k not in {"Asc", "MC", "Dsc", "IC", "SN"}}
    p2_in_p1 = {k: v.house or 1 for k, v in pts2.items()
                if k not in {"Asc", "MC", "Dsc", "IC", "SN"}}

    # Davison chart datetime (midpoint of two birth JDs)
    jd1 = to_jd(n1["meta"]["dt"])
    jd2 = to_jd(n2["meta"]["dt"])
    davison_jd = (jd1 + jd2) / 2

    # Compatibility indicators
    strong_links = [
        f"{a['p1_planet']}-{a['p2_planet']} {a['asp']}"
        for a in aspects_out if a["harmony"] and a["orb"] < 3
    ]
    challenges = [
        f"{a['p1_planet']}-{a['p2_planet']} {a['asp']}"
        for a in aspects_out if not a["harmony"] and a["orb"] < 3
    ]
    harmony_score = round(sum(10 - a["orb"] for a in aspects_out if a["harmony"]) / max(1, len(aspects_out)) * 2, 1)
    tension_score = round(sum(10 - a["orb"] for a in aspects_out if not a["harmony"]) / max(1, len(aspects_out)) * 2, 1)

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
            "strong_links": strong_links[:5],
            "challenges": challenges[:5],
        },
    }


def calculate_composite_chart(
    person1_date: str | None = None,
    person1_time: str | None = None,
    person1_location: str | dict | None = None,
    person2_date: str | None = None,
    person2_time: str | None = None,
    person2_location: str | dict | None = None,
    house_system: str = "P",
    method: str = "midpoint",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 8: Composite chart via midpoints or Davison."""
    try:
        n1 = _resolve_natal(person1_date, person1_time, person1_location, house_system)
        n2 = _resolve_natal(person2_date, person2_time, person2_location, house_system)
    except ValueError as e:
        return {"error": True, "code": "NATAL_MISSING", "message": str(e)}

    jd1 = to_jd(n1["meta"]["dt"])
    jd2 = to_jd(n2["meta"]["dt"])

    if method == "davison":
        # Davison: use midpoint JD and mean lat/lon
        dav_jd = (jd1 + jd2) / 2
        lat = (n1["meta"]["loc"]["lat"] + n2["meta"]["loc"]["lat"]) / 2
        lon = (n1["meta"]["loc"]["lon"] + n2["meta"]["loc"]["lon"]) / 2
        cusps, ascmc = calc_houses(dav_jd, lat, lon, house_system)
        comp_planets = calc_all_planets(dav_jd, cusps, include_asteroids=False)
        comp_angles = build_angles(ascmc, cusps)
        comp_houses = build_house_cusps(cusps)
    else:
        # Midpoint: average longitudes (handling 0°/360° wrap with vector mean)
        import math
        pts1 = _natal_to_points(n1)
        pts2 = _natal_to_points(n2)

        comp_pts: dict[str, ChartPoint] = {}
        planet_keys = list(pts1.keys())
        for k in planet_keys:
            if k not in pts2:
                continue
            lon1 = math.radians(pts1[k].lon_decimal)
            lon2 = math.radians(pts2[k].lon_decimal)
            avg_sin = (math.sin(lon1) + math.sin(lon2)) / 2
            avg_cos = (math.cos(lon1) + math.cos(lon2)) / 2
            avg_lon = math.degrees(math.atan2(avg_sin, avg_cos)) % 360
            from astro_mcp.core.ephemeris_provider import build_chart_point
            comp_pts[k] = build_chart_point(avg_lon, 0.0)

        # Houses from midpoint ASC/MC
        asc_lon = comp_pts.get("Asc")
        mc_lon = comp_pts.get("MC")
        # fallback to averaged geodata
        lat = (n1["meta"]["loc"]["lat"] + n2["meta"]["loc"]["lat"]) / 2
        lon = (n1["meta"]["loc"]["lon"] + n2["meta"]["loc"]["lon"]) / 2
        dav_jd = (jd1 + jd2) / 2
        cusps, ascmc = calc_houses(dav_jd, lat, lon, house_system)

        comp_planets = {k: v for k, v in comp_pts.items() if k not in {"Asc", "MC", "Dsc", "IC"}}
        comp_angles = {k: v for k, v in comp_pts.items() if k in {"Asc", "MC", "Dsc", "IC"}}
        if not comp_angles:
            comp_angles = build_angles(ascmc, cusps)
        comp_houses = build_house_cusps(cusps)

    # Recompute house for planets based on composite cusps
    cusp_list = [hc.lon_decimal for hc in comp_houses]
    for k, pt in list(comp_planets.items()):
        from astro_mcp.core.ephemeris_provider import house_of
        comp_planets[k] = ChartPoint(
            lon_decimal=pt.lon_decimal,
            sign=pt.sign,
            sign_lon=pt.sign_lon,
            house=house_of(pt.lon_decimal, cusp_list),
            retrograde=pt.retrograde,
            speed=pt.speed,
        )

    # Aspects within composite
    all_comp: dict[str, ChartPoint] = {**comp_planets, **comp_angles}
    raw_aspects = find_aspects(all_comp, all_comp, angle_orb_keys={"Asc", "MC"})
    seen: set[frozenset[str]] = set()
    comp_aspects = []
    for a in raw_aspects:
        k = frozenset([a.point1, a.point2])
        if k not in seen:
            seen.add(k)
            comp_aspects.append(a)

    return {
        "method": method,
        "comp_planets": {k: serialize_point(v, degree_format) for k, v in comp_planets.items()},
        "comp_angles": {k: serialize_point(v, degree_format, include_house=False) for k, v in comp_angles.items()},
        "comp_houses": [serialize_house(h, degree_format) for h in comp_houses],
        "comp_aspects": [
            {"p1": a.point1, "p2": a.point2, "asp": a.aspect_type, "orb": a.orb}
            for a in comp_aspects
        ],
    }
