"""Swiss Ephemeris wrapper — centralises all pyswisseph interactions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import swisseph as swe

from astro_mcp.config import settings
from astro_mcp.core.errors import AstroError
from astro_mcp.core.models import (
    ANGLE_ORBS,
    ASPECT_ANGLES,
    DEFAULT_ORBS,
    PLANET_IDS,
    RULERS,
    SIGNS,
    SOUTH_NODE_ID,
    Aspect,
    ChartPoint,
    HouseCusp,
)

logger = logging.getLogger(__name__)

# Years covered by the installed .se1 files, detected at init time from the
# file names (``sepl_18.se1`` spans centuries 18..23, i.e. 1800-2399). Used to
# tell "date outside coverage" apart from "files missing" — the two are
# indistinguishable in swisseph's own error output but need opposite fixes.
_COVERED_YEARS: tuple[int, int] | None = None


def _detect_covered_years(path: str) -> tuple[int, int] | None:
    """(min_year, max_year) covered by the ``sepl_*.se1`` files in *path*."""
    starts = []
    for f in Path(path).glob("sepl_*.se1"):
        suffix = f.stem.rsplit("_", 1)[-1]
        if suffix.isdigit():
            starts.append(int(suffix) * 100)
    if not starts:
        return None
    return min(starts), max(starts) + 600 - 1


def ephemeris_covered_years() -> tuple[int, int] | None:
    """Covered year span of the installed data files, or None if undetected."""
    global _COVERED_YEARS
    if _COVERED_YEARS is None:
        _COVERED_YEARS = _detect_covered_years(settings.ephe_path)
    return _COVERED_YEARS

# Flags requested for every body.  FLG_SWIEPH selects the high-precision
# Swiss Ephemeris data files; see _check_calc_flags for why the *returned*
# flags matter as much as the requested ones.
_CALC_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

# Initialise ephemeris path at import time so that importing a tool module in
# isolation (tests, scripts) still works.  init_ephemeris() re-applies this and
# additionally *validates* it; the server calls it explicitly at startup.
swe.set_ephe_path(settings.ephe_path)


def pid_for(key: str) -> int:
    """Swiss Ephemeris id for a chart key, honouring the mean/true node setting.

    ``calc_all_planets`` stores both node flavours under the canonical key
    ``NN``, so any *chart-key -> swe id* lookup must go through here: looking
    ids up naively scans the True Node even when ``NODE_TYPE`` selected the
    Mean one. The two flavours sit up to ~1.7 deg apart, so mixing them makes
    transit-to-natal node contacts appear and disappear between tools.
    """
    if key == "NN" and settings.use_mean_node:
        return PLANET_IDS["NN_m"]
    return PLANET_IDS[key]


def init_ephemeris(ephe_path: str | None = None) -> None:
    """Point Swiss Ephemeris at the data files and fail fast if they're absent.

    Without this check a missing ``.se1`` set does not raise for the main
    planets — pyswisseph silently downgrades to the built-in Moshier ephemeris,
    which is materially less accurate.  Detecting that at startup is far better
    than emitting subtly wrong charts for the lifetime of the process.
    """
    path = ephe_path or settings.ephe_path

    # Validate *before* touching Swiss Ephemeris' global state, so a failed
    # init cannot leave the process pointed at a directory with no data.
    directory = Path(path)
    if not directory.is_dir() or not any(directory.glob("*.se1")):
        raise AstroError(
            "EPHEMERIS_UNAVAILABLE",
            f"No Swiss Ephemeris data files (*.se1) found in '{path}'.",
            hint=("Set EPHE_PATH to the directory holding the .se1 files, or run "
                  "scripts/download_ephe.sh to fetch them."),
        )

    swe.set_ephe_path(path)
    global _COVERED_YEARS
    _COVERED_YEARS = _detect_covered_years(path)
    logger.info("Swiss Ephemeris initialised from %s", path)


def _check_calc_flags(retflag: int, planet_id: int, jd: float) -> None:
    """Validate the flags Swiss Ephemeris actually used for a calculation.

    ``swe.calc_ut`` does not raise when the requested ephemeris is unavailable
    for the *main* planets: it quietly substitutes the Moshier ephemeris and
    reports that in the return flags.  Positions then differ from the Swiss
    Ephemeris by arcseconds (more for the outer planets and for dates far from
    J2000), which is enough to move a tight aspect in or out of orb.  Treat the
    substitution as an error rather than shipping degraded data unannounced.

    The fallback has two distinct causes that need opposite fixes: the .se1
    files are missing entirely, or the date lies outside their coverage.  The
    installed file names tell them apart, so the error does not send a user
    with a year-2500 query off to re-download files they already have.
    """
    if retflag < 0:
        raise AstroError(
            "EPHEMERIS_UNAVAILABLE",
            f"Swiss Ephemeris could not compute body {planet_id}.",
        )
    if retflag & swe.FLG_MOSEPH:
        covered = ephemeris_covered_years()
        if covered is not None:
            lo, hi = covered
            y, _, _ = swe.revjul(jd)[:3]
            if y < lo or y > hi:
                raise AstroError(
                    "EPHEMERIS_OUT_OF_RANGE",
                    (f"Date (JD {jd:.1f}, year ~{y}) is outside the coverage of "
                     f"the installed Swiss Ephemeris data files ({lo}-{hi})."),
                    hint=("Query dates within the covered span, or install "
                          "extended-range files (see scripts/download_ephe.sh)."),
                )
        raise AstroError(
            "EPHEMERIS_UNAVAILABLE",
            (f"Swiss Ephemeris fell back to the low-precision Moshier ephemeris "
             f"for body {planet_id}; the .se1 data files are missing."),
            hint=(f"Expected data files in '{settings.ephe_path}'. "
                  "Run scripts/download_ephe.sh or set EPHE_PATH."),
        )


# ---------------------------------------------------------------------------
# Julian Day helpers
# ---------------------------------------------------------------------------

def to_jd(dt_utc: str) -> float:
    """Convert ISO-8601 UTC datetime string to Julian Day number (UT).

    Non-UTC offsets are rejected rather than silently dropped: parsing them
    and discarding tzinfo would compute the JD of the wall-clock time read as
    UTC, shifting every downstream calculation by the offset.
    """
    dt = datetime.fromisoformat(dt_utc.replace("Z", "+00:00"))
    offset = dt.utcoffset()
    if offset not in (None, timedelta(0)):
        raise AstroError(
            "INPUT_ERROR",
            f"to_jd expects a UTC timestamp, got offset {offset}.",
            hint="Convert to UTC first (suffix 'Z' or '+00:00').",
        )
    return float(swe.julday(dt.year, dt.month, dt.day,
                            dt.hour + dt.minute / 60 + dt.second / 3600))


def jd_to_iso(jd: float) -> str:
    """Convert Julian Day to ISO-8601 UTC datetime string.

    Rounds to the nearest second rather than truncating, and carries the
    rounding through minute/hour/day boundaries via ``timedelta`` so that
    e.g. 12:59:59.7 becomes 13:00:00 instead of 12:59:59.
    """
    y, mo, d, h = swe.revjul(jd)
    base = datetime(y, mo, d)
    total_seconds = round(h * 3600)
    return (base + timedelta(seconds=total_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    if planet_id == SOUTH_NODE_ID:
        # Derived rather than looked up: the south node is the north node
        # opposed. Both nodes regress together, so the speed is shared, not
        # mirrored -- negating it would report SN as direct while NN is
        # retrograde. Resolving the flavour here keeps SN on whichever node
        # NODE_TYPE selected.
        node_id = PLANET_IDS["NN_m"] if settings.use_mean_node else PLANET_IDS["NN"]
        lon, speed = calc_planet(jd, node_id)
        return (lon + 180.0) % 360.0, speed
    try:
        result, retflag = swe.calc_ut(jd, planet_id, _CALC_FLAGS)
    except swe.Error as exc:
        message = str(exc)
        # swisseph reports both "file not found" and "outside the body's valid
        # JD range" through the same exception type; the distinction matters to
        # the caller, so recover it from the message.
        if "restricted to" in message or "outside" in message:
            raise AstroError(
                "EPHEMERIS_OUT_OF_RANGE",
                f"Date (JD {jd:.1f}) is outside the valid range for body {planet_id}.",
                hint=message,
            ) from exc
        raise AstroError(
            "EPHEMERIS_UNAVAILABLE",
            f"Swiss Ephemeris could not compute body {planet_id}.",
            hint=message,
        ) from exc
    _check_calc_flags(retflag, planet_id, jd)
    return result[0], result[3]


# ---------------------------------------------------------------------------
# Day / night
# ---------------------------------------------------------------------------

def is_day_chart(jd: float, lat: float, lon: float) -> bool:
    """True when the Sun is above the horizon at (jd, lat, lon).

    Derived from the Sun's true altitude rather than its house placement:
    quadrant-house numbering puts houses 7-12 above the horizon only for
    northern-hemisphere charts cast in a quadrant system, and whole-sign or
    southern-hemisphere placements drift across the ascendant by degrees.
    Altitude is unambiguous everywhere.
    """
    sun_lon, _ = calc_planet(jd, PLANET_IDS["Su"])
    _, true_altitude, _ = swe.azalt(
        jd, swe.ECL2HOR, (lon, lat, 0), 0.0, 0.0, (sun_lon, 0.0, 1.0)
    )
    return float(true_altitude) > 0


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
    use_mean_node: bool | None = None,
    include_lilith: bool = True,
    include_chiron: bool = True,
) -> dict[str, ChartPoint]:
    """Calculate all standard planets.

    Args:
        use_mean_node: If True, NN/SN use Mean Node (swe ID 10) instead of
            True Node (swe ID 11).  ``None`` (the default) defers to the
            ``NODE_TYPE`` setting, which keeps every tool on the *same*
            definition — mixing the two shifts the nodes by up to 1.7° and makes
            transit-to-natal node aspects appear and disappear between tools.
        include_lilith: Include Black Moon Lilith (Mean Apogee, swe ID 12).
        include_chiron: Include Chiron (swe ID 15).
        include_asteroids: Include minor asteroids Ceres, Pallas, Juno, Vesta.
    """
    if use_mean_node is None:
        use_mean_node = settings.use_mean_node
    base_keys = ["Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa", "Ur", "Ne", "Pl"]
    if include_chiron:
        base_keys.append("Ch")
    if include_lilith:
        base_keys.append("Li")
    asteroid_keys = ["Ce", "Pa", "Jun", "Ves"] if include_asteroids else []

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

    # South Node = NN + 180°, regressing at the same rate as the North Node.
    nn = planets["NN"]
    sn_lon = (nn.lon_decimal + 180) % 360
    planets["SN"] = build_chart_point(sn_lon, nn.speed, cusps)

    return planets


# ---------------------------------------------------------------------------
# Houses & Angles
# ---------------------------------------------------------------------------

HOUSE_SYSTEM_MAP = {"P": b"P", "W": b"W", "K": b"K"}

# Quadrant systems (Placidus, Koch) are undefined near the poles: above roughly
# this latitude some houses collapse or invert and swisseph errors out.
POLAR_LIMIT_DEG = 66.0
QUADRANT_SYSTEMS = frozenset({"P", "K"})


def resolve_house_system(requested: str, lat: float) -> tuple[str, str | None]:
    """Return ``(house_system, warning)`` valid for the given latitude.

    Placidus and Koch cannot be computed inside the polar circles, so they are
    substituted with Whole Sign.  Every tool must route through this helper:
    applying the fallback in one tool only (as was previously the case) means a
    natal chart and its own solar return can silently use different house
    systems for the same person.
    """
    system = requested if requested in HOUSE_SYSTEM_MAP else settings.default_house_system
    if system in QUADRANT_SYSTEMS and abs(lat) > POLAR_LIMIT_DEG:
        return "W", (
            f"house_system_fallback: {system} is undefined above "
            f"{POLAR_LIMIT_DEG}° latitude; used Whole Sign (W) instead."
        )
    return system, None


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
    try:
        cusps_raw, ascmc = swe.houses(jd, lat, lon, hs)
    except swe.Error as exc:
        raise AstroError(
            "HOUSE_CALC_FAILED",
            (f"Could not compute {house_system} house cusps at "
             f"latitude {lat}, longitude {lon}."),
            hint=str(exc),
        ) from exc
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
        sign, _ = lon_to_sign_info(cusp_lon)
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


def aspect_delta(lon1: float, lon2: float, asp_angle: float) -> float:
    """Signed quantity that crosses zero exactly when the aspect perfects.

    Used for both scanning (detect a sign change between samples) and bisection.

    Conjunction and opposition need special handling: the absolute separation
    is merely *tangent* to 0°/180° and never changes sign there, so a
    root-finder would never see a crossing.  For those two the directed arc is
    used instead, which does pass through zero.  Every other aspect is safe to
    express as ``separation - angle``.
    """
    if asp_angle in (0.0, 180.0):
        delta = ((lon1 - lon2) % 360) - asp_angle
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360
        return delta
    return angular_distance(lon1, lon2) - asp_angle


def signed_separation(lon1: float, lon2: float) -> float:
    """Separation of point 1 from point 2, normalised to (-180, +180].

    Positive means point 1 is ahead of point 2 in zodiacal order.
    """
    return ((lon1 - lon2 + 180.0) % 360.0) - 180.0


def is_applying(lon1: float, speed1: float, lon2: float, speed2: float, asp_angle: float) -> bool:
    """True if the aspect is approaching exactness.

    Works in terms of the *signed* separation ``d`` in (-180, +180]. Any aspect
    of size ``A`` is exact at two separations, ``d = +A`` and ``d = -A``; the
    pair is near whichever one matches the sign of ``d``. The gap still to be
    travelled is ``delta = d - target``, and ``d`` changes at the relative speed
    ``speed1 - speed2``, so the aspect is applying precisely when ``delta`` and
    the relative speed have opposite signs.

    Comparing an unsigned 0-360 arc against ``asp_angle`` (as this once did)
    inverts the answer for every pair in the upper half-circle, and separately
    breaks across the 0/360 boundary for conjunctions.
    """
    d = signed_separation(lon1, lon2)
    target = asp_angle if d >= 0 else -asp_angle
    delta = d - target
    relative_speed = speed1 - speed2
    if delta == 0 or relative_speed == 0:
        return False               # exact, or locked at a constant separation
    return delta * relative_speed < 0


def find_aspects(
    points_a: dict[str, ChartPoint],
    points_b: dict[str, ChartPoint],
    orb_factor: float | None = None,
    angle_orb_keys: set[str] | None = None,
    custom_orbs: dict[str, float] | None = None,
) -> list[Aspect]:
    """Find all aspects between two sets of chart points."""
    angle_orb_keys = angle_orb_keys or set()
    if orb_factor is None:
        orb_factor = settings.default_orb_factor
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
    """Return (jd_rise, jd_set) for the given Julian Day and location.

    Raises ``NO_RISE_SET`` when the Sun neither rises nor sets — inside the
    polar circles this is a normal occurrence for part of the year, and
    swisseph signals it with a ``-2`` return flag alongside an all-zero result
    array.  Ignoring the flag yields planetary hours derived from JD 0.
    """
    rise_flag, rise_result = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE, (lon, lat, 0))
    set_flag, set_result = swe.rise_trans(jd, swe.SUN, swe.CALC_SET, (lon, lat, 0))
    if rise_flag < 0 or set_flag < 0:
        raise AstroError(
            "NO_RISE_SET",
            (f"The Sun does not both rise and set at latitude {lat} on this date "
             "(polar day or polar night)."),
            hint="Planetary hours are undefined when there is no sunrise/sunset pair.",
        )
    return rise_result[0], set_result[0]


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
        return aspect_delta(lon1, lon2, asp_angle)

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
