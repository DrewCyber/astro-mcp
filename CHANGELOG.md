# Changelog

All notable changes to this project are documented here.
The project follows semantic versioning; correctness fixes bump the patch
version so downstream installs can tell broken from fixed builds.

## [1.1.0] — 2026-09-04

Remote deployment: the server can now be reached over HTTP as a claude.ai
custom connector instead of only as a local stdio process. See `DEPLOY.md`.

### Fixed

- **Ephemeris path could silently miss worker threads** — tools run via
  `asyncio.to_thread` while `swe.set_ephe_path` had only been applied at
  import time in the main thread. In pyswisseph builds where that state is
  thread-local (observed in an emulated amd64 container), every remote
  request degraded to the Moshier fallback and returned
  `EPHEMERIS_UNAVAILABLE`. The path is now re-applied once per thread at the
  two file-dependent entry points (`calc_planet`, `calc_rise_set`).
- `scripts/download_ephe.sh` fetched `fixstars.cat`, which no longer exists
  upstream (404 broke cold-cache CI and image builds); now fetches
  `sefstars.txt` — the file the repo actually ships.

### Added

- Streamable-HTTP transport (`ASTRO_MCP_TRANSPORT=http`, `HOST`, `PORT`):
  stateless, session-free `/mcp` endpoint plus `/health` for uptime pings.
  `POST /mcp` is answered directly — never a 307 redirect to `/mcp/` —
  because some MCP clients do not follow redirects.
- `Dockerfile` + `.dockerignore` (Python 3.11 base: pyswisseph cp311 wheels
  need no C toolchain) with ephemeris data baked in.
- `render.yaml` blueprint and a one-click **Deploy to Render** button
  (free tier, no credit card) for personal remote instances.
- CI `docker-build` job that builds the image, smoke-tests `/health` and
  `/mcp`, and publishes it to GitHub Container Registry
  (`ghcr.io/drewcyber/astro-mcp`, tags `X.Y.Z` / `X.Y` / `latest`); triggered
  only by version tags (`v*`), while the test matrix runs on every push and
  pull request.
- `DEPLOY.md`: free hosting guide (RU/EN) — shared instance, Render,
  `cloudflared` tunnel, Cloud Run, Koyeb, keepalive and troubleshooting.
- Explicit `starlette`/`uvicorn` dependencies (imported directly) and
  `tzdata` as a `zoneinfo` fallback in slim containers.

### Changed

- **Migrated to `mcp` 2.1** (from 1.27): 2.x replaced decorator registration
  with constructor handlers (`on_list_tools` / `on_call_tool`) and added
  `Server.streamable_http_app()`, which now backs the HTTP transport — the
  hand-rolled session-manager wiring and the redirect-avoiding route are the
  SDK's own. `serverInfo` now reports the package version instead of the
  SDK's. Dependency bound `mcp>=2.1,<3`.
- All dependencies refreshed to current releases (starlette 1.6, uvicorn 0.52,
  geopy 2.5, timezonefinder 8.3, pydantic 2.13, pytest 9, ruff 0.16,
  mypy 2.3). mypy target moved to 3.12 because numpy 2.5 stubs (via
  timezonefinder) use PEP 695 syntax; ruff still enforces the 3.11 syntax
  floor.

## [1.0.1] — 2026-08-24

Correctness fixes from the 2026-08-22 review (`context/CODE_REVIEW_OX_ALPHA_2026-08-22.md`).

### Fixed

- **Arabic parts day/night detection was inverted** — every chart received the
  opposite sect (Fortune/Spirit swapped, all sect-based lots wrong). Sect is now
  derived once from solar altitude and stored on `NatalChart.is_day`. (R-1)
- **`find_aspect_exact_dates` collapsed fast pairs into one fabricated
  "triple pass"** — twelve lunations in a year reported as a single retrograde
  loop. Grouping is now capped at half the pair's synodic cycle. (R-2)
- **Rectification's `profections` technique was a silent no-op** — advertised,
  budgeted, and reported but never scored. Now implemented. (R-3)
- **Node flavour inconsistency** — `find_aspect_exact_dates`/`get_ephemeris`
  scanned the True Node even with `NODE_TYPE=mean`; all tools share one
  `pid_for()` resolver. (R-4)
- **Out-of-range dates misreported as missing ephemeris files** — new
  `EPHEMERIS_OUT_OF_RANGE` names the covered span; solar-return `year` bounded
  to 1800–2400. (R-5)
- **Davison midpoint broke across the antimeridian** — great-circle midpoint
  via vector mean, reported in the payload. (R-12)
- **`to_jd` silently dropped non-UTC offsets** — now rejected. (R-13)
- **Non-exact events were scored in rectification** although documented as not
  counting. (R-11)
- Progressed angles disclosed as quotidian convention (`angles_method`). (R-7)

### Changed

- Rectification scoring hoists redundant chart computation (~30x faster scans). (R-10)
- Geocoding: normalized cache keys, negative cache, Nominatim rate limiting. (R-9)
- CI: coverage floor (`--cov-fail-under=83`), Python 3.13 matrix entry,
  bounded dev dependencies. (R-16)

### Removed

- Dead code: unused TypedDicts, never-populated `Aspect.exact_date`,
  `dms_to_decimal`, duplicated sign helper. (R-14)

## [1.0.0] — 2026-07-26

Initial release following the first full audit.
