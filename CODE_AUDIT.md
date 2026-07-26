# astro-mcp — Code Audit & Recommendations

**Audit date:** 2026-07-26
**Scope:** `src/astro_mcp/` (21 modules, ~2,100 LOC), `tests/` (10 files, 57 tests), packaging & repo hygiene
**Toolchain used:** `pytest`, `ruff`, `mypy --strict`, targeted runtime probes
**Remediation status:** all Critical, High and Medium findings resolved — see [§8](#8-remediation-outcome)

---

## 1. Executive summary

The project is well-structured: a clean `server → tools → core` layering, consistent compact-JSON output contract, and a genuinely good DST-handling implementation in `local_to_utc`. The 57 existing tests pass.

However, the audit found **several correctness defects that silently return wrong astrological data**, plus one feature that is advertised in the tool schema but not implemented, and one tool that returns hard-coded placeholder values presented as real results. Because this server feeds an LLM, wrong-but-plausible output is the highest-impact failure mode — the model has no way to detect it.

| Severity | Count | Theme |
|---|---|---|
| Critical | 4 | Silently wrong results / fabricated output |
| High | 6 | Precision loss, unimplemented features, blocking event loop |
| Medium | 9 | Inconsistent conventions, missing validation, dead config |
| Low | 5 | Hygiene, lint, docs, packaging |

**Current quality gates:**

| Gate | Result |
|---|---|
| `pytest` | 57 passed |
| `ruff check src` | **69 errors** (28 unused imports, 11 unused variables, 18 unsorted import blocks) |
| `mypy --strict src` | **60 errors in 14 files** |
| CI workflow | **none** (`.github/` contains only agent definitions) |
| Coverage gate | none configured |

---

## 2. Critical findings

### C-1 — Synastry house overlays are computed against the wrong chart

**File:** [src/astro_mcp/tools/synastry.py](src/astro_mcp/tools/synastry.py#L74)

`p1_planets_in_p2_houses` is built as `{k: v.house for k, v in pts1.items()}` — i.e. Person 1's planets in **Person 1's own** houses. The same for `p2_in_p1`. House overlay is the single most-used synastry technique and it is currently meaningless.

Verified at runtime: the overlay map returned by `calculate_synastry` is byte-identical to the `house` values in Person 1's own natal chart.

The function also contains ~25 lines of abandoned scaffolding (`house_for_lon`, which unconditionally `return 1` on the first loop iteration, plus three dead loops) that mask the defect during review.

**Fix**

```python
from astro_mcp.core.ephemeris_provider import house_of

# resolve cusps once per chart instead of round-tripping serialised output
cusps1 = _cusps_from_chart(n1)   # list[float], 12 entries
cusps2 = _cusps_from_chart(n2)

p1_in_p2 = {k: house_of(pt.lon_decimal, cusps2)
            for k, pt in pts1.items() if k not in ANGLE_KEYS}
p2_in_p1 = {k: house_of(pt.lon_decimal, cusps1)
            for k, pt in pts2.items() if k not in ANGLE_KEYS}
```

Delete `house_for_lon` and the dead loops entirely.

---

### C-2 — `find_aspect_exact_dates` returns fabricated fields

**File:** [src/astro_mcp/tools/ephemeris.py](src/astro_mcp/tools/ephemeris.py#L262)

Every occurrence is emitted with hard-coded values:

```python
"retrograde_exact": None,
"direct_exact": exact_date,
"is_triple_pass": False,
"peak_orb": 0.01,
```

Verified runtime output for `Ma–Sa Cnj, 2026`:

```json
{"approach_date":"2026-04-18","exact_date":"2026-04-19","separation_date":"2026-04-21",
 "retrograde_exact":null,"direct_exact":"2026-04-19","is_triple_pass":false,"peak_orb":0.01}
```

`is_triple_pass` and `peak_orb` are never computed. An LLM will report "this is not a triple pass" as fact. Triple passes (retrograde stations inside the orb window) are exactly what users ask this tool for.

**Fix (pick one, do not ship as-is):**
1. **Remove** the four fields from the payload, or
2. **Compute** them: group crossings of the same aspect within a ±~7-month window, mark `is_triple_pass` when 3 crossings occur, classify each by the sign of the transiting body's speed at exactness, and compute `peak_orb` as the actual minimum orb in the window.

Option 2 is the correct product answer; option 1 is the correct immediate safety fix.

---

### C-3 — Annual profections use `days // 365`, producing an off-by-one house

**File:** [src/astro_mcp/tools/profections.py](src/astro_mcp/tools/profections.py#L38)

```python
age = (t_date - b_date).days // 365
```

Leap days accumulate, so the profected year rolls over **before** the actual birthday. Verified for birth `1990-03-15`:

| Target date | Correct age / house | Returned |
|---|---|---|
| 2026-03-13 | 35 → 12th house | **36 → 1st house** |
| 2026-03-14 | 35 → 12th house | **36 → 1st house** |
| 2018-03-14 | 27 → 4th house | **28 → 5th house** |

The whole tool output (profected house, sign, year lord, activated planets) is wrong for those dates — and the year lord is the primary deliverable of the technique.

**Fix**

```python
age = t_date.year - b_date.year - ((t_date.month, t_date.day) < (b_date.month, b_date.day))
```

Additionally, `b_date` is derived from `natal["meta"]["dt"]`, which is the **UTC** timestamp — for births near local midnight the birthday shifts by a day. Use the caller's local `birth_date` instead.

---

### C-4 — Swiss Ephemeris error flags are discarded

**File:** [src/astro_mcp/core/ephemeris_provider.py](src/astro_mcp/core/ephemeris_provider.py#L79)

```python
result, _ = swe.calc_ut(jd, planet_id, flags)
return result[0], result[3]
```

The second return value is the return flag / error string. With `FLG_SWIEPH` and a missing or out-of-range `.se1` file (Chiron is only valid 675–4650 AD; asteroid files have their own limits), `pyswisseph` degrades to a fallback or returns an error state — and this code returns whatever is in `result[0]` as if it were valid. Same pattern in `calc_rise_set`, where a polar day/night (no rise or set) is not detected at all and `get_planetary_hours` will silently emit nonsense hour boundaries.

**Fix**

```python
def calc_planet(jd: float, planet_id: int) -> tuple[float, float]:
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    result, retflag = swe.calc_ut(jd, planet_id, flags)
    if retflag < 0:
        raise ValueError(f"EPHEMERIS_ERROR: swisseph failed for body {planet_id} at JD {jd}")
    return result[0], result[3]
```

And in `calc_rise_set`, check the returned status and raise `NO_RISE_SET` for polar conditions so `get_planetary_hours` can report a proper error instead of fake times.

---

## 3. High findings

### H-1 — Chart data is round-tripped through rounded JSON, losing precision everywhere

**File:** [src/astro_mcp/tools/transits.py](src/astro_mcp/tools/transits.py#L27)

`_natal_to_points()` reconstructs `ChartPoint` objects by re-parsing the **serialised** natal output, where `deg` was already rounded to 2 decimals by `serialize_point`. Every downstream tool — transits, progressions, returns, synastry, composite, profections, rectification, arabic parts, antiscia — consumes natal positions through this path.

Consequences:
- Up to **±0.005° (18 arcsec)** error injected into every natal position, and hence into every orb, every exact-date bisection seed, and every solar/lunar return target longitude.
- `speed` is forced to `0.0`, so the `applying` flag on all transit/synastry aspects is computed from a wrong relative velocity.
- `sign` is read from the dict while `lon_decimal` is recomputed from the rounded `deg` — the two can disagree at a sign boundary.

**Fix (architectural, highest ROI in this report):** have the natal computation return a typed internal object and serialise only at the edge.

```python
@dataclass
class NatalChart:
    meta: dict[str, Any]
    planets: dict[str, ChartPoint]
    angles: dict[str, ChartPoint]
    cusps: list[float]
    aspects: list[Aspect]

def compute_natal(...) -> NatalChart: ...          # internal, full precision
def calculate_natal_chart(...) -> dict[str, Any]:  # MCP boundary, serialises
    return serialize_natal(compute_natal(...))
```

All tools then call `compute_natal` and `_natal_to_points` disappears. This also removes the `synastry → transits` import cycle (`synastry.py` importing a private helper from `transits.py` is a layering violation in itself).

---

### H-2 — `period_days` is advertised but silently ignored

**Files:** [src/astro_mcp/server.py](src/astro_mcp/server.py#L100), [src/astro_mcp/tools/transits.py](src/astro_mcp/tools/transits.py#L94)

The schema exposes `period_days` with `"maximum": 3650`, but the implementation is:

```python
dates = [date_obj + timedelta(days=i) for i in range(max(1, period_days))]
for d in dates[:1]:      # <-- only the first date
    ...
    return {...}         # returns from inside the loop
return {}                # unreachable in practice
```

Verified: `period_days=30` returns a single-day payload. `period_days` only leaks into the exact-date bisection window. An LLM asked for "transits over the next month" will confidently answer from one day of data.

**Fix:** either implement the multi-day scan (returning aspect windows with ingress/exact/egress per aspect), or remove `period_days` from the schema. Do not leave it advertised-but-inert.

---

### H-3 — `is_applying` mis-classifies aspects when the arc exceeds 180°

**File:** [src/astro_mcp/core/ephemeris_provider.py](src/astro_mcp/core/ephemeris_provider.py#L207)

```python
diff = (lon1 - lon2) % 360
return (relative_speed < 0 and diff < asp_angle) or (relative_speed > 0 and diff > asp_angle)
```

`diff` lives in `[0, 360)` but is compared against `asp_angle ∈ [0, 180]`. For any pair whose directed arc is in the upper half-circle, the exact-aspect arc is `360 - asp_angle`, not `asp_angle`. E.g. a trine with `diff = 250°` (true separation 110°, separating) is reported as **applying**. Roughly half of all aspect pairs fall in this region.

The exact-hit case is also wrong: `diff == asp_angle` returns `False` for both branches.

**Fix**

```python
def is_applying(lon1, speed1, lon2, speed2, asp_angle) -> bool:
    diff = (lon1 - lon2) % 360
    target = asp_angle if diff <= 180 else (360 - asp_angle) % 360
    delta = diff - target                       # signed distance to exactness
    rel = speed1 - speed2
    if rel == 0 or delta == 0:
        return False
    return (delta > 0 and rel < 0) or (delta < 0 and rel > 0)
```

Add a unit test matrix covering all four quadrants for each aspect angle.

---

### H-4 — Natal chart uses True Node, every other tool uses Mean Node

**Files:** [src/astro_mcp/core/ephemeris_provider.py](src/astro_mcp/core/ephemeris_provider.py#L96), [src/astro_mcp/tools/transits.py](src/astro_mcp/tools/transits.py#L104), [src/astro_mcp/tools/rectification.py](src/astro_mcp/tools/rectification.py#L86)

`calc_all_planets` defaults to `use_mean_node=False` (True Node, swe ID 11). `natal.py` accepts that default; `transits.py` and `rectification.py` explicitly pass `use_mean_node=True`; `returns.py`, `progressions.py`, `synastry.py` and `antiscia.py` use the default again.

True and Mean Node diverge by up to **±1.7°**, so transit-to-natal node aspects are computed between two different definitions of the same point. Node aspects near the orb boundary will appear and disappear depending on which tool is called.

**Fix:** promote node selection to `Settings` (`NODE_TYPE=true|mean`, default `true`), thread it through every call site, and echo the choice in `meta` so the output is self-describing.

---

### H-5 — Synchronous CPU-bound tools block the MCP event loop

**File:** [src/astro_mcp/server.py](src/astro_mcp/server.py#L405)

`call_tool` is `async` but calls the tool functions directly. `calculate_rectification_hints` with the default 4-minute step evaluates **360 candidate times**, and for each candidate builds a natal chart plus a transit chart and a full progression per event. With 5 events that is on the order of **4,000 full chart computations** in a single synchronous call. The server cannot answer anything — including `list_tools` or a cancellation — while it runs.

**Fix**

```python
result = await asyncio.to_thread(tool_fn, **validated_args)
```

Plus a per-tool time budget, and a hard cap on `(time range / time_step_min) × len(events)` in the rectification tool with an actionable error when exceeded.

---

### H-6 — Rectification scoring is dominated by time-invariant factors

**File:** [src/astro_mcp/tools/rectification.py](src/astro_mcp/tools/rectification.py#L59)

`_score_candidate` scores **all** transit-to-natal aspects. For a candidate set spanning one day, only the Moon (~13°/day), the Ascendant/MC, and house cusps actually change; every other transit-to-natal aspect contributes an identical score to all 360 candidates. That constant offset:

- inflates every score toward the arbitrary `score < 30 → NO_CANDIDATES` threshold, so the guard rarely triggers;
- compresses the relative gap between candidates, which then feeds the `gap > 15 → "high"` confidence heuristic — so the tool reports **high confidence on essentially undifferentiated candidates**.

**Fix:** restrict scoring to time-sensitive significators only (angles, house cusps, house placements, Moon, progressed MC/Asc), or subtract the per-event baseline score (`score(candidate) - min over candidates`) before ranking. Re-derive the confidence heuristic from the normalised spread, not the raw gap. Until then, the tool's `confidence` field should be documented as heuristic and not surfaced as a probability.

Secondary issues in the same file:
- `geo = resolve_location(birth_location)` at line 187 is computed and never used (`F841`).
- The `_score_candidate` parameter named `geo` actually receives an unresolved `birth_location`; it then re-resolves internally. Rename for clarity.
- The `TOO_FEW_EVENTS` guard at line 149 has an inverted nested condition — events with `date_accuracy != "exact"` count toward the minimum, contradicting the error message ("at least 3 events with known dates").

---

## 4. Medium findings

### M-1 — No input validation at the MCP boundary

**File:** [src/astro_mcp/server.py](src/astro_mcp/server.py#L406)

`result = calculate_natal_chart(**arguments)` splats untrusted client input directly into Python signatures. An unexpected key produces a `TypeError` surfaced as `INTERNAL_ERROR` with the raw exception text.

Missing validation includes:
- **Latitude / longitude range.** `resolve_location` does `float(location["lat"])` with no bounds check; `lat = 999` reaches `swe.houses` and yields garbage cusps rather than an error.
- **Date / time format.** Malformed strings reach `date.fromisoformat` / `datetime.strptime`; the resulting `ValueError` text is used as an error *code* (see M-2).
- **Missing keys.** `location["lat"]` raises `KeyError`, which is not caught by the `except ValueError` branch and becomes `INTERNAL_ERROR`.
- **Year range.** No guard against dates outside the ephemeris files' validity.

**Fix:** define a Pydantic model per tool (you already depend on Pydantic), validate in the dispatcher, and map `ValidationError` to a structured `INPUT_ERROR` payload. This also lets you generate the JSON schemas from the models instead of hand-maintaining ~340 lines of literal schema in `server.py`.

---

### M-2 — Error-code derivation produces sentence fragments as codes

**File:** [src/astro_mcp/server.py](src/astro_mcp/server.py#L473)

```python
code = str(exc).split(":")[0] if ":" in str(exc) else "INPUT_ERROR"
```

Any `ValueError` containing a colon becomes the code. A malformed date yields `code = "Invalid isoformat string"`. Codes must come from a closed enum, not from message text.

**Fix:** introduce `class AstroError(Exception)` with an explicit `code` attribute; raise `AstroError("GEOCODE_FAILED", ...)` etc. and map unknown exceptions to a fixed `INTERNAL_ERROR`.

---

### M-3 — Two incompatible error conventions

Tools such as `calculate_transits`, `calculate_solar_return` and `calculate_profections` `return {"error": True, "code": ...}`, which the dispatcher wraps in `_ok()` — an **error payload delivered through the success path**. Others (`natal`, `geocoding`) raise `ValueError`, which goes through `_err()`. Clients cannot rely on either.

**Fix:** pick raising `AstroError` as the single convention; the dispatcher is the only place that formats errors.

---

### M-4 — Internal exception text is echoed to the client

**File:** [src/astro_mcp/server.py](src/astro_mcp/server.py#L477)

```python
return _err("INTERNAL_ERROR", f"Unexpected error: {exc}")
```

Unexpected exception strings can contain file paths, API keys embedded in geocoder URLs, or library internals. Log the detail server-side (already done via `logger.exception`) and return a generic message plus a correlation id.

---

### M-5 — Ephemeris path resolution depends on the process working directory

**File:** [src/astro_mcp/config.py](src/astro_mcp/config.py#L12) → [src/astro_mcp/core/ephemeris_provider.py](src/astro_mcp/core/ephemeris_provider.py#L22)

`ephe_path` defaults to the **relative** `"./ephe"`, and `swe.set_ephe_path()` is executed at import time. MCP clients launch the server from an arbitrary CWD, so the default silently resolves to a non-existent directory — and because of C-4 the resulting bad calculations are never reported.

**Fix:** resolve to an absolute path at startup, verify at least one `.se1` file is present, and fail fast with a clear message naming `EPHE_PATH` and `scripts/download_ephe.sh`. Move the `set_ephe_path` call out of module import into an explicit `init_ephemeris()` invoked from `_run()`.

---

### M-6 — Polar-latitude handling is applied in exactly one tool

**File:** [src/astro_mcp/tools/natal.py](src/astro_mcp/tools/natal.py#L38)

`natal.py` silently downgrades Placidus → Whole Sign above 66.5°, but `transits.py`, `returns.py`, `progressions.py`, `synastry.py` and `rectification.py` call `calc_houses(..., "P")` at any latitude. A natal chart and its own solar return can therefore use **different house systems** for the same person.

Additionally, the substitution is silent — `meta.hs` reports `W` but nothing tells the user a fallback occurred, and Koch (`K`) fails at high latitudes too but is not covered.

**Fix:** centralise as `resolve_house_system(requested, lat) -> (system, warning)` in `core/`, call it from every tool, and always emit the warning in `meta`.

---

### M-7 — Composite (midpoint) houses are derived from the Davison chart

**File:** [src/astro_mcp/tools/synastry.py](src/astro_mcp/tools/synastry.py#L186)

In the `method="midpoint"` branch, planets are correctly averaged as midpoints, but the house cusps come from `calc_houses(dav_jd, mean_lat, mean_lon, ...)` — i.e. the **Davison** chart. Planets then get house numbers from Davison cusps while `comp_angles` are midpoint angles. The two are internally inconsistent; a midpoint composite should derive its houses from the composite MC (or composite Asc) using the standard tables.

Two further defects in the same branch:
- `asc_lon` / `mc_lon` are assigned and never used (`F841`) — a partially-written implementation left in place.
- The vector-mean midpoint is undefined when the two longitudes are exactly opposed (`atan2(0, 0) → 0°`), silently yielding 0° Aries. Add an explicit rule (astrological convention: take the midpoint nearer the shorter arc, and document the tie-break).

---

### M-8 — `DEFAULT_HOUSE_SYSTEM` and `DEFAULT_ORB_FACTOR` are documented but never read

**Files:** [src/astro_mcp/config.py](src/astro_mcp/config.py#L15), [README.md](README.md#L79)

Both settings are defined in `Settings` and listed in the README's environment table, but grep shows zero consumers. `find_aspects(orb_factor=...)` exists but is never passed `settings.default_orb_factor`; every tool hard-codes `house_system="P"`.

**Fix:** wire them up (`house_system: str = settings.default_house_system`, `orb_factor=settings.default_orb_factor`) or delete both from config and README. Documented-but-inert configuration is worse than no configuration.

---

### M-9 — Serialised `lon` field changes type with `degree_format`

**File:** [src/astro_mcp/core/formatters.py](src/astro_mcp/core/formatters.py#L52)

```python
lon_str = decimal_to_dms(...) + point.sign   if dms
lon_str = str(round(point.lon_decimal, 2))   if dec
```

In `dec` mode `lon` is a stringified number sitting next to `deg`, which is already the same number as a float. This is redundant tokens plus a type that varies by parameter. Emit `lon` only in `dms` mode, or make it a number in `dec` mode.

Related: `lon_to_dms_with_sign` accepts a `lon_decimal` argument it never uses, and `dms_to_decimal` has no callers.

---

## 5. Low findings

### L-1 — Lint and type-check debt

- `ruff check src`: **69 errors** — 28 unused imports, 11 unused variables, 18 unsorted import blocks, 2 uses of the deprecated `datetime.utcnow()` ([returns.py](src/astro_mcp/tools/returns.py#L98), [returns.py](src/astro_mcp/tools/returns.py#L157)), 1 blind `except Exception` ([ephemeris.py](src/astro_mcp/tools/ephemeris.py#L123)).
- Several unused variables are the fingerprints of the abandoned implementations in C-1 and M-7, so `ruff` would have surfaced two of the critical/medium bugs on day one.
- `mypy --strict` is configured in `pyproject.toml` but **60 errors** exist in 14 files — the strict setting is currently decorative.

**Fix:** run `ruff check --fix src tests`, hand-fix the remaining 23, then add both tools to CI as blocking. If full `--strict` is not reachable now, ratchet: enable `disallow_untyped_defs` per-module and expand.

---

### L-2 — No CI pipeline

`.github/` contains only agent markdown; there is no workflow. Nothing enforces tests, lint, or types.

**Fix:** add `.github/workflows/ci.yml` running on 3.11/3.12/3.13 — cache the `ephe/` download, then `ruff check`, `mypy src`, `pytest --cov=astro_mcp --cov-fail-under=<baseline>`.

---

### L-3 — Test coverage gaps

Untested modules: `rectification.py`, `profections.py`, `planetary_hours.py`, `antiscia.py`, `server.py` (dispatch and error mapping), `geocoding.resolve_location`.

Notably, three of the four critical findings sit in untested code. Recommended additions:

- **Golden-chart regression tests.** Pin Einstein's chart positions to arcsecond tolerance against a published reference so ephemeris/flag regressions are caught.
- **Property tests** for `house_of` (every longitude maps to exactly one house; cusps are boundary-inclusive at the start) and `is_applying` (four-quadrant matrix per aspect angle).
- **Dispatcher tests** asserting unknown tool → `UNKNOWN_TOOL`, malformed input → `INPUT_ERROR`, and that no tool returns an `error: true` body through the success path.
- **Profection anniversary boundary tests** covering the day before, on, and after the birthday across leap-year spans.
- Network isolation: geocoding tests should be marked and mocked so the suite does not depend on Nominatim availability.

---

### L-4 — Packaging issues

**File:** [pyproject.toml](pyproject.toml#L19)

- `requests>=2.34.2` is a **runtime dependency that is never imported** anywhere in `src/`. Remove it. (`geopy` brings its own HTTP stack.)
- `httpx` sits in `dev` but is likewise unused.
- No `[tool.setuptools.package-data]` entry for `ephe/`, and no `py.typed` marker despite the strict-typing intent.
- `src/astro_mcp.egg-info/` is committed in the working tree; `*.egg-info/` is gitignored, so it is untracked noise — confirm it stays out of the repo.
- `version = "1.0.0"` with no changelog. Given the defects above, consider `0.x` until C-1…C-4 are resolved.

---

### L-5 — Documentation drift

- [README.md](README.md#L22) says `calculate_arabic_parts` computes "7 Arabic Parts"; the implementation supports **12** (`PART_FORMULAS` in [arabic_parts.py](src/astro_mcp/tools/arabic_parts.py#L20)).
- The README environment table documents two settings that do nothing (M-8).
- `tmp/Family_July2026_Brother1_recalc_25May.md` appears to be personal working data committed to the repo. `.gitignore` has a `private/` rule but not `tmp/` — move it or ignore the directory.
- The `_antiscia_lon` docstring contains a worked example whose intermediate wording ("More precisely: reflect over 90°/270° axis") reads as if the first formula were an approximation. The formula is correct; simplify the docstring.

---

## 6. Recommended remediation order

| Order | Item | Why first |
|---|---|---|
| 1 | C-4 ephemeris error flags; M-5 absolute `EPHE_PATH` + fail-fast | Everything else is unverifiable if the ephemeris silently misbehaves |
| 2 | C-2 remove/compute fabricated fields | Cheapest removal of fabricated data reaching the LLM |
| 3 | C-3 profection age; C-1 synastry overlays | Small, self-contained, each fixes a wholly wrong tool output |
| 4 | H-3 `is_applying`; H-4 node consistency | Core primitives; fix before writing regression tests |
| 5 | L-1 `ruff --fix` + L-2 CI | Locks in the above and prevents re-introduction |
| 6 | H-1 `NatalChart` refactor | Largest change; removes precision loss and the import cycle. Do it once tests exist |
| 7 | M-1/M-2/M-3/M-4 Pydantic validation + `AstroError` | Makes the MCP contract trustworthy; enables schema generation |
| 8 | H-5 `asyncio.to_thread` + budgets; H-6 rectification scoring | Turns rectification from a liability into a usable feature |
| 9 | H-2 `period_days`; M-6/M-7 house-system and composite consistency | Feature completeness |
| 10 | M-8, M-9, L-3, L-4, L-5 | Cleanup and hardening |

---

## 7. What is already good

Worth preserving through any refactor:

- **`local_to_utc`** ([geocoding.py](src/astro_mcp/core/geocoding.py#L72)) — the fold-based DST handling is genuinely careful, correctly distinguishes fall-back from spring-forward, documents the chosen convention, propagates a `dst_warning` to the output, and is backed by a dedicated 124-line test file. This is the standard the rest of the codebase should meet.
- **Module layering** — `server → tools → core` with no logic in the transport layer is the right shape; the only violations are `synastry → transits._natal_to_points` and the tool-to-tool calls that H-1 resolves.
- **Token-efficient output contract** — abbreviated codes, omitted `R` when direct, and `to_compact_json` are well-judged for an LLM consumer.
- **Signed-arc handling for conjunction/opposition** in `find_exact_aspect_jd` — the comment explaining why absolute distance cannot cross zero shows real understanding of the numerics.

---

## 8. Remediation outcome

All Critical, High and Medium findings are resolved. Low findings are resolved except L-3, which is partially addressed: regression coverage was added for every Critical/High defect, but broader per-tool coverage is still thin.

### Quality gates, before and after

| Gate | Before | After |
|---|---|---|
| `pytest` | 57 passed | **178 passed** |
| `ruff check src tests` | 69 errors | **clean** |
| `mypy --strict src` | 60 errors in 14 files | **clean** (23 modules) |
| CI workflow | none | `.github/workflows/ci.yml` (3.11 + 3.12) |
| Tools working via MCP dispatch | not verified | **14/14** |

### Verification highlights

Each Critical defect is now pinned by a behavioural test in [tests/test_audit_regressions.py](tests/test_audit_regressions.py):

- **C-1** — overlays are asserted equal to `house_of(person1_planet, person2_cusps)`, asserted *unequal* to each person's own natal houses, and asserted asymmetric between the two directions.
- **C-2** — the 2021 Saturn-square-Uranus triple pass is reproduced exactly (`2021-02-17`, `2021-06-14`, `2021-12-24`) with the middle pass correctly flagged retrograde. The 2020 Great Conjunction is asserted to be a *single* pass, guarding against over-grouping.
- **C-3** — profected age is checked on both sides of the anniversary boundary, including a leap-day birth. The old `days // 365` arithmetic drifted one day per leap year and moved the year lord early.
- **C-4** — an out-of-range body now raises rather than returning a Moshier-derived position.
- **H-3** — `is_applying` is exercised across 16 hand-derived cases spanning all four quadrants, plus an antisymmetry property test over the full circle.

### Corrections to the original findings

- **C-4 was understated.** The finding described discarded error flags. Runtime probing showed the failure mode is worse: with the `.se1` files absent, `swe.calc_ut` does **not** raise for the main planets — it silently substitutes the low-precision Moshier ephemeris and reports that only in the return flags (`retflag & FLG_MOSEPH`). Every chart would have been quietly degraded. `_check_calc_flags` now treats this as an error, and `init_ephemeris()` fails fast at startup.
- **C-2's `peak_orb` could not be salvaged.** Since every reported occurrence is a real perfection, a "tightest orb" is ~0 by construction and carries no information. It was replaced with `max_separation_orb`, emitted only for multi-pass occurrences, describing how far the bodies retreat mid-retrograde.
- **Two further latent bugs surfaced during the fixes**, both on dead paths that would have produced wrong numbers had they been reached: `_get_lon` in `arabic_parts.py` fell back to `idx * 30.0` for serialised house dicts (which never carry a `lon_decimal` key), and `requests>=2.34.2` in `pyproject.toml` pinned a version that does not exist, so a clean install would have failed. Both are removed.
- **The regression tests found two bugs in the fixes themselves.** The first `is_applying` rewrite still inverted its answer across the 0°/360° conjunction wrap, and the new `init_ephemeris` validation called `swe.set_ephe_path()` *before* validating, so a single negative test poisoned global Swiss Ephemeris state for the rest of the suite. Both are fixed; both were invisible without the tests.

### Deliberate non-changes

- **Naive datetimes** (`DTZ001`/`DTZ007`) are suppressed in ruff config rather than "fixed". A birth time is a wall-clock local time; attaching `tzinfo` before the fold resolution in `local_to_utc` would defeat the DST-ambiguity handling praised in §7.
- **`mypy` decorator rules** are relaxed for `astro_mcp.server` only, because the MCP SDK ships untyped decorators. The other 21 modules remain fully strict.
- **Rectification scores are now explicitly relative.** Restricting scoring to time-sensitive points (angles + Moon) means the old absolute `score < 30` cutoff no longer had meaning, so confidence is derived from the *relative* gap between top candidates and the output carries a `score_note` saying so.

### M-1 in detail: the schemas were the drift

Replacing the 260 lines of hand-written JSON Schema in `server.py` with Pydantic models ([schemas.py](src/astro_mcp/schemas.py)) was filed as a tidiness item. It turned out to be a correctness one. Comparing the models against the real function signatures found **four** mismatches that had been shipping:

| Tool | Mismatch |
|---|---|
| `find_aspect_exact_dates` | `degree_format` accepted in code, absent from the schema |
| `calculate_antiscia` | `orb` and `include_contra` accepted in code, absent from the schema |
| `calculate_antiscia` | `include_transits_date` **advertised in the schema, not accepted by the function** — any client that used it got an argument error |

The first three were documentation gaps. The last was a promise the code did not keep, so the feature was implemented rather than withdrawn, matching the decision taken for H-2. Transit contacts to antiscia are computed directly from the ephemeris (conjunctions only, as the tradition treats a mirrored degree) instead of routing through `calculate_transits`, which keeps the `tools -> core` layering intact.

`server.py` drops from 425 lines to 130. Both the advertised schema and the runtime validation now derive from one declaration, and [tests/test_schemas.py](tests/test_schemas.py) asserts set-equality in both directions between each model's fields and its function's parameters — so this class of drift is now a test failure rather than a silent contract break.

Two consequences worth noting:

- **Validation moved earlier and got stricter.** `extra="forbid"` means a mistyped argument name is now reported as `hous_system: Extra inputs are not permitted` instead of being silently ignored, and coordinate ranges, enums and the 366-day transit ceiling are enforced before any Swiss Ephemeris work begins. The `except TypeError` arm of the dispatcher became unreachable and was removed.
- **The SDK's own validation is disabled** (`@server.call_tool(validate_input=False)`). It validates against the same schema a second time and reports failures as prose, which broke the structured-JSON error contract that every other failure path honours. Since the models are the source of that schema, nothing is lost by validating once, in the layer that can emit the project's own error format.

