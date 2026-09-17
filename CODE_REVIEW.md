# Code review remediation tracker

Review baseline: `7e8cff8`. Remediation branch: `union-alpha/review-remediation`.

Check an item only after regression tests and the full pytest, Ruff, and strict mypy gates pass. Commit messages use `Union Alpha:`. Original review severity labels used P0 for confirmed bugs, not production emergencies; this tracker instead groups by fix area. Suspected risks require validation before changes.

## Ordered remediation

- [x] R01 Cross-chart aspects: preserve same-body contacts; fixed natal targets must have zero effective speed. (`core/ephemeris_provider.py`, transit/progression/return/synastry/rectification callers)
- [x] R02 Exact-aspect bisection: reject angular discontinuities, validate residuals and exact endpoints.
- [x] R03 Internal precision: retain raw point longitude/speed/orb; consistent node motion; normalize serialization carry at sign boundaries.
- [x] R04 Derived tools: Arabic parts and antiscia must calculate contacts from raw points, never serialized `deg`; reflected motion must reverse sign.
- [ ] R05 Geocoding: propagate provider exceptions; bounded negative cache with correct error categories; validate persistent entries; safe concurrent persistence.
- [x] R06 Planetary hours: anchor requested day in location timezone; output timezone only renders; chronological sunrise/sunset.
- [x] R07 Aspect occurrence grouping: distinguish branches and actual retrograde loops; avoid out-of-coverage auxiliary reads; include exact scan samples.
- [x] R08 Profections: activated rulers follow profected signs rather than quadrant cusps.
- [x] R09 Progressions: reported progressed instant derives from computed Julian day.
- [x] R10 Davison: resolve house system at midpoint latitude, not first birthplace.
- [x] R11 Synastry: nonnegative compatibility weights with custom orbs.
- [x] R12 Rectification: internal progression results rather than wire form; remove synthetic sign-cusp scoring inconsistent with angles/Moon contract.
- [x] R13 Sect helper: require explicit solar-altitude sect; remove house-based fallback.
- [x] R14 Dispatcher: MCP error envelope and sanitized unexpected ValueError/serialization failures.
- [x] R15 CI: release image publication depends on quality gates; frozen dependency installs in CI and Docker.
- [ ] R16 HTTP: configured Host/Origin validation and bounded admission; assess quotas/auth without silently changing public access contract.
- [x] R17 Orb schemas: recognized keys and bounded finite values.
- [ ] R18 Ephemeris downloads: pinned source, checksums, atomic downloads, validation of existing files.
- [ ] R19 Ephemeris initialization/thread policy and sunrise error/fallback handling: validate reported risks, enforce consistent initialization.
- [x] R20 Preserve fractional seconds in Julian-day conversion.
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

### R12 — rectification internal computations

Extracted shared progressed-point computation and removed rectification's call to the serialized public tool. Removed synthetic profected sign-cusp scoring; the transiting year lord is scored against actual natal angles/Moon. Progression-only calls no longer construct unused event transit charts. Regressions forbid those public/unused paths and enforce the target set. Full gates: 390 tests, 91.54% coverage, Ruff and strict mypy clean.

### R03 — internal precision and chart serialization

Points, speeds, cusps, derived nodes and aspect orbs no longer round inside the calculation layer. Tool payloads round aspect orbs explicitly. Chart point/house serializers carry rounded positions across sign boundaries, including traditional/modern ruler metadata; DMS uses whole-second precision rather than first reducing to hundredths of a degree. Four precision regressions and unchanged Einstein golden pins pass. Full verbose suite: 388 tests, 91.53% coverage, Ruff and strict mypy clean.

### R07 — bounded aspect scans and branch-aware groups

Removed the annual auxiliary ephemeris scan. Exact endpoint/sample hits are included once; both scanning and orb-window walks stay inside the requested interval. Grouping checks continuous directed separation and reversed relative motion rather than temporal proximity alone; fast transit pairs remain independent. Regressions preserve the three 2021 Saturn–Uranus squares, separate six 2026 Mercury–Sun conjunctions and 24 lunar sextiles, and permit short December 2399 ranges. An independent hourly directed-arc count confirmed 12 sextiles per branch (the initial test expectation of 25 total was corrected). Full gates: 384 tests, 91.46% coverage, Ruff and strict mypy clean.

### R04 — antiscia raw contacts and reflected motion

Completed the remaining antiscia half of R04 (Arabic parts were fixed earlier). Natal and transit contacts consume internal mirrored points, not rounded output dictionaries; both reflections reverse speed. Four decimal/DMS boundary regressions cover contacts inside/outside the orb, reflected retrograde flags, dictionary output and JSON serialization. Full gates: 377 tests, 91.42% coverage, Ruff and strict mypy clean. The shared point builder's six-decimal rounding remains tracked separately under R03.

### R11 — synastry weights

Reproduced a negative harmony total for a 10-degree conjunction accepted through a wide custom orb. Compatibility weights now clamp at zero. Nine focused tests pass; full gates: 373 tests, 91.42% coverage, Ruff and strict mypy clean.

### R10 — Davison midpoint houses

Two births at 60°N and ±80° longitude reproduce a Placidus failure at their 84.27°N midpoint. The requested house system is now resolved at that midpoint, preserving the existing whole-sign fallback policy and reporting its warning. Eight focused tests pass; full gates: 371 tests, 91.42% coverage, Ruff and strict mypy clean.

### R09 — progressed instant

A 23:30 UTC birth reproduced a one-day discrepancy between `prog_day` and the actual progressed Julian day. The date now comes from that Julian day, with the full instant exposed as `prog_datetime_utc`. UTC and Tokyo boundary regressions pass, as do all six progression tests. Full gates: 370 tests, 91.41% coverage, Ruff and strict mypy clean.

### R15 / R17 — release gating and orb validation

Release publication now depends on the complete test matrix. CI and Docker use the frozen uv lock; CI keeps development extras across commands. Orb overrides reject unknown aspect names, nonfinite values and values outside 0–15 degrees. Six regression cases pass; full gates: 368 tests, 91.41% coverage, Ruff and strict mypy clean. `uv lock --check` and frozen development/runtime dry-runs pass. Container build and hosted smoke test have not been run locally.

### R14 — dispatcher errors

`Union Alpha: mark MCP failures and sanitize unexpected execution errors`

Added seven protocol regressions in `tests/test_review_dispatcher.py`. Baseline fails on `is_error=False` and discloses `private-path`; restored fix passes all 14 dispatcher tests. Full working-tree gates: 351 passed, 90.23% coverage, Ruff clean, strict mypy clean. Other in-progress changes are not included in this commit.

### R06 — planetary hours

Committed as `e11187e` (Union Alpha prefix). Tokyo reproduction produced backward hours before the fix; output timezones now affect rendering only. Ten planetary-hours tests passed; full gates at commit time: 328 passed, Ruff and strict mypy clean.
