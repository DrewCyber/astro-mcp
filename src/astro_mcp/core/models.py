"""Shared data models used across all tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Resolved internal types
# ---------------------------------------------------------------------------

@dataclass
class GeoLocation:
    lat: float
    lon: float
    tz: str            # IANA timezone
    name: str = ""


@dataclass
class ChartPoint:
    lon_decimal: float    # [0, 360)
    sign: str
    sign_lon: float       # [0, 30)
    house: int | None
    retrograde: bool
    speed: float

    def dms(self) -> str:
        """Return DMS string e.g. '24°45'12\"'."""
        deg = int(self.sign_lon)
        remainder = (self.sign_lon - deg) * 60
        minutes = int(remainder)
        seconds = int((remainder - minutes) * 60)
        return f"{deg:02d}\u00b0{minutes:02d}'{seconds:02d}\""


@dataclass
class Aspect:
    point1: str
    point2: str
    aspect_type: str     # "Cnj" | "Opp" | ...
    orb: float
    applying: bool
    significance: float = 0.0   # 0..1, see aspect_significance()


@dataclass
class HouseCusp:
    number: int
    lon_decimal: float
    sign: str
    ruler: str
    modern_ruler: str | None


ANGLE_KEYS: frozenset[str] = frozenset({"Asc", "MC", "Dsc", "IC"})


@dataclass
class NatalChart:
    """Full-precision internal representation of a computed chart.

    Tools that build on a natal chart (transits, progressions, returns,
    synastry, ...) must consume *this*, never the serialised dict.  The wire
    format rounds longitudes to two decimals and drops ``speed`` entirely, so
    re-parsing it injects ~18 arcsec of error into every derived orb and
    silently breaks applying/separating determination.
    """

    meta: dict[str, Any]
    planets: dict[str, ChartPoint]
    angles: dict[str, ChartPoint]
    cusps: list[float]
    houses: list[HouseCusp]
    aspects: list[Aspect]
    geo: GeoLocation
    jd: float
    house_system: str
    is_day: bool
    dst_warning: str | None = None
    house_system_warning: str | None = None

    @property
    def all_points(self) -> dict[str, ChartPoint]:
        """Planets and angles in one map, for aspect scanning."""
        return {**self.planets, **self.angles}


# ---------------------------------------------------------------------------
# Astrological constants
# ---------------------------------------------------------------------------

# The south node has no Swiss Ephemeris body of its own: it is definitionally
# the north node opposed. This sentinel lets it travel through the same
# id-based plumbing as every real body; calc_planet() resolves it.
SOUTH_NODE_ID = -1

PLANET_IDS: dict[str, int] = {
    "Su": 0,   # SUN
    "Mo": 1,   # MOON
    "Me": 2,   # MERCURY
    "Ve": 3,   # VENUS
    "Ma": 4,   # MARS
    "Ju": 5,   # JUPITER
    "Sa": 6,   # SATURN
    "Ur": 7,   # URANUS
    "Ne": 8,   # NEPTUNE
    "Pl": 9,   # PLUTO
    "NN_m": 10, # MEAN_NODE
    "NN": 11,   # TRUE_NODE
    "SN": SOUTH_NODE_ID,  # derived: NN + 180
    "Li": 12,   # MEAN_APOG (Black Moon Lilith)
    "Ch": 15,   # CHIRON
    "Ce": 17,   # CERES
    "Pa": 18,   # PALLAS
    "Jun": 19,  # JUNO   -- deliberately not "Ju2"; too easily read as Jupiter
    "Ves": 20,  # VESTA  -- deliberately not "Ve2"; too easily read as Venus
}

SIGNS: list[str] = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

RULERS: dict[str, tuple[str, str | None]] = {
    "Ari": ("Ma", None),
    "Tau": ("Ve", None),
    "Gem": ("Me", None),
    "Can": ("Mo", None),
    "Leo": ("Su", None),
    "Vir": ("Me", None),
    "Lib": ("Ve", None),
    "Sco": ("Ma", "Pl"),
    "Sag": ("Ju", None),
    "Cap": ("Sa", None),
    "Aqu": ("Sa", "Ur"),
    "Pis": ("Ju", "Ne"),
}

# Default orbs for aspect types — planet-to-planet
DEFAULT_ORBS: dict[str, float] = {
    "Cnj": 8.0,
    "Opp": 8.0,
    "Tri": 7.0,
    "Squ": 7.0,
    "Sex": 5.0,
    "SSq": 2.0,
    "Ses": 2.0,
}

# Wider orbs when one point is an angle (Asc, MC, Dsc, IC)
ANGLE_ORBS: dict[str, float] = {
    "Cnj": 10.0,
    "Opp": 10.0,
    "Tri": 8.0,
    "Squ": 8.0,
    "Sex": 6.0,
}

# Aspect angles
ASPECT_ANGLES: dict[str, float] = {
    "Cnj": 0.0,
    "SSq": 45.0,
    "Sex": 60.0,
    "Squ": 90.0,
    "Tri": 120.0,
    "Ses": 135.0,
    "Opp": 180.0,
}

# Pairs whose opposition is a mathematical identity, not an aspect: Dsc is
# Asc+180, IC is MC+180, SN is NN+180 by construction. They always show up as
# exact 180°/0.0-orb "aspects" and carry no interpretive weight, so natal and
# composite outputs drop them by default (exclude_axis_pairs).
DERIVED_OPPOSITION_PAIRS: frozenset[frozenset[str]] = frozenset(
    {frozenset(p) for p in (("Asc", "Dsc"), ("MC", "IC"), ("NN", "SN"))}
)


