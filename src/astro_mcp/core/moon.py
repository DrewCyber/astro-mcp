"""Lunar phase and void-of-course calculations.

Both live here rather than in a tool module because the natal, transit and
electional tools all want them, and because getting the phase wrong is easy:
the elongation has to be measured from the Sun to the Moon in that order, and
the result taken modulo 360. Reading it off the two longitudes by eye gives the
wrong answer whenever the Moon's degree number is the smaller of the pair.
"""

from __future__ import annotations

from math import cos, radians
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    aspect_delta,
    calc_planet,
    find_exact_aspect_jd,
    jd_to_iso,
)
from astro_mcp.core.models import PLANET_IDS, SIGNS

# The eight-fold division used in astrological practice (Rudhyar's phases).
# Index is elongation // 45.
PHASE_NAMES: tuple[str, ...] = (
    "New",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full",
    "Disseminating",
    "Last Quarter",
    "Balsamic",
)

# Void-of-course is judged against the seven traditional bodies only; counting
# the outers or the nodes would leave the Moon almost never void.
VOC_BODIES: tuple[str, ...] = ("Su", "Me", "Ve", "Ma", "Ju", "Sa")

# Ptolemaic aspects only, again by tradition.
VOC_ASPECTS: dict[str, float] = {"Cnj": 0.0, "Sex": 60.0, "Squ": 90.0, "Tri": 120.0,
                                 "Opp": 180.0}

# The Moon clears a sign in ~2.2 days; 3 gives comfortable headroom.
_MAX_SIGN_DAYS = 3.0
# 3 hours. The Moon moves ~1.6 deg per step, fine for bracketing a crossing.
_SCAN_STEP = 1 / 8


