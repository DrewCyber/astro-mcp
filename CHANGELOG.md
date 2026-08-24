# Changelog

All notable changes to this project are documented here.
The project follows semantic versioning; correctness fixes bump the patch
version so downstream installs can tell broken from fixed builds.

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
