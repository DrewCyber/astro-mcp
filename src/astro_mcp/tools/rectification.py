"""Tool 5: calculate_rectification_hints."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from astro_mcp.core.ephemeris_provider import (
    calc_all_planets,
    calc_houses,
    find_aspects,
    to_jd,
)
from astro_mcp.core.geocoding import local_to_utc, resolve_location


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



def _score_candidate(
    candidate_time: str,
    birth_date: str,
    geo,
    events: list[dict],
    house_system: str,
    techniques: list[str],
) -> tuple[float, list[dict]]:
    """Build chart for candidate time, score all events."""
    from astro_mcp.tools.natal import calculate_natal_chart
    natal = calculate_natal_chart(birth_date, candidate_time, geo, house_system, "dec")

    correlations: list[dict] = []
    total_score = 0.0

    # Pre-resolve location and build natal point map for aspect finding
    from astro_mcp.tools.transits import _natal_to_points
    natal_points = _natal_to_points(natal)
    geo_resolved = resolve_location(geo)

    for event in events:
        event_date = event["date"]
        event_type = event.get("type", "other")

        if "transits" in techniques:
            # Compute transits directly (skip bisection overhead) for speed
            utc_str, _ = local_to_utc(event_date, "12:00", geo_resolved.tz)
            jd_tr = to_jd(utc_str)
            cusps_tr, _ = calc_houses(jd_tr, geo_resolved.lat, geo_resolved.lon, house_system)
            tr_planets = calc_all_planets(
                jd_tr, cusps_tr,
                include_asteroids=False, use_mean_node=True,
                include_lilith=True, include_chiron=True,
            )
            raw_asps = find_aspects(
                tr_planets, natal_points,
                angle_orb_keys={"Asc", "MC", "Dsc", "IC"},
            )
            for asp in raw_asps:
                if asp.orb <= MAX_ORB:
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

        if "progressions" in techniques:
            from astro_mcp.tools.progressions import calculate_secondary_progressions
            prog = calculate_secondary_progressions(
                birth_date=birth_date,
                birth_time=candidate_time,
                birth_location=geo,
                progression_date=event_date,
                house_system=house_system,
                degree_format="dec",
                max_orb=MAX_ORB,
            )
            for asp in prog.get("prog_to_natal_aspects", []):
                corr_score = score_event_match(asp["orb"], asp["asp"], "progressions")
                if corr_score > 1:
                    total_score += corr_score

    return total_score, correlations


def calculate_rectification_hints(
    birth_date: str,
    birth_location: str | dict,
    time_from: str = "00:00",
    time_to: str = "23:56",
    events: list[dict] | None = None,
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
    """
    events = events or []
    if len([e for e in events if e.get("date_accuracy", "exact") == "exact"]) < 3:
        if len(events) < 3:
            return {"error": True, "code": "TOO_FEW_EVENTS",
                    "message": "Provide at least 3 events with known dates."}

    techniques = techniques or ["transits", "progressions", "profections"]

    # --- Verification mode: score a single pre-known birth_time ---
    if birth_time:
        geo = resolve_location(birth_location)
        score, correlations = _score_candidate(
            birth_time, birth_date, birth_location, events, house_system, techniques
        )
        from astro_mcp.tools.natal import calculate_natal_chart
        c_natal = calculate_natal_chart(birth_date, birth_time, birth_location, house_system, "dms")
        return {
            "mode": "verification",
            "time": birth_time,
            "score": round(score, 1),
            "Asc": c_natal["angles"]["Asc"]["lon"],
            "MC": c_natal["angles"]["MC"]["lon"],
            "correlations": correlations,
        }

    # Build candidate times
    fmt = "%H:%M"
    t_from = datetime.strptime(time_from, fmt)
    t_to = datetime.strptime(time_to, fmt)
    if (t_to - t_from).total_seconds() > 24 * 3600:
        return {"error": True, "code": "RANGE_TOO_WIDE",
                "message": "Time range > 24 hours is not supported."}

    candidates_times = []
    t = t_from
    while t <= t_to:
        candidates_times.append(t.strftime(fmt))
        t += timedelta(minutes=time_step_min)

    geo = resolve_location(birth_location)
    scored = []
    for ctime in candidates_times:
        score, correlations = _score_candidate(
            ctime, birth_date, birth_location, events, house_system, techniques
        )
        from astro_mcp.tools.natal import calculate_natal_chart
        c_natal = calculate_natal_chart(birth_date, ctime, birth_location, house_system, "dms")
        scored.append({
            "time": ctime,
            "score": round(score, 1),
            "Asc": c_natal["angles"]["Asc"]["lon"],
            "MC": c_natal["angles"]["MC"]["lon"],
            "correlations": correlations[:10],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    if not top or top[0]["score"] < 30:
        return {"error": True, "code": "NO_CANDIDATES",
                "message": "No candidates scored > 30. Add more events."}

    # Confidence
    best = top[0]["score"]
    second = top[1]["score"] if len(top) > 1 else 0
    gap = best - second
    n_events = len(events)
    if n_events >= 5 and gap > 15:
        confidence = "high"
    elif n_events >= 3 and gap >= 8:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "candidates": top,
        "best_time": top[0]["time"],
        "confidence": confidence,
        "note": (f"Score based on {len(techniques)} techniques, {n_events} events. "
                 f"Confidence: {confidence}"),
    }
