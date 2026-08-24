"""Golden-chart regression test: Albert Einstein's natal chart.

Birth data: 1879-03-14, 11:30 LMT, Ulm, Germany (Astro-Databank AA).

Two layers of assertion:

1. *Published cross-checks* — sign placements and the widely quoted rounded
   positions (astro.com / Astro-Databank agree on these): Sun 23°30' Pisces,
   Moon and the rest in their traditional signs, Cancer rising. These catch
   calendar/timezone/epoch-level mistakes.

2. *Ephemeris pins* — every body's longitude pinned to the arcsecond against
   the Swiss Ephemeris output at remediation time. Any change to flags,
   ephemeris files, node flavour or date handling shifts these and fails the
   test. They are regression constants, not independent references.
"""

from astro_mcp.tools.natal import compute_natal

BIRTH = {
    "birth_date": "1879-03-14",
    "birth_time": "11:30",
    "birth_location": {"lat": 48.4011, "lon": 9.9876, "tz": "Europe/Berlin"},
}

# (sign, lon_decimal pinned to 1e-5 deg = 0.036 arcsec)
PLANET_PINS: dict[str, tuple[str, float]] = {
    "Su": ("Pis", 353.49843),
    "Mo": ("Sag", 254.39573),
    "Me": ("Ari", 3.12563),
    "Ve": ("Ari", 16.97349),
    "Ma": ("Cap", 296.90741),
    "Ju": ("Aqu", 327.48197),
    "Sa": ("Ari", 4.18867),
    "Ur": ("Vir", 151.28897),
    "Ne": ("Tau", 37.87170),
    "Pl": ("Tau", 54.72545),
}

ANGLE_PINS: dict[str, tuple[str, float]] = {
    "Asc": ("Can", 98.82411),
    "MC": ("Pis", 339.20840),
}

ARCSEC = 1.0 / 3600.0


def _chart():
    return compute_natal(**BIRTH)


def test_published_sign_placements():
    chart = _chart()
    for code, (sign, _) in PLANET_PINS.items():
        assert chart.planets[code].sign == sign, f"{code} should be in {sign}"
    assert chart.angles["Asc"].sign == "Can"


def test_published_rounded_positions():
    """astro.com quotes Sun 23°30' Pisces for this birth time; allow the
    rounding slack of half an arcminute."""
    chart = _chart()
    sun = chart.planets["Su"]
    assert abs(sun.lon_decimal - 353.50) < 30.5 * ARCSEC  # 23°29'54" -> 23°30'


def test_longitudes_pinned_to_arcsecond():
    """Regression pins against Swiss Ephemeris output (see module docstring)."""
    chart = _chart()
    for code, (_, pinned) in PLANET_PINS.items():
        assert abs(chart.planets[code].lon_decimal - pinned) < ARCSEC, code
    for code, (_, pinned) in ANGLE_PINS.items():
        assert abs(chart.angles[code].lon_decimal - pinned) < ARCSEC, code


def test_retrograde_flags_pinned():
    chart = _chart()
    # Only Uranus is retrograde among the ten planets at birth; the lunar
    # nodes regress by definition and are excluded here.
    planets = {code: pt for code, pt in chart.planets.items()
               if code not in {"NN", "SN"}}
    retro = {code for code, pt in planets.items() if pt.retrograde}
    assert retro == {"Ur"}


def test_utc_resolution_uses_historical_lmt_offset():
    """Europe/Berlin in 1879 is LMT +00:53:28; 11:30 local must resolve to
    10:36:32Z, not modern CET."""
    chart = _chart()
    assert chart.meta["dt"] == "1879-03-14T10:36:32Z"
