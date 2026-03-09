"""Swiss Ephemeris wrapper — centralises all pyswisseph interactions."""

from __future__ import annotations

import math
import swisseph as swe

from astro_mcp.config import settings
from astro_mcp.core.models import (
    ASPECT_ANGLES,
    DEFAULT_ORBS,
    PLANET_IDS,
    RULERS,
    SIGNS,
    Aspect,
    ChartPoint,
    GeoLocation,
    HouseCusp,
)

# Initialise ephemeris path once at import time
swe.set_ephe_path(settings.ephe_path)


# ---------------------------------------------------------------------------
# Julian Day helpers
# ---------------------------------------------------------------------------

def to_jd(dt_utc: str) -> float:
    """Convert ISO-8601 UTC datetime string to Julian Day number (UT)."""
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(dt_utc.replace("Z", "+00:00"))
    return swe.julday(dt.year, dt.month, dt.day,
                      dt.hour + dt.minute / 60 + dt.second / 3600)


def jd_to_iso(jd: float) -> str:
    """Convert Julian Day to ISO-8601 UTC datetime string."""
    y, mo, d, h = swe.revjul(jd)
    hour = int(h)
    minute = int((h - hour) * 60)
    second = int(((h - hour) * 60 - minute) * 60)
    return f"{y:04d}-{mo:02d}-{d:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"


# ---------------------------------------------------------------------------
# Sign / house utilities
# ---------------------------------------------------------------------------

