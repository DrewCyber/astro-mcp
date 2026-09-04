"""Ephemeris path must hold in worker threads (asyncio.to_thread callers).

Depending on how pyswisseph was built, ``swe.set_ephe_path`` state is
thread-local: a path applied only at import time in the main thread leaves
worker threads silently calculating on the Moshier fallback. The deployed HTTP
server runs every tool in a worker thread with a working directory that has no
``./ephe`` next to it, so this test reproduces that environment.
"""

import os
import threading

from astro_mcp.core.ephemeris_provider import calc_planet, pid_for, to_jd


def test_calc_planet_in_worker_thread_uses_configured_ephe_path(tmp_path, monkeypatch):
    # Move away from the repo root so a CWD-relative default path (the
    # mechanism that masked this bug on developer machines) finds nothing.
    monkeypatch.chdir(tmp_path)

    outcome: dict[str, str] = {}

    def run() -> None:
        try:
            lon, _speed = calc_planet(to_jd("1879-03-14T10:36:32Z"), pid_for("Su"))
            outcome["lon"] = lon
        except Exception as exc:  # noqa: BLE001 - re-raised in main thread below
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()

    assert "error" not in outcome, outcome["error"]
    # Einstein's Sun: 23 Pisces 29'54" == 353.4984…
    assert round(outcome["lon"], 3) == 353.498


def test_ensure_ephe_path_is_idempotent_per_thread():
    from astro_mcp.core import ephemeris_provider as ep

    # Calling twice in the same thread must not re-apply (TLS flag set).
    ep._ensure_ephe_path()
    assert getattr(ep._tls, "ephe_applied", False)
    ep._ensure_ephe_path()  # no error, no state change


def test_ephe_directory_contents_match_expected_files():
    # Guards the CI/deploy cache: a partial download must not pass silently
    # just because one .se1 file happens to be present.
    from astro_mcp.config import settings

    names = {os.path.basename(p) for p in os.listdir(settings.ephe_path)}
    assert {"seas_18.se1", "sepl_18.se1", "semo_18.se1"} <= names