def moon_phase(jd: float) -> dict[str, Any]:
    """Sun-Moon elongation, phase name and illuminated fraction at ``jd``.

    ``waxing`` is true for an elongation below 180 degrees, i.e. from New
    through to Full.
    """
    sun_lon, _ = calc_planet(jd, PLANET_IDS["Su"])
    moon_lon, _ = calc_planet(jd, PLANET_IDS["Mo"])

    elongation = (moon_lon - sun_lon) % 360.0
    illumination = (1.0 - cos(radians(elongation))) / 2.0

    return {
        "phase": PHASE_NAMES[int(elongation // 45)],
        "elongation": round(elongation, 2),
        "waxing": elongation < 180.0,
        "illum_pct": round(illumination * 100.0, 1),
        "sign": SIGNS[int(moon_lon // 30)],
    }


def _sign_boundary_jd(jd: float, forward: bool) -> float:
    """Julian day of the Moon's next (or previous) sign ingress."""
    moon_lon, _ = calc_planet(jd, PLANET_IDS["Mo"])
    index = int(moon_lon // 30)
    target = float((index + 1) * 30 % 360) if forward else float(index * 30)

    def offset(at: float) -> float:
        lon, _ = calc_planet(at, PLANET_IDS["Mo"])
        return ((lon - target + 180.0) % 360.0) - 180.0

    step = _SCAN_STEP if forward else -_SCAN_STEP
    lo, lo_val = jd, offset(jd)
    for _ in range(int(_MAX_SIGN_DAYS / _SCAN_STEP) + 1):
        hi = lo + step
        hi_val = offset(hi)
        if lo_val < 0 <= hi_val or hi_val < 0 <= lo_val:
            for _ in range(40):  # bisect to well under a second
                mid = (lo + hi) / 2
                if (offset(mid) < 0) == (lo_val < 0):
                    lo = mid
                else:
                    hi = mid
            return (lo + hi) / 2
        lo, lo_val = hi, hi_val
    # The Moon cannot fail to change sign within three days; fall back rather
    # than raise so a phase report is never lost to an edge case.
    return jd + (_MAX_SIGN_DAYS if forward else -_MAX_SIGN_DAYS)


def _aspect_times(jd_from: float, jd_to: float) -> list[float]:
    """Every Ptolemaic Moon-to-traditional-planet perfection in the window."""
    times: list[float] = []
    for body in VOC_BODIES:
        pid = PLANET_IDS[body]
        for angle in VOC_ASPECTS.values():
            jd = jd_from
            prev = aspect_delta(
                calc_planet(jd, PLANET_IDS["Mo"])[0], calc_planet(jd, pid)[0], angle
            )
            while jd < jd_to:
                nxt = min(jd + _SCAN_STEP, jd_to)
                delta = aspect_delta(
                    calc_planet(nxt, PLANET_IDS["Mo"])[0], calc_planet(nxt, pid)[0], angle
                )
                if prev * delta < 0 and abs(prev - delta) < 180:
                    exact = find_exact_aspect_jd(
                        PLANET_IDS["Mo"], pid, angle, jd, nxt
                    )
                    if exact is not None:
                        times.append(exact)
                jd, prev = nxt, delta
    return sorted(times)


def moon_void_of_course(jd: float) -> dict[str, Any]:
    """Whether the Moon is void of course at ``jd``, and the current window.

    The Moon is void from its last Ptolemaic aspect to a traditional planet
    until it changes sign. Nothing is "brought to fruition" during that gap, so
    it matters for electional questions.
    """
    sign_start = _sign_boundary_jd(jd, forward=False)
    sign_end = _sign_boundary_jd(jd, forward=True)

    aspects = _aspect_times(sign_start, sign_end)
    # The void begins after the final aspect made while in this sign; with no
    # aspects at all the Moon is void for the whole passage.
    void_start = aspects[-1] if aspects else sign_start

    return {
        "void_of_course": jd >= void_start,
        "void_start": jd_to_iso(void_start),
        "void_end": jd_to_iso(sign_end),
        "note": (
            "Void from the Moon's last Ptolemaic aspect to a traditional planet "
            "until it enters the next sign."
        ),
    }


# A synodic month is 29.53 days, so 30 always contains one of each lunation.
_LUNATION_SEARCH_DAYS = 30.0


def next_lunations(jd: float) -> dict[str, dict[str, Any]]:
    """The next New and Full Moon strictly after ``jd``.

    Reported so that a lunation never has to be inferred from a transit result.
    A lunation is the Moon against the *current* Sun, whereas an entry in
    ``aspect_events`` is the Moon against the *natal* Sun; the two read
    identically ("Moon opposite Sun") but fall on different days, and reading a
    Full Moon date off the natal contact has produced wrong forecasts.

    Each entry carries the positions *at the lunation itself*, because the
    surrounding ``moon`` object describes the queried moment: pairing a future
    timestamp with the present ``sign`` produced a Full Moon reported in the
    wrong sign. Here ``sign``/``deg`` are the Moon's, and for a Full Moon
    ``sun_sign`` gives the opposite end of the axis.
    """
    out: dict[str, dict[str, Any]] = {}
    for name, angle in (("next_new", 0.0), ("next_full", 180.0)):
        at = jd
        prev = aspect_delta(
            calc_planet(at, PLANET_IDS["Mo"])[0],
            calc_planet(at, PLANET_IDS["Su"])[0],
            angle,
        )
        end = jd + _LUNATION_SEARCH_DAYS
        while at < end:
            nxt = min(at + _SCAN_STEP, end)
            delta = aspect_delta(
                calc_planet(nxt, PLANET_IDS["Mo"])[0],
                calc_planet(nxt, PLANET_IDS["Su"])[0],
                angle,
            )
            if prev * delta < 0 and abs(prev - delta) < 180:
                exact = find_exact_aspect_jd(
                    PLANET_IDS["Mo"], PLANET_IDS["Su"], angle, at, nxt
                )
                if exact is not None and exact > jd:
                    moon_lon, _ = calc_planet(exact, PLANET_IDS["Mo"])
                    sun_lon, _ = calc_planet(exact, PLANET_IDS["Su"])
                    out[name] = {
                        "dt": jd_to_iso(exact),
                        "sign": SIGNS[int(moon_lon // 30)],
                        "deg": round(moon_lon, 2),
                        "sun_sign": SIGNS[int(sun_lon // 30)],
                    }
                    break
            at, prev = nxt, delta
    return out
