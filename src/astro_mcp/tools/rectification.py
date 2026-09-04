"""Tool 5: calculate_rectification_hints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    calc_all_planets,
    calc_houses,
    find_aspects,
    resolve_house_system,
    to_jd,
)
from astro_mcp.core.errors import AstroError
from astro_mcp.core.geocoding import local_to_utc, resolve_location
from astro_mcp.core.models import ANGLE_KEYS, RULERS, SIGNS, ChartPoint, GeoLocation, NatalChart

# ---------------------------------------------------------------------------
# Significator mapping per event type
# ---------------------------------------------------------------------------

EVENT_SIGNIFICATORS: dict[str, list[tuple[str, list[str]]]] = {
    "marriage":       [("Ve", ["7th_cusp", "Asc", "Ju"]), ("Su", ["DSC"])],
    "divorce":        [("Sa", ["Ve", "7th_cusp", "DSC"]), ("Ma", ["Ve", "7th_cusp"])],
    "birth_child":    [("Ju", ["5th_cusp", "Mo"]), ("Mo", ["5th_cusp", "Su"])],
    "death_close":    [("Sa", ["4th_cusp", "8th_cusp"]), ("Pl", ["Mo", "Su"])],
    "career_rise":    [("Ju", ["MC", "Su"]), ("Su", ["MC"])],
    "career_fall":    [("Sa", ["MC", "Su"]), ("Pl", ["MC"])],
    "relocation":     [("Ur", ["IC", "4th_cusp"]), ("Sa", ["4th_cusp"])],
    "accident":       [("Ma", ["Asc", "Mo"]), ("Ur", ["Asc", "Ma"])],
    "illness_major":  [("Sa", ["Asc", "Mo", "Su"]), ("Ne", ["Asc", "6th_cusp"])],
    "surgery":        [("Ma", ["Asc", "6th_cusp"]), ("Pl", ["Asc", "Mo"])],
    "financial_gain": [("Ju", ["2nd_cusp", "Ve"])],
    "financial_loss": [("Sa", ["2nd_cusp", "Ve"]), ("Ne", ["2nd_cusp"])],
    "education":      [("Me", ["3rd_cusp", "9th_cusp", "Ju"]), ("Ju", ["9th_cusp"])],
    "spiritual_shift": [("Ne", ["Asc", "Su"]), ("Pl", ["Mo", "Su"])],
    "other":          [],
}

MAX_ORB = 8.0
MIN_EVENTS = 3
MAX_CANDIDATE_CHARTS = 400
MAX_WORK_UNITS = 4_000

#: Only these natal points actually move as the birth time varies.  Scoring
#: aspects to the slow natal planets adds the *same* constant to every
#: candidate, which flattens the ranking and makes the top score meaningless.
#: The Moon is included because it travels ~13 deg/day; over a 24-hour search
#: window it genuinely discriminates between candidates.
TIME_SENSITIVE_POINTS: frozenset[str] = ANGLE_KEYS | {"Mo"}


def score_event_match(orb: float, aspect_type: str, technique: str) -> float:
    base_scores: dict[str, float] = {
        "Cnj": 10.0, "Opp": 9.0, "Squ": 8.5, "Tri": 7.0,
        "Sex": 5.0, "SSq": 3.0, "Ses": 3.0, "SSx": 2.0,
        "BiQ": 2.0, "Qui": 2.0,
    }
    technique_weights: dict[str, float] = {
        "transits": 1.0,
        "progressions": 1.2,
        "profections": 0.8,
    }
    base = base_scores.get(aspect_type, 2.0)
    orb_factor = max(0.0, 1 - orb / MAX_ORB)
    return base * orb_factor * technique_weights.get(technique, 1.0)


def completed_years(birth_date: str, event_date: str) -> int:
    """Whole years of life completed by the event date (profection counter)."""
    b = date.fromisoformat(birth_date)
    e = date.fromisoformat(event_date)
    years = e.year - b.year
    if (e.month, e.day) < (b.month, b.day):
        years -= 1
    return max(0, years)


def profection_for_age(asc_lon: float, age_years: int) -> tuple[int, float, str]:
    """Profected sign for an age, from the candidate's Ascendant.

    Returns ``(sign_index, profected_cusp_longitude, year_lord_code)``.
    Annual profections advance one whole sign per completed year of life,
    starting from the rising sign at age 0; the year lord is the sign's
    traditional ruler.
    """
    asc_sign_idx = int(asc_lon % 360 // 30)
    prof_sign_idx = (asc_sign_idx + age_years % 12) % 12
    return prof_sign_idx, prof_sign_idx * 30.0, RULERS[SIGNS[prof_sign_idx]][0]


def _transit_charts_for_events(
    events: list[dict[str, Any]],
    geo: GeoLocation,
    house_system: str,
) -> dict[str, dict[str, ChartPoint]]:
    """Transiting positions at each event's local noon, computed once per call.

    Transits at a given date do not depend on the candidate birth time (only
    the natal side of the aspect does), so building them once instead of once
    per candidate removes the largest redundant chunk of work from scans.
    """
    hs, _ = resolve_house_system(house_system, geo.lat)
    charts: dict[str, dict[str, ChartPoint]] = {}
    for event in events:
        event_date = event["date"]
        if event_date in charts:
            continue
        utc_str, _ = local_to_utc(event_date, "12:00", geo.tz)
        jd_tr = to_jd(utc_str)
        cusps_tr, _ = calc_houses(jd_tr, geo.lat, geo.lon, hs)
        charts[event_date] = calc_all_planets(
            jd_tr, cusps_tr,
            include_asteroids=False,
            include_lilith=True, include_chiron=True,
        )
    return charts


def _score_candidate(
    chart: NatalChart,
    birth_date: str,
    events: list[dict[str, Any]],
    techniques: list[str],
    transit_charts: dict[str, dict[str, ChartPoint]],
) -> tuple[float, list[dict[str, Any]]]:
    """Score one pre-built candidate chart against all events.

    Only time-sensitive natal points contribute to the score; see
    :data:`TIME_SENSITIVE_POINTS`.
    """
    natal_points: dict[str, ChartPoint] = {
        code: pt for code, pt in chart.all_points.items()
        if code in TIME_SENSITIVE_POINTS
    }

    correlations: list[dict[str, Any]] = []
    total_score = 0.0

    for event in events:
        event_date = event["date"]
        event_type = event.get("type", "other")

        tr_planets: dict[str, ChartPoint] | None = None
        if "transits" in techniques or "profections" in techniques:
            tr_planets = transit_charts[event_date]

        if "transits" in techniques and tr_planets is not None:
            raw_asps = find_aspects(
                tr_planets, natal_points,
                angle_orb_keys=set(ANGLE_KEYS),
            )
            for asp in raw_asps:
                if asp.orb > MAX_ORB:
                    continue
                corr_score = score_event_match(asp.orb, asp.aspect_type, "transits")
                if corr_score > 1:
                    correlations.append({
                        "event_date": event_date,
                        "event_type": event_type,
                        "technique": "transits",
                        "indicators": [{"planet": asp.point1, "asp": asp.aspect_type,
                                        "point": asp.point2, "orb": round(asp.orb, 2)}],
                        "score": round(corr_score, 2),
                    })
                    total_score += corr_score

        if "profections" in techniques and tr_planets is not None:
            age = completed_years(birth_date, event_date)
            prof_sign_idx, prof_cusp_lon, lord = profection_for_age(
                chart.angles["Asc"].lon_decimal, age
            )
            prof_sign = SIGNS[prof_sign_idx]

            # Target set anchored on the candidate's Ascendant sign, so it
            # moves with the birth time exactly as a profection does:
            # - the profected house cusp (start of the profected sign);
            # - the natal year lord, when that point is time-sensitive.
            targets: dict[str, ChartPoint] = {
                f"{prof_sign}_cusp": ChartPoint(
                    prof_cusp_lon, prof_sign, 0.0, None, False, 0.0
                ),
            }
            lord_pt = chart.planets.get(lord)
            if lord_pt is not None and lord in TIME_SENSITIVE_POINTS:
                targets[lord] = ChartPoint(
                    lord_pt.lon_decimal, lord_pt.sign, lord_pt.sign_lon,
                    None, lord_pt.retrograde, lord_pt.speed,
                )

            for asp in find_aspects(tr_planets, targets, angle_orb_keys=set(targets)):
                if asp.orb > MAX_ORB:
                    continue
                corr_score = score_event_match(asp.orb, asp.aspect_type, "profections")
                if corr_score > 1:
                    correlations.append({
                        "event_date": event_date,
                        "event_type": event_type,
                        "technique": "profections",
                        "age_year_lord": lord,
                        "profected_sign": prof_sign,
                        "indicators": [{"planet": asp.point1, "asp": asp.aspect_type,
                                        "point": asp.point2, "orb": round(asp.orb, 2)}],
                        "score": round(corr_score, 2),
                    })
                    total_score += corr_score

            # The year lord's own transit condition describes its year: score
            # the transiting lord against the candidate's angles and Moon.
            tr_lord = tr_planets.get(lord)
            if tr_lord is not None:
                for asp in find_aspects({lord: tr_lord}, natal_points,
                                        angle_orb_keys=set(ANGLE_KEYS)):
                    if asp.orb > MAX_ORB:
                        continue
                    corr_score = score_event_match(asp.orb, asp.aspect_type, "profections")
                    if corr_score > 1:
                        correlations.append({
                            "event_date": event_date,
                            "event_type": event_type,
                            "technique": "profections",
                            "age_year_lord": lord,
                            "profected_sign": prof_sign,
                            "indicators": [{"planet": lord, "asp": asp.aspect_type,
                                            "point": asp.point2, "orb": round(asp.orb, 2)}],
                            "score": round(corr_score, 2),
                        })
                        total_score += corr_score

        if "progressions" in techniques:
            from astro_mcp.tools.progressions import calculate_secondary_progressions
            prog = calculate_secondary_progressions(
                progression_date=event_date,
                degree_format="dec",
                max_orb=MAX_ORB,
                chart=chart,
                birth_date=birth_date,
            )
            for asp in prog.get("prog_to_natal_aspects", []):
                # Serialized as pp/np (progression point / natal point); the
                # previous p1/p2 reads always evaluated to None, silently
                # disabling the whole progressions technique.
                if asp.get("np") not in TIME_SENSITIVE_POINTS:
                    continue
                corr_score = score_event_match(asp["orb"], asp["asp"], "progressions")
                if corr_score > 1:
                    total_score += corr_score
                    correlations.append({
                        "event_date": event_date,
                        "event_type": event_type,
                        "technique": "progressions",
                        "indicators": [{"planet": asp.get("pp"), "asp": asp["asp"],
                                        "point": asp.get("np"), "orb": round(asp["orb"], 2)}],
                        "score": round(corr_score, 2),
                    })

    return total_score, correlations


def calculate_rectification_hints(
    birth_date: str,
    birth_location: str | dict[str, Any],
    time_from: str = "00:00",
    time_to: str = "23:56",
    events: list[dict[str, Any]] | None = None,
    time_step_min: int = 4,
    techniques: list[str] | None = None,
    top_n: int = 5,
    house_system: str = "P",
    birth_time: str | None = None,
) -> dict[str, Any]:
    """Tool 5: Rectification — score candidate birth times against life events.

    If birth_time is supplied, the function runs in *verification mode*:
    scores only that single time and returns its correlations without
    requiring a time range.

    Scores are **relative**: they rank candidates against each other within a
    single call and carry no absolute meaning.
    """
    events = events or []
    # Only exactly-known dates are scored, matching the documented contract:
    # the hint below promises fuzzy events "do not count", so they must not
    # silently drive the ranking either.
    events = [e for e in events if e.get("date_accuracy", "exact") == "exact"]
    if len(events) < MIN_EVENTS:
        raise AstroError(
            "TOO_FEW_EVENTS",
            f"Provide at least {MIN_EVENTS} events with exactly known dates "
            f"(got {len(events)}).",
            hint="Events with date_accuracy other than 'exact' do not count.",
        )

    techniques = techniques or ["transits", "progressions", "profections"]
    geo = resolve_location(birth_location)

    from astro_mcp.tools.natal import compute_natal

    # --- Verification mode: score a single pre-known birth_time ---
    if birth_time:
        chart = compute_natal(birth_date, birth_time, birth_location, house_system)
        transit_charts = _transit_charts_for_events(events, geo, house_system)
        score, correlations = _score_candidate(
            chart, birth_date, events, techniques, transit_charts
        )
        return {
            "mode": "verification",
            "time": birth_time,
            "score": round(score, 1),
            "Asc": round(chart.angles["Asc"].lon_decimal, 4),
            "MC": round(chart.angles["MC"].lon_decimal, 4),
            "correlations": correlations,
            "score_note": "Relative score; comparable only within one call.",
        }

    if time_step_min < 1:
        raise AstroError("INPUT_ERROR", "time_step_min must be at least 1 minute.")

    fmt = "%H:%M"
    try:
        t_from = datetime.strptime(time_from, fmt)
        t_to = datetime.strptime(time_to, fmt)
    except ValueError as exc:
        raise AstroError("INVALID_TIME", "time_from and time_to must be HH:MM.") from exc

    span_seconds = (t_to - t_from).total_seconds()
    if span_seconds < 0:
        raise AstroError("INVALID_TIME", "time_to must be after time_from.")
    if span_seconds > 24 * 3600:
        raise AstroError("RANGE_TOO_WIDE", "Time range > 24 hours is not supported.")

    n_candidates = int(span_seconds // (time_step_min * 60)) + 1
    if n_candidates > MAX_CANDIDATE_CHARTS:
        raise AstroError(
            "WORKLOAD_TOO_LARGE",
            f"{n_candidates} candidate times exceeds the limit of {MAX_CANDIDATE_CHARTS}.",
            hint="Increase time_step_min or narrow the time range.",
        )
    work_units = n_candidates * max(1, len(events)) * max(1, len(techniques))
    if work_units > MAX_WORK_UNITS:
        raise AstroError(
            "WORKLOAD_TOO_LARGE",
            f"This request needs about {work_units:,} chart computations, over the "
            f"limit of {MAX_WORK_UNITS:,}.",
            hint="Increase time_step_min, narrow the time range, or pass fewer events.",
        )

    candidates_times = []
    t = t_from
    while t <= t_to:
        candidates_times.append(t.strftime(fmt))
        t += timedelta(minutes=time_step_min)

    # Transit charts depend only on the event dates: build them once.
    transit_charts = _transit_charts_for_events(events, geo, house_system)

    scored: list[dict[str, Any]] = []
    scores: list[float] = []
    for ctime in candidates_times:
        chart = compute_natal(birth_date, ctime, birth_location, house_system)
        score, correlations = _score_candidate(
            chart, birth_date, events, techniques, transit_charts
        )
        scores.append(score)
        scored.append({
            "time": ctime,
            "score": round(score, 1),
            "Asc": round(chart.angles["Asc"].lon_decimal, 4),
            "MC": round(chart.angles["MC"].lon_decimal, 4),
            "correlations": correlations[:10],
        })

    order = sorted(range(len(scored)), key=lambda i: scores[i], reverse=True)
    scored = [scored[i] for i in order]
    scores = [scores[i] for i in order]
    top = scored[:top_n]

    # Confidence is driven by the *separation* between the best candidate and
    # the runner-up, relative to the spread of all scores -- an absolute score
    # threshold is meaningless now that only time-sensitive points contribute.
    best = scores[0] if scores else 0.0
    second = scores[1] if len(scores) > 1 else 0.0
    gap = best - second
    spread = best - min(scores) if scores else 0.0
    relative_gap = gap / spread if spread > 0 else 0.0
    n_events = len(events)

    if n_events >= 5 and relative_gap > 0.15:
        confidence = "high"
    elif n_events >= MIN_EVENTS and relative_gap > 0.07:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "candidates": top,
        "best_time": top[0]["time"] if top else None,
        "confidence": confidence,
        "score_note": (
            "Scores are relative and comparable only within this call. Only "
            "time-sensitive natal points (angles and the Moon) are scored, since "
            "aspects to the slow planets are identical for every candidate time."
        ),
        "note": (f"Scored {len(scored)} candidate times using {len(techniques)} "
                 f"technique(s) and {n_events} event(s). Confidence: {confidence}."),
    }
