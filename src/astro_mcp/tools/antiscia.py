"""Tool 14: calculate_antiscia."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.ephemeris_provider import (
    PLANET_IDS,
    calc_all_planets,
    calc_houses,
    angular_distance,
    to_jd,
)
from astro_mcp.core.formatters import decimal_to_dms
from astro_mcp.core.models import SIGNS, ChartPoint
from astro_mcp.tools.natal import calculate_natal_chart


def _antiscia_lon(lon: float) -> float:
    """
    Antiscia: reflection over the Cancer/Capricorn axis (0° Cancer = 90°).
    Formula: antiscia = 180° - lon  (mod 360)
    Example: 24°45' Pisces (354.75°) → antiscia = 180 - 354.75 = -174.75 → +185.25° = 5°15' Libra
    More precisely: reflect over 90°/270° axis:
      antiscia = (180 - lon) % 360
    """
    return (180.0 - lon) % 360.0


def _contraantiscia_lon(lon: float) -> float:
    """
    Contra-antiscia: reflection over the Aries/Libra axis (0° Aries = 0°).
    Formula: contraantiscia = 360° - lon  (mod 360) = -lon % 360
    """
    return (360.0 - lon) % 360.0


def _lon_to_sign_dms(lon: float) -> str:
    lon = lon % 360
    sign_idx = int(lon // 30)
    sign = SIGNS[sign_idx]
    sign_lon = lon % 30
    return decimal_to_dms(sign_lon) + sign


def calculate_antiscia(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict | None = None,
    include_transits_date: str | None = None,
    house_system: str = "P",
    degree_format: str = "dms",
) -> dict[str, Any]:
    """Tool 14: Antiscia and contra-antiscia for natal planets."""
    if not (birth_date and birth_time and birth_location):
        return {"error": True, "code": "NATAL_MISSING",
                "message": "birth_date, birth_time and birth_location are required."}
    natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, degree_format)

    antiscia_map: dict[str, Any] = {}
    points_to_check = list(natal["planets"].items()) + list(natal["angles"].items())

    for code, pdata in points_to_check:
        natal_lon = pdata["deg"]
        anti_lon = _antiscia_lon(natal_lon)
        contra_lon = _contraantiscia_lon(natal_lon)

        if degree_format == "dms":
            natal_str = _lon_to_sign_dms(natal_lon)
            anti_str = _lon_to_sign_dms(anti_lon)
            contra_str = _lon_to_sign_dms(contra_lon)
        else:
            natal_str = str(round(natal_lon, 2))
            anti_str = str(round(anti_lon, 2))
            contra_str = str(round(contra_lon, 2))

        antiscia_map[code] = {
            "natal_lon": natal_str,
            "antiscia": anti_str,
            "contraantiscia": contra_str,
        }

    # Mutual antiscia aspects between natal planets
    mutual_antiscia: list[dict] = []
    planet_keys = list(natal["planets"].keys())
    for i, k1 in enumerate(planet_keys):
        lon1 = natal["planets"][k1]["deg"]
        anti1 = _antiscia_lon(lon1)
        for k2 in planet_keys[i + 1:]:
            lon2 = natal["planets"][k2]["deg"]
            orb_anti = angular_distance(anti1, lon2)
            if orb_anti <= 1.5:
                mutual_antiscia.append({
                    "p1": k1,
                    "p2": k2,
                    "type": "antiscia_cnj",
                    "orb": round(orb_anti, 2),
                })
            orb_contra = angular_distance(_contraantiscia_lon(lon1), lon2)
            if orb_contra <= 1.5:
                mutual_antiscia.append({
                    "p1": k1,
                    "p2": k2,
                    "type": "contraantiscia_cnj",
                    "orb": round(orb_contra, 2),
                })

    # Transit antiscia aspects
    transit_aspects: list[dict] | None = None
    if include_transits_date:
        jd_tr = to_jd(f"{include_transits_date}T12:00:00Z")
        cusps, _ = calc_houses(jd_tr,
                               natal["meta"]["loc"]["lat"],
                               natal["meta"]["loc"]["lon"], house_system)
        tr_planets = calc_all_planets(jd_tr, cusps, include_asteroids=False)
        transit_aspects = []
        for tr_code, tr_pt in tr_planets.items():
            tr_lon = tr_pt.lon_decimal
            for n_code, n_pdata in natal["planets"].items():
                n_anti = _antiscia_lon(n_pdata["deg"])
                orb_anti = angular_distance(tr_lon, n_anti)
                if orb_anti <= 1.5:
                    transit_aspects.append({
                        "transit": tr_code,
                        "natal": n_code,
                        "type": "transit_to_antiscia",
                        "orb": round(orb_anti, 2),
                    })

    return {
        "antiscia": antiscia_map,
        "mutual_antiscia_aspects": mutual_antiscia,
        "transit_antiscia_aspects": transit_aspects,
    }