def lon_to_sign_info(lon: float) -> tuple[str, float]:
    """Return (sign_code, degrees_within_sign)."""
    lon = lon % 360
    idx = int(lon // 30)
    return SIGNS[idx], lon % 30


def house_of(lon: float, cusps: list[float]) -> int:
    """Return house number (1-12) for a given longitude and house cusps list."""
    lon = lon % 360
    for i in range(12):
        cusp_start = cusps[i] % 360
        cusp_end = cusps[(i + 1) % 12] % 360
        if cusp_end > cusp_start:
            if cusp_start <= lon < cusp_end:
                return i + 1
        else:  # crossing 0°
            if lon >= cusp_start or lon < cusp_end:
                return i + 1
    return 1


# ---------------------------------------------------------------------------
# Planet calculation
# ---------------------------------------------------------------------------

def calc_planet(jd: float, planet_id: int) -> tuple[float, float]:
    """Return (longitude, speed_deg_per_day)."""
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    result, _ = swe.calc_ut(jd, planet_id, flags)
    return result[0], result[3]


def build_chart_point(
    longitude: float,
    speed: float,
    cusps: list[float] | None = None,
) -> ChartPoint:
    sign, sign_lon = lon_to_sign_info(longitude)
    h = house_of(longitude, cusps) if cusps else None
    return ChartPoint(
        lon_decimal=round(longitude % 360, 6),
        sign=sign,
        sign_lon=round(sign_lon, 6),
        house=h,
        retrograde=speed < 0,
        speed=round(speed, 4),
    )


def calc_all_planets(
    jd: float,
    cusps: list[float] | None = None,
    include_asteroids: bool = True,
    use_mean_node: bool = False,
    include_lilith: bool = True,
    include_chiron: bool = True,
) -> dict[str, ChartPoint]:
    """Calculate all standard planets.

    Args:
        use_mean_node: If True, NN/SN use Mean Node (swe ID 10) instead of
            True Node (swe ID 11).  Mean Node matches most traditional astrology
            software (e.g. Solar Fire, Astro.com default).
        include_lilith: Include Black Moon Lilith (Mean Apogee, swe ID 12).
        include_chiron: Include Chiron (swe ID 15).
        include_asteroids: Include minor asteroids Ceres, Pallas, Juno, Vesta.
    """
    base_keys = ["Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa", "Ur", "Ne", "Pl"]
    if include_chiron:
        base_keys.append("Ch")
    if include_lilith:
        base_keys.append("Li")
    asteroid_keys = ["Ce", "Pa", "Ju2", "Ve2"] if include_asteroids else []

    # Decide which node ID to use
    nn_key = "NN_m" if use_mean_node else "NN"
    keys = base_keys + [nn_key] + asteroid_keys

    planets: dict[str, ChartPoint] = {}
    for key in keys:
        pid = PLANET_IDS[key]
        lon, speed = calc_planet(jd, pid)
        # Always store under canonical key "NN" regardless of mean/true
        store_key = "NN" if key == "NN_m" else key
        planets[store_key] = build_chart_point(lon, speed, cusps)

    # South Node = NN + 180°
    nn = planets["NN"]
    sn_lon = (nn.lon_decimal + 180) % 360
    planets["SN"] = build_chart_point(sn_lon, -nn.speed, cusps)

    return planets


# ---------------------------------------------------------------------------
# Houses & Angles
# ---------------------------------------------------------------------------

HOUSE_SYSTEM_MAP = {"P": b"P", "W": b"W", "K": b"K"}


def calc_houses(
    jd: float,
    lat: float,
    lon: float,
    house_system: str = "P",
) -> tuple[list[float], list[float]]:
    """
    Return (cusps, ascmc) where cusps[0] is cusp of house 1 .. cusps[11] is cusp of house 12,
    and ascmc contains [ASC, MC, ARMC, Vertex, ...].
    """
    hs = HOUSE_SYSTEM_MAP.get(house_system, b"P")
    cusps_raw, ascmc = swe.houses(jd, lat, lon, hs)
    # pyswisseph returns cusps as a 12-element tuple (house 1 at index 0)
    cusps = list(cusps_raw[:12])
    return cusps, list(ascmc)


def build_angles(ascmc: list[float], cusps: list[float]) -> dict[str, ChartPoint]:
    asc_lon = ascmc[0]
    mc_lon = ascmc[1]
    dsc_lon = (asc_lon + 180) % 360
    ic_lon = (mc_lon + 180) % 360
    return {
        "Asc": build_chart_point(asc_lon, 0.0),
        "MC": build_chart_point(mc_lon, 0.0),
        "Dsc": build_chart_point(dsc_lon, 0.0),
        "IC": build_chart_point(ic_lon, 0.0),
    }


def build_house_cusps(cusps: list[float]) -> list[HouseCusp]:
    result = []
    for i, cusp_lon in enumerate(cusps):
        sign, sign_lon = lon_to_sign_info(cusp_lon)
        ruler, mod_ruler = RULERS[sign]
        result.append(HouseCusp(
            number=i + 1,
            lon_decimal=round(cusp_lon % 360, 6),
            sign=sign,
            ruler=ruler,
            modern_ruler=mod_ruler,
        ))
    return result


# ---------------------------------------------------------------------------
# Aspect calculation
# ---------------------------------------------------------------------------

def angular_distance(lon1: float, lon2: float) -> float:
    """Shortest angular distance between two longitudes [0, 180]."""
    diff = abs((lon1 % 360) - (lon2 % 360))
    if diff > 180:
        diff = 360 - diff
    return diff


def is_applying(lon1: float, speed1: float, lon2: float, speed2: float, asp_angle: float) -> bool:
    """True if the aspect is approaching exactness."""
    diff = (lon1 - lon2) % 360
    relative_speed = speed1 - speed2
    # Check which direction closes the orb
    return (relative_speed < 0 and diff < asp_angle) or (relative_speed > 0 and diff > asp_angle)


def find_aspects(
    points_a: dict[str, ChartPoint],
    points_b: dict[str, ChartPoint],
    orb_factor: float = 1.0,
    angle_orb_keys: set[str] | None = None,
    custom_orbs: dict[str, float] | None = None,
) -> list[Aspect]:
    """Find all aspects between two sets of chart points."""
    angle_orb_keys = angle_orb_keys or set()
    aspects = []
    for k1, p1 in points_a.items():
        for k2, p2 in points_b.items():
            if k1 == k2:
                continue
            dist = angular_distance(p1.lon_decimal, p2.lon_decimal)
            for asp_code, asp_angle in ASPECT_ANGLES.items():
                if custom_orbs and asp_code in custom_orbs:
                    orb_limit = custom_orbs[asp_code] * orb_factor
                elif k1 in angle_orb_keys or k2 in angle_orb_keys:
                    from astro_mcp.core.models import ANGLE_ORBS
                    orb_limit = ANGLE_ORBS.get(asp_code, DEFAULT_ORBS.get(asp_code, 2.0)) * orb_factor
                else:
                    orb_limit = DEFAULT_ORBS.get(asp_code, 2.0) * orb_factor
                orb = abs(dist - asp_angle)
                if orb <= orb_limit:
                    applying = is_applying(p1.lon_decimal, p1.speed, p2.lon_decimal, p2.speed, asp_angle)
                    aspects.append(Aspect(k1, k2, asp_code, round(orb, 2), applying))
    aspects.sort(key=lambda a: a.orb)
    return aspects


# ---------------------------------------------------------------------------
# Rise / Transit (sunrise / sunset)
# ---------------------------------------------------------------------------

def calc_rise_set(jd: float, lat: float, lon: float) -> tuple[float, float]:
    """Return (jd_rise, jd_set) for the given Julian Day and location."""
    jd_rise_result = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE, (lon, lat, 0))
    jd_set_result = swe.rise_trans(jd, swe.SUN, swe.CALC_SET, (lon, lat, 0))
    return jd_rise_result[1][0], jd_set_result[1][0]


# ---------------------------------------------------------------------------
# Bisection search for exact aspect date
# ---------------------------------------------------------------------------

def find_exact_aspect_jd(
    pid1: int,
    pid2: int | None,
    asp_angle: float,
    jd_start: float,
    jd_end: float,
    natal_lon2: float | None = None,
    tolerance: float = 1 / 86400,  # 1 second
) -> float | None:
    """
    Binary search for JD when the angular distance between two bodies equals asp_angle.
    If natal_lon2 is given, planet2 is treated as a static natal point.
    """
    def diff_at(jd: float) -> float:
        lon1, _ = calc_planet(jd, pid1)
        lon2 = natal_lon2 if natal_lon2 is not None else calc_planet(jd, pid2)[0]  # type: ignore[arg-type]
        return angular_distance(lon1, lon2) - asp_angle

    d_start = diff_at(jd_start)
    d_end = diff_at(jd_end)

    if d_start * d_end > 0:
        return None  # no crossing

    for _ in range(80):  # max iterations
        jd_mid = (jd_start + jd_end) / 2
        if abs(jd_end - jd_start) < tolerance:
            return jd_mid
        d_mid = diff_at(jd_mid)
        if d_start * d_mid <= 0:
            jd_end = jd_mid
            d_end = d_mid
        else:
            jd_start = jd_mid
            d_start = d_mid
    return (jd_start + jd_end) / 2
