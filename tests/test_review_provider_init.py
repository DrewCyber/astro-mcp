"""Provider initialization policy and rise/set error handling regressions.

Two contract areas from the review:

* ``init_ephemeris(custom)`` must reconfigure *every* calculation thread, not
  only the calling one: workers pick up the active path by generation, and
  coverage detection / error hints follow the active path rather than the
  startup default.
* ``calc_rise_set`` must reserve ``NO_RISE_SET`` for the genuine polar
  "no event" status (-2) and map ``swe.Error``/other negative statuses onto
  ephemeris errors, so a polar planetary-hours request never masquerades as a
  data problem or vice versa.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import swisseph as swe

import astro_mcp.core.ephemeris_provider as provider
from astro_mcp.core.ephemeris_provider import calc_rise_set, to_jd
from astro_mcp.core.errors import AstroError


@pytest.fixture()
def provider_state():
    """Snapshot provider globals and the native path; restore afterwards."""
    saved_active = provider._ACTIVE_EPHE_PATH
    saved_covered = provider._COVERED_YEARS
    saved_generation = provider._EPHE_GENERATION
    saved_set_path = swe.set_ephe_path
    try:
        yield
    finally:
        provider._COVERED_YEARS = saved_covered
        provider._ACTIVE_EPHE_PATH = saved_active
        provider._EPHE_GENERATION = saved_generation
        # A fresh thread-local forces every thread to re-apply the restored
        # path on its next calculation.
        provider._tls = threading.local()
        saved_set_path(saved_active)


def _make_ephe_dir(tmp_path: Path, name: str) -> str:
    directory = tmp_path / name
    directory.mkdir()
    (directory / "sepl_18.se1").touch()
    return str(directory)


def test_init_ephemeris_activates_resolved_custom_path(
    tmp_path: Path, provider_state
) -> None:
    data = Path(_make_ephe_dir(tmp_path, "custom"))
    provider.init_ephemeris(str(data))
    assert Path(provider._ACTIVE_EPHE_PATH) == data.resolve()
    assert provider._COVERED_YEARS == (1800, 2399)


def test_init_ephemeris_resolves_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider_state
) -> None:
    _make_ephe_dir(tmp_path, "relative")
    monkeypatch.chdir(tmp_path)
    provider.init_ephemeris("relative")
    active = Path(provider._ACTIVE_EPHE_PATH)
    assert active.is_absolute() and active.name == "relative"


def test_init_ephemeris_failure_keeps_active_path(tmp_path: Path, provider_state) -> None:
    before = (provider._ACTIVE_EPHE_PATH, provider._EPHE_GENERATION)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AstroError):
        provider.init_ephemeris(str(empty))
    assert (provider._ACTIVE_EPHE_PATH, provider._EPHE_GENERATION) == before


def test_worker_threads_apply_active_path(provider_state) -> None:
    calls: list[str] = []
    original = swe.set_ephe_path

    def recording(path: str) -> None:
        calls.append(path)

    provider.swe.set_ephe_path = recording  # type: ignore[assignment]
    try:
        provider._ACTIVE_EPHE_PATH = "/custom/ephe"
        provider._EPHE_GENERATION += 1
        seen: dict[str, list[str]] = {}
        thread = threading.Thread(
            target=lambda: (
                provider._ensure_ephe_path(),
                seen.update(applied=calls.copy()),
            )
        )
        thread.start()
        thread.join()
    finally:
        provider.swe.set_ephe_path = original  # type: ignore[assignment]
    # A fresh worker thread applies the *active* path (generation change),
    # not the startup default.
    assert seen["applied"] == ["/custom/ephe"]


def test_covered_years_probe_follows_active_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider_state
) -> None:
    extended = tmp_path / "extended"
    extended.mkdir()
    (extended / "sepl_06.se1").touch()
    provider._COVERED_YEARS = None
    provider._ACTIVE_EPHE_PATH = str(extended)
    # The startup path still holds the 1800-2399 set; detection must consult
    # the active directory, not the startup default.
    assert provider.ephemeris_covered_years() == (600, 1199)


def test_moshier_hint_names_active_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider_state
) -> None:
    from astro_mcp.core.ephemeris_provider import _check_calc_flags

    data = Path(_make_ephe_dir(tmp_path, "active"))
    provider._ACTIVE_EPHE_PATH = str(data)
    provider._COVERED_YEARS = None
    with pytest.raises(AstroError) as excinfo:
        _check_calc_flags(swe.FLG_MOSEPH, swe.SUN, to_jd("2026-01-01T00:00:00Z"))
    assert str(data) in excinfo.value.hint


def _fake_rise_trans(
    monkeypatch: pytest.MonkeyPatch,
    rise: tuple[int, tuple[float]],
    set_: tuple[int, tuple[float]],
) -> None:
    def fake(jd: float, body: int, rsmi: int, geopos: tuple[float, float, float]):
        return rise if rsmi == swe.CALC_RISE else set_

    monkeypatch.setattr(provider.swe, "rise_trans", fake)


MIDDAY_JD = 2461216.0


def test_rise_set_maps_swe_error_to_out_of_range(
    monkeypatch: pytest.MonkeyPatch, provider_state
) -> None:
    def failing(jd: float, body: int, rsmi: int, geopos: object):
        raise swe.Error("law is restricted to Solar System")

    monkeypatch.setattr(provider.swe, "rise_trans", failing)
    with pytest.raises(AstroError) as excinfo:
        calc_rise_set(MIDDAY_JD, 50.0, 10.0)
    assert excinfo.value.code == "EPHEMERIS_OUT_OF_RANGE"


MIDDAY_JD = 2461216.0


def test_rise_set_maps_swe_error_to_unavailable(
    monkeypatch: pytest.MonkeyPatch, provider_state
) -> None:
    def failing(jd: float, body: int, rsmi: int, geopos: object):
        raise swe.Error("internal error")

    monkeypatch.setattr(provider.swe, "rise_trans", failing)
    with pytest.raises(AstroError) as excinfo:
        calc_rise_set(MIDDAY_JD, 50.0, 10.0)
    assert excinfo.value.code == "EPHEMERIS_UNAVAILABLE"


def test_negative_rise_status_is_not_no_rise_set(
    monkeypatch: pytest.MonkeyPatch, provider_state
) -> None:
    _fake_rise_trans(monkeypatch, (-1, (MIDDAY_JD,)), (0, (2461216.5,)))
    with pytest.raises(AstroError) as excinfo:
        calc_rise_set(MIDDAY_JD, 50.0, 10.0)
    assert excinfo.value.code == "EPHEMERIS_UNAVAILABLE"


@pytest.mark.parametrize(
    "jd", [to_jd("2026-06-21T12:00:00Z"), to_jd("2026-12-21T12:00:00Z")]
)
def test_polar_day_and_night_raise_no_rise_set(jd: float) -> None:
    # Tromsø inside the polar circles: no sunset near the June solstice, no
    # sunrise near the December one. Both are normal NO_RISE_SET conditions.
    with pytest.raises(AstroError) as excinfo:
        calc_rise_set(jd, 69.65, 18.96)
    assert excinfo.value.code == "NO_RISE_SET"
