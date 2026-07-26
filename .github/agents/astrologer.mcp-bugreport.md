# Astrologer MCP Bug Report Log

Log for bugs, uncertainties, and API mismatches found while using the astro MCP
tools.

- The agent appends new entries at the end and never edits existing ones.
- Maintainers triage entries and delete them once the fix has landed with a
  regression test, so this file holds only open issues.

No open issues.

Last cleared 2026-07-26. The five previously logged issues (Moon aspects missing
from short windows, `output_tz` ignored, an overlong Ma-Sa separation date, an
unknown timezone surfacing as INTERNAL_ERROR, and a waxing/waning misreading)
are all fixed. Server-side fixes are pinned by `tests/test_bugreports.py`; the
Moon-phase reasoning rule now lives in `astrologer.agent.md` under "Derived
Quantities (Compute, Never Estimate)".

New entries go below this line, newest last, in the format given in
`astrologer.agent.md`.
