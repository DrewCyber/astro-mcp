# AGENTS.md — working notes for coding agents

## Quality gates (all must pass before committing)

```bash
pytest -q                      # coverage floor enforced via pyproject addopts (83%)
ruff check src tests
mypy --strict src
```

Raise the coverage floor when coverage grows; never lower it.

## Architecture invariants

- Layering: `server → tools → core`. No logic in the transport layer.
- Tools consume the full-precision `NatalChart` (`tools/natal.compute_natal`);
  serialize only at the MCP edge. Never re-parse serialized output — it is
  rounded and drops `speed`.
- Schemas in `schemas.py` are the single source of truth for tool inputs.
  Lockstep tests enforce both names and defaults against function signatures
  (`INTERNAL_PARAMS` in `tests/test_schemas.py` exempts internal-only params
  like `chart`). Keep them green instead of bypassing them.
- Errors: raise `AstroError(code, message, hint=...)` with codes from the
  closed set in `core/errors.py`. Only `server.py` formats error payloads;
  `INTERNAL_ERROR` must not leak internals.

## Domain conventions that were bugs before — do not regress

- Day/night sect comes from `NatalChart.is_day` (solar altitude via
  `swe.azalt`), NOT from house numbers. Houses 7–12 are above the horizon.
- Resolve chart keys to swe ids only through `ephemeris_provider.pid_for()`;
  `NN` honours `NODE_TYPE`, `SN` is derived. Never use raw `PLANET_IDS[key]`
  lookups for transiting bodies.
- `.se1` files cover **1800–2400**. Out-of-coverage dates raise
  `EPHEMERIS_OUT_OF_RANGE`; missing files raise `EPHEMERIS_UNAVAILABLE`.
  Do not widen schema year bounds past real file coverage.
- Aspect-date grouping in `find_aspect_exact_dates` is synodic-aware:
  fast pairs (Moon, Mercury, …) emit one occurrence per crossing. A "triple
  pass" label requires an actual retrograde loop.
- Progressed angles are quotidian (~360+1°/year) and labelled
  `angles_method: "quotidian"` — they intentionally differ from Astro.com's
  solar-arc MC/Asc.
- Naive datetimes are intentional: a birth time is wall-clock local time and
  DST folds are resolved in `geocoding.local_to_utc`. Do not attach tzinfo
  earlier; DTZ lint rules are suppressed on purpose.
- Rectification scores only exactly-dated events and only time-sensitive
  natal points (angles + Moon); scores are relative within one call.
- Davison space midpoint is the great-circle vector mean (antimeridian-safe).
- Geocoding: keys are normalized before caching, failures negatively cached
  300 s, Nominatim rate-limited to 1 req/s. Don't bypass `resolve_location`.
- `to_jd` accepts UTC only (naive or Z/+00:00).

## Repo hygiene

- Personal material lives in ignored dirs (`tmp/`, `private/`, `context/`,
  `.kilo/` are excluded locally). Never `git add` personal files.
- Commit messages are prefixed with `ox-alpha` per owner preference.
- Remaining known gap: behavioral tests for `tools/planetary_hours.py` and
  dispatcher-level tests (unknown tool / error mapping through
  `server.call_tool`). See `context/CODE_AUDIT.md`.
