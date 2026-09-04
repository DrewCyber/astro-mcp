"""1.2.0 output UX: significance ranking, axis-pair filter, legend, dec default."""

from __future__ import annotations

from astro_mcp.core.models import aspect_significance, is_derived_opposition
from astro_mcp.tools.natal import calculate_natal_chart
from astro_mcp.tools.transits import calculate_transits

BIRTH = {
    "birth_date": "1990-03-15",
    "birth_time": "14:30",
    "birth_location": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"},
}


# --- significance formula -----------------------------------------------------


def test_significance_orders_body_classes_correctly():
    tight_conj = aspect_significance("Su", "Mo", "Cnj", 0.0, 8.0)
    outer_conj = aspect_significance("Ur", "Pl", "Cnj", 0.0, 8.0)
    minor = aspect_significance("Su", "Mo", "SSq", 0.0, 2.0)
    wide = aspect_significance("Su", "Mo", "Cnj", 7.5, 8.0)
    assert tight_conj > outer_conj > minor > 0.0
    assert wide < 0.1, "an aspect at the edge of orb must score near zero"
    assert 0.0 <= wide <= 1.0


def test_significance_of_same_orb_scales_with_allowed_orb():
    # Tightness is relative to the allowance: the same 2.0° orb consumes a
    # quarter of an 8° allowance but half of a 4° one.
    assert aspect_significance("Su", "Ma", "Cnj", 2.0, 8.0) > aspect_significance(
        "Su", "Ma", "Cnj", 2.0, 4.0
    )
    assert aspect_significance("Su", "Ma", "Cnj", 8.0, 8.0) == 0.0, "at the limit"


# --- derived axis pairs -------------------------------------------------------


def test_derived_pair_detection():
    assert is_derived_opposition("Asc", "Dsc")
    assert is_derived_opposition("Dsc", "Asc")
    assert is_derived_opposition("MC", "IC")
    assert is_derived_opposition("NN", "SN")
    assert not is_derived_opposition("Asc", "MC"), "angle squares are meaningful"
    assert not is_derived_opposition("Su", "Dsc")


def test_axis_pairs_excluded_by_default():
    result = calculate_natal_chart(**BIRTH)
    pairs = {frozenset((a["p1"], a["p2"])) for a in result["aspects"]}
    assert frozenset(("Asc", "Dsc")) not in pairs
    assert frozenset(("MC", "IC")) not in pairs
    assert frozenset(("NN", "SN")) not in pairs


def test_axis_pairs_kept_when_asked():
    result = calculate_natal_chart(exclude_axis_pairs=False, **BIRTH)
    pairs = {frozenset((a["p1"], a["p2"])) for a in result["aspects"]}
    assert frozenset(("Asc", "Dsc")) in pairs
    derived = next(a for a in result["aspects"] if frozenset((a["p1"], a["p2"]))
                   == frozenset(("Asc", "Dsc")))
    assert derived["orb"] == 0.0, "the identity opposition is always exact"


# --- top_n / min_significance -------------------------------------------------


def test_top_n_limits_the_aspect_list():
    full = calculate_natal_chart(**BIRTH)["aspects"]
    top3 = calculate_natal_chart(top_n=3, **BIRTH)["aspects"]
    assert [a["p1"] for a in top3] == [a["p1"] for a in full[:3]]


def test_min_significance_filters_but_keeps_order():
    result = calculate_natal_chart(min_significance=0.5, **BIRTH)["aspects"]
    assert result
    assert all(a["sig"] >= 0.5 for a in result)
    sigs = [a["sig"] for a in result]
    assert sigs == sorted(sigs, reverse=True)


def test_transit_events_carry_sig_and_respect_min_significance():
    result = calculate_transits(
        transit_date="2026-07-26", period_days=7, moon_events="none", **BIRTH
    )
    assert all("sig" in e for e in result["aspect_events"])
    trimmed = calculate_transits(
        transit_date="2026-07-26", period_days=7, moon_events="none",
        min_significance=0.6, **BIRTH
    )
    assert trimmed["aspect_events"]
    assert all(e["sig"] >= 0.6 for e in trimmed["aspect_events"])
    # Events stay chronological even after filtering.
    dates = [e["exact"] for e in trimmed["aspect_events"]]
    assert dates == sorted(dates)


# --- legend & degree format ---------------------------------------------------


def test_legend_is_opt_in():
    plain = calculate_natal_chart(**BIRTH)
    assert "legend" not in plain
    with_legend = calculate_natal_chart(include_legend=True, **BIRTH)
    legend = with_legend["legend"]
    assert legend["bodies"]["Su"] == "Sun"
    assert legend["aspects"]["Ses"] == "sesquiquadrate"
    assert legend["signs"]["Sco"] == "Scorpio"
    assert "sig" in legend["other"]


def test_dec_is_the_default_degree_format():
    result = calculate_natal_chart(**BIRTH)
    assert "lon" not in result["planets"]["Su"], "DMS string must be opt-in now"
    assert "deg" in result["planets"]["Su"]
    dms = calculate_natal_chart(degree_format="dms", **BIRTH)
    assert "°" in dms["planets"]["Su"]["lon"]
    assert "°" in dms["houses"][0]["cusp"]
