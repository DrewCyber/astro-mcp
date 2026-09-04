"""Tests for calculate_rectification_hints."""

BIRTH = {
    "birth_date": "1990-06-15",
    "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
}

EVENTS = [
    {"date": "2015-06-15", "type": "marriage", "date_accuracy": "exact"},
    {"date": "2018-03-01", "type": "career_rise", "date_accuracy": "exact"},
    {"date": "2020-09-10", "type": "relocation", "date_accuracy": "exact"},
]


# --- Profection arithmetic -------------------------------------------------

def test_completed_years():
    from astro_mcp.tools.rectification import completed_years
    assert completed_years("1990-06-15", "1990-06-15") == 0
    assert completed_years("1990-06-15", "1991-06-14") == 0
    assert completed_years("1990-06-15", "1991-06-15") == 1
    # Birthday not yet reached in the event year
    assert completed_years("1990-06-15", "2020-05-01") == 29
    assert completed_years("1990-06-15", "2020-07-01") == 30


def test_profection_for_age_cycles_through_signs_from_asc():
    from astro_mcp.tools.rectification import profection_for_age
    asc_lon = 125.0          # 5 Leo
    sign0, cusp0, lord0 = profection_for_age(asc_lon, 0)
    assert (sign0, cusp0) == (4, 120.0)   # Leo starts at 120
    assert lord0 == "Su"
    # Twelve years later the cycle returns to the rising sign
    sign12, cusp12, lord12 = profection_for_age(asc_lon, 12)
    assert (sign12, cusp12, lord12) == (sign0, cusp0, lord0)
    # One year forward advances exactly one sign (with wrap)
    sign13, cusp13, _ = profection_for_age(asc_lon, 13)
    assert sign13 == (sign0 + 1) % 12
    assert cusp13 == 150.0
    # Wrap across Pisces -> Aries
    sign_wrap, cusp_wrap, lord_wrap = profection_for_age(350.0, 1)
    assert (sign_wrap, cusp_wrap, lord_wrap) == (0, 0.0, "Ma")


def test_profections_technique_produces_correlations():
    """R-3 regression: 'profections' was advertised but scored nothing."""
    from astro_mcp.tools.rectification import calculate_rectification_hints

    result = calculate_rectification_hints(
        **BIRTH,
        birth_time="12:00",
        events=EVENTS,
        techniques=["profections"],
    )
    assert result["mode"] == "verification"
    assert result["score"] > 0
    techniques_used = {c["technique"] for c in result["correlations"]}
    assert "profections" in techniques_used
    for corr in result["correlations"]:
        if corr["technique"] == "profections":
            assert corr["indicators"]
            assert 0 <= corr["score"]


def test_all_techniques_include_working_profections_contribution():
    from astro_mcp.tools.rectification import calculate_rectification_hints

    full = calculate_rectification_hints(
        **BIRTH, birth_time="12:00", events=EVENTS,
        techniques=["transits", "progressions", "profections"],
    )
    pro_only = calculate_rectification_hints(
        **BIRTH, birth_time="12:00", events=EVENTS,
        techniques=["profections"],
    )
    # Scores are sums of non-negative technique contributions, so the
    # all-technique run must include at least the profections part.
    assert pro_only["score"] > 0
    assert full["score"] >= pro_only["score"]


def test_too_few_events_rejected():
    import pytest

    from astro_mcp.core.errors import AstroError
    from astro_mcp.tools.rectification import calculate_rectification_hints

    with pytest.raises(AstroError) as exc:
        calculate_rectification_hints(
            **BIRTH, birth_time="12:00",
            events=[{"date": "2015-06-15", "type": "marriage"}],
        )
    assert exc.value.code == "TOO_FEW_EVENTS"


def test_non_exact_events_do_not_influence_scores():
    """R-11 regression: month/year-accuracy events were scored although the
    tool promises they 'do not count'."""
    from astro_mcp.tools.rectification import calculate_rectification_hints

    base = calculate_rectification_hints(**BIRTH, birth_time="12:00", events=EVENTS)
    padded = calculate_rectification_hints(
        **BIRTH,
        birth_time="12:00",
        events=EVENTS + [
            {"date": "2001-01-01", "type": "career_rise", "date_accuracy": "year"},
            {"date": "2012-07-01", "type": "relocation", "date_accuracy": "month"},
        ],
    )
    assert padded["score"] == base["score"]
    dates = {c["event_date"] for c in base["correlations"]}
    assert "2001-01-01" not in dates and "2012-07-01" not in dates
    # Fuzzy-only supply must still be rejected even though 5 events were given.
    import pytest

    from astro_mcp.core.errors import AstroError

    with pytest.raises(AstroError) as exc:
        calculate_rectification_hints(
            **BIRTH,
            birth_time="12:00",
            events=[
                {"date": "2001-01-01", "type": "career_rise", "date_accuracy": "year"},
                {"date": "2012-07-01", "type": "relocation", "date_accuracy": "month"},
            ],
        )
    assert exc.value.code == "TOO_FEW_EVENTS"


# --- 1.2.0: the progressions branch actually scores --------------------------

def test_progressions_technique_produces_correlations():
    """Regression: rectification read p1/p2 keys from the progressions payload,
    which serialises as pp/np — the technique silently never matched."""
    from astro_mcp.tools.rectification import calculate_rectification_hints

    result = calculate_rectification_hints(
        **BIRTH, birth_time="12:00", events=EVENTS,
        techniques=["progressions"],
    )
    assert result["mode"] == "verification"
    progressions = [
        c for c in result["correlations"] if c["technique"] == "progressions"
    ]
    assert progressions, (
        "the progressions branch must contribute correlations after the pp/np fix"
    )
    for corr in progressions:
        for ind in corr["indicators"]:
            assert ind["planet"], "indicator planets must resolve, not be None"
