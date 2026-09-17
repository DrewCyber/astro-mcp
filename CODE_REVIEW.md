# Code review remediation tracker

Review baseline: `7e8cff8`. Remediation branch: `union-alpha/review-remediation`.

Check an item only after regression tests and the full pytest, Ruff, and strict mypy gates pass. Commit messages use `Union Alpha:`. Original review severity labels used P0 for confirmed bugs, not production emergencies; this tracker instead groups by fix area. Suspected risks require validation before changes.

## Ordered remediation

- [ ] R01 Cross-chart aspects: preserve same-body contacts; fixed natal targets must have zero effective speed. (`core/ephemeris_provider.py`, transit/progression/return/synastry/rectification callers)
- [ ] R02 Exact-aspect bisection: reject angular discontinuities, validate residuals and exact endpoints.
- [ ] R03 Internal precision: retain raw point longitude/speed/orb; consistent node motion; normalize serialization carry at sign boundaries.
- [ ] R04 Derived tools: Arabic parts and antiscia must calculate contacts from raw points, never serialized `deg`; reflected motion must reverse sign.
- [ ] R05 Geocoding: propagate provider exceptions; bounded negative cache with correct error categories; validate persistent entries; safe concurrent persistence.
- [x] R06 Planetary hours: anchor requested day in location timezone; output timezone only renders; chronological sunrise/sunset.
- [ ] R07 Aspect occurrence grouping: distinguish branches and actual retrograde loops; avoid out-of-coverage auxiliary reads; include exact scan samples.
- [ ] R08 Profections: activated rulers follow profected signs rather than quadrant cusps.
- [ ] R09 Progressions: reported progressed instant derives from computed Julian day.
- [ ] R10 Davison: resolve house system at midpoint latitude, not first birthplace.
- [ ] R11 Synastry: nonnegative compatibility weights with custom orbs.
- [ ] R12 Rectification: internal progression results rather than wire form; remove synthetic sign-cusp scoring inconsistent with angles/Moon contract.
- [ ] R13 Sect helper: require explicit solar-altitude sect; remove house-based fallback.
- [x] R14 Dispatcher: MCP error envelope and sanitized unexpected ValueError/serialization failures.
- [ ] R15 CI: release image publication depends on quality gates; frozen dependency installs in CI and Docker.
- [ ] R16 HTTP: configured Host/Origin validation and bounded admission; assess quotas/auth without silently changing public access contract.
- [ ] R17 Orb schemas: recognized keys and bounded finite values.
- [ ] R18 Ephemeris downloads: pinned source, checksums, atomic downloads, validation of existing files.
- [ ] R19 Ephemeris initialization/thread policy and sunrise error/fallback handling: validate reported risks, enforce consistent initialization.
- [ ] R20 Preserve fractional seconds in Julian-day conversion.
- [ ] R21 Reduce repeated lunar and rectification computations without changing results.
- [ ] R22 Broaden regression/HTTP tests; raise coverage floor if achieved coverage permits.

## Validation record

Baseline review: 326 tests passed, 90.26% statement coverage; Ruff and strict mypy passed. No Docker image build or hosted deployment test in the original review.

## Recommendations (not automatic product scope)

- Property-based wraparound/date-boundary tests.
- Independent astronomical reference datasets beyond Einstein goldens.
- Structured per-tool latency/error metrics without birth-data logging.
- Generated conventions documentation sourced from constants.
- Optional authenticated deployment mode and per-client quotas; deployment identity/proxy trust need explicit design.

## Completed fixes

Git history supplies commit hashes.

### R14 — dispatcher errors

`Union Alpha: mark MCP failures and sanitize unexpected execution errors`

Added seven protocol regressions in `tests/test_review_dispatcher.py`. Baseline fails on `is_error=False` and discloses `private-path`; restored fix passes all 14 dispatcher tests. Full working-tree gates: 351 passed, 90.23% coverage, Ruff clean, strict mypy clean. Other in-progress changes are not included in this commit.

### R06 — planetary hours

Committed as `e11187e` (Union Alpha prefix). Tokyo reproduction produced backward hours before the fix; output timezones now affect rendering only. Ten planetary-hours tests passed; full gates at commit time: 328 passed, Ruff and strict mypy clean.
