"""Tool 14: calculate_antiscia."""

from __future__ import annotations

from typing import Any

from astro_mcp.core.ephemeris_provider import (
    angular_distance,
    build_chart_point,
    calc_all_planets,
    to_jd,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.formatters import serialize_point
from astro_mcp.core.models import ANGLE_KEYS
from astro_mcp.tools.natal import compute_natal

# Antiscia mirror about the 0 Cancer / 0 Capricorn (solstitial) axis.
ANTISCIA_AXIS = 90.0
# Contra-antiscia mirror about the 0 Aries / 0 Libra (equinoctial) axis.
CONTRA_AXIS = 0.0


def antiscion(lon: float) -> float:
    """Reflection across the solstice axis: 90 - lon (mod 360)."""
    return (ANTISCIA_AXIS * 2 - lon) % 360


def contra_antiscion(lon: float) -> float:
    """Reflection across the equinox axis: 360 - lon (mod 360)."""
    return (CONTRA_AXIS * 2 - lon) % 360


def _transit_contacts(
    mirrors: dict[str, dict[str, dict[str, Any]]],
    transit_date: str,
    orb: float,
) -> list[dict[str, Any]]:
    """Transiting planets conjunct the natal antiscia on a given date.

    Only conjunctions are reported: an antiscion is a mirrored degree, and the
    tradition treats contact with it as a conjunction rather than as a full
    aspect set.
    """
    try:
        jd = to_jd(f"{transit_date}T12:00:00+00:00")
    except ValueError as exc:
        raise AstroError(
            "INVALID_DATE",
            f"Could not parse include_transits_date '{transit_date}'.",
            hint="Use YYYY-MM-DD.",
        ) from exc

    transiting = calc_all_planets(jd)
    hits: list[dict[str, Any]] = []
    for kind, mirror in mirrors.items():
        for m_code, m_data in mirror.items():
            for t_code, t_pt in transiting.items():
                o = angular_distance(m_data["deg"], t_pt.lon_decimal)
                if o <= orb:
                    hits.append({
                        "transit": t_code,
                        "kind": kind,
                        "contacts": m_code,
                        "orb": round(o, 2),
                    })
    hits.sort(key=lambda h: float(h["orb"]))
    return hits


def calculate_antiscia(
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_location: str | dict[str, Any] | None = None,
    orb: float = 1.5,
    house_system: str = "P",
    degree_format: str = "dms",
    include_contra: bool = True,
    include_transits_date: str | None = None,
) -> dict[str, Any]:
    """Tool 14: Antiscia and contra-antiscia points plus their natal contacts."""
    if not (birth_date and birth_time and birth_location):
        raise AstroError(
            "INPUT_ERROR",
            "birth_date, birth_time and birth_location are required.",
        )
    if orb <= 0:
        raise AstroError("INPUT_ERROR", "orb must be greater than 0.")

    chart = compute_natal(birth_date, birth_time, birth_location, house_system)
    points = chart.all_points

    antiscia: dict[str, dict[str, Any]] = {}
    contra: dict[str, dict[str, Any]] = {}

    for code, pt in points.items():
        if code in ANGLE_KEYS:
            continue
        a_lon = antiscion(pt.lon_decimal)
        antiscia[code] = serialize_point(
            build_chart_point(a_lon, pt.speed, chart.cusps), degree_format
        )
        if include_contra:
            c_lon = contra_antiscion(pt.lon_decimal)
            contra[code] = serialize_point(
                build_chart_point(c_lon, pt.speed, chart.cusps), degree_format
            )

    def _contacts(mirror: dict[str, dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for m_code, m_data in mirror.items():
            m_lon = m_data["deg"]
            for n_code, n_pt in points.items():
                if n_code == m_code:
                    continue
                o = angular_distance(m_lon, n_pt.lon_decimal)
                if o <= orb:
                    hits.append({
                        "point": m_code,
                        "kind": kind,
                        "contacts": n_code,
                        "orb": round(o, 2),
                    })
        hits.sort(key=lambda h: float(h["orb"]))
        return hits

    result: dict[str, Any] = {
        "orb_used": orb,
        "antiscia": antiscia,
        "contacts": _contacts(antiscia, "antiscion"),
    }
    if include_contra:
        result["contra_antiscia"] = contra
        result["contacts"].extend(_contacts(contra, "contra-antiscion"))
        result["contacts"].sort(key=lambda h: float(h["orb"]))

    if include_transits_date:
        mirrors = {"antiscion": antiscia}
        if include_contra:
            mirrors["contra-antiscion"] = contra
        hits = _transit_contacts(mirrors, include_transits_date, orb)
        if hits:
            result["transit_contacts"] = hits
        result["transits_date"] = include_transits_date
        result["transits_note"] = (
            "Transit positions taken at 12:00 UTC on transits_date. Antiscion "
            "contacts are conjunctions to the mirrored degree by tradition."
        )

    if chart.house_system_warning:
        result["house_system_warning"] = chart.house_system_warning
    return result
