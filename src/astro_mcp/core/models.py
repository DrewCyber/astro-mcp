"""Shared data models used across all tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

# ---------------------------------------------------------------------------
# Input / wire types
# ---------------------------------------------------------------------------

class CoordDict(TypedDict):
    lat: float
    lon: float
    tz: str


class BirthData(TypedDict, total=False):
    date: str          # "YYYY-MM-DD"
    time: str          # "HH:MM" or "HH:MM:SS"
    location: object   # str or CoordDict


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
    exact_date: str | None = None


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
    dst_warning: str | None = None
    house_system_warning: str | None = None

    @property
    def all_points(self) -> dict[str, ChartPoint]:
        """Planets and angles in one map, for aspect scanning."""
        return {**self.planets, **self.angles}


# ---------------------------------------------------------------------------
# Astrological constants
# ---------------------------------------------------------------------------

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
    "Li": 12,   # MEAN_APOG (Black Moon Lilith)
    "Ch": 15,   # CHIRON
    "Ce": 17,   # CERES
    "Pa": 18,   # PALLAS
    "Ju2": 19,  # JUNO
    "Ve2": 20,  # VESTA
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