def is_derived_opposition(point1: str, point2: str) -> bool:
    """True when the pair is an axis identity (Asc-Dsc, MC-IC, NN-SN)."""
    return frozenset((point1, point2)) in DERIVED_OPPOSITION_PAIRS


# Interpretive weight of each body for aspect ranking (0..1). Personal planets
# dominate a chart's texture; transpersonal bodies colour generations more than
# individuals; angles/nodes/lilith/asteroids carry narrower meaning.
BODY_WEIGHTS: dict[str, float] = {
    "Su": 1.0, "Mo": 1.0, "Me": 1.0, "Ve": 1.0, "Ma": 1.0,   # personal
    "Ju": 0.75, "Sa": 0.75,                                   # social
    "Ur": 0.6, "Ne": 0.6, "Pl": 0.6,                          # transpersonal
    "Asc": 0.7, "MC": 0.7,
    "Dsc": 0.5, "IC": 0.5, "NN": 0.5, "SN": 0.5,
    "Ch": 0.45, "Li": 0.35,
    "Ce": 0.3, "Pa": 0.3, "Jun": 0.3, "Ves": 0.3,             # asteroids
}
_UNKNOWN_BODY_WEIGHT = 0.4

# Weight of each aspect type for ranking (0..1): major aspects first, the
# minors (semi-square, sesquiquadrate) carry distinctly less.
ASPECT_WEIGHTS: dict[str, float] = {
    "Cnj": 1.0, "Opp": 0.95, "Tri": 0.85, "Squ": 0.85,
    "Sex": 0.7, "SSq": 0.5, "Ses": 0.5,
}
_UNKNOWN_ASPECT_WEIGHT = 0.4


def aspect_significance(
    point1: str, point2: str, aspect_type: str, orb: float, orb_allowed: float
) -> float:
    """Rank an aspect's interpretive importance on a 0..1 scale.

    Combines how weighted the two bodies are (mean), how major the aspect type
    is, and how tight the orb is relative to what was allowed for it. The scale
    is relative within one chart, not an absolute truth meter.
    """
    pair = (
        BODY_WEIGHTS.get(point1, _UNKNOWN_BODY_WEIGHT)
        + BODY_WEIGHTS.get(point2, _UNKNOWN_BODY_WEIGHT)
    ) / 2
    kind = ASPECT_WEIGHTS.get(aspect_type, _UNKNOWN_ASPECT_WEIGHT)
    tightness = 0.0 if orb_allowed <= 0 else max(0.0, 1.0 - orb / orb_allowed)
    return round(min(1.0, pair * kind * tightness), 2)


def rank_aspects(
    aspects: list[Aspect],
    min_significance: float | None = None,
    top_n: int | None = None,
    exclude_derived: bool = False,
) -> list[Aspect]:
    """Order aspects by significance (desc, orb asc as tiebreak) and trim.

    Presentation-layer helper shared by every tool that serialises an aspect
    list; callers keep the unfiltered full-precision data internally.
    """
    ranked = sorted(aspects, key=lambda a: (-a.significance, a.orb))
    if exclude_derived:
        ranked = [a for a in ranked if not is_derived_opposition(a.point1, a.point2)]
    if min_significance is not None:
        ranked = [a for a in ranked if a.significance >= min_significance]
    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked


# Human-readable names for the include_legend payload.
PLANET_NAMES: dict[str, str] = {
    "Su": "Sun", "Mo": "Moon", "Me": "Mercury", "Ve": "Venus", "Ma": "Mars",
    "Ju": "Jupiter", "Sa": "Saturn", "Ur": "Uranus", "Ne": "Neptune",
    "Pl": "Pluto", "NN": "North Node", "SN": "South Node",
    "Li": "Black Moon Lilith", "Ch": "Chiron", "Ce": "Ceres",
    "Pa": "Pallas", "Jun": "Juno", "Ves": "Vesta",
    "Asc": "Ascendant", "MC": "Midheaven", "Dsc": "Descendant", "IC": "Imum Coeli",
}

ASPECT_NAMES: dict[str, str] = {
    "Cnj": "conjunction", "Opp": "opposition", "Tri": "trine",
    "Squ": "square", "Sex": "sextile", "SSq": "semi-square",
    "Ses": "sesquiquadrate",
}

SIGN_NAMES: dict[str, str] = {
    "Ari": "Aries", "Tau": "Taurus", "Gem": "Gemini", "Can": "Cancer",
    "Leo": "Leo", "Vir": "Virgo", "Lib": "Libra", "Sco": "Scorpio",
    "Sag": "Sagittarius", "Cap": "Capricorn", "Aqu": "Aquarius", "Pis": "Pisces",
}

# Chaldean order for planetary hours
CHALDEAN_ORDER: list[str] = ["Sa", "Ju", "Ma", "Su", "Ve", "Me", "Mo"]

# Day rulers (index into CHALDEAN_ORDER by weekday Mon=0..Sun=6)
# weekday Sunday=6 → Sa, Monday=0 → Mo ...
WEEKDAY_TO_RULER: dict[int, str] = {
    0: "Mo",  # Monday
    1: "Ma",  # Tuesday
    2: "Me",  # Wednesday
    3: "Ju",  # Thursday
    4: "Ve",  # Friday
    5: "Sa",  # Saturday
    6: "Su",  # Sunday
}
