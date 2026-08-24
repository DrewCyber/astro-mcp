# Astrologer MCP Bug Report Log

<!-- NEW ENTRIES GO DIRECTLY BELOW THIS LINE, NEWEST FIRST. -->

No open issues.

<!-- END OF ENTRIES -->

## How this file works

Log for bugs, uncertainties, and API mismatches found while using the astro MCP
tools.

- The agent adds new entries at the top, immediately under the marker above, and
  never edits or deletes existing ones.
- Maintainers triage entries and delete them once the fix has landed with a
  regression test, so this file holds only open issues.
- Use the entry format given in `astrologer.agent.md`.
- A `logic-error` entry is as valuable as a bug: the 2026-07-27 retraction below
  was self-filed, correct, and produced a real server improvement.

Last cleared 2026-08-24.

Fixed and removed so far: Moon aspects missing from short windows, `output_tz`
ignored, an overlong Ma-Sa separation date, an unknown timezone surfacing as
INTERNAL_ERROR, a waxing/waning misreading, `SN` rejected as a planet code by
`find_aspect_exact_dates`, an `events_note` that blamed the 14-day threshold for
an omission the caller had requested, transiting planets housed against the
transit-moment chart instead of the natal cusps, and a lunation that had to be
labelled with the queried day's Moon sign. The progressed-house convention gap
(2026-08-11) is documented in `astrologer.agent.md`: progressions carry
`angles_method: "quotidian"` in their payload, and the prompt now states that
prog houses are progressed-chart houses while natal/transit house fields are
natal houses.

### The Full Moon thread, closed

Filed twice as a bug, then correctly retracted by the agent as a logic-error.
No ephemeris defect existed; two different events were being compared:

```text
2026-07-29T14:35Z  Moon opposite the CURRENT Sun (125.9 deg)  <- the Full Moon
2026-07-30T11:5xZ  Moon opposite the NATAL Sun   (137.4 deg)  <- the aspect_event
```

The natal and transiting Sun sit 11.4 degrees apart, which the Moon covers in
about 21 hours. `aspect_events` reports transits to the NATAL chart, so its
`Su` is never the Sun in the sky.

Two payload changes came out of it, because prose alone did not stop the
confusion:

- `calculate_transits` returns `moon.next_new` and `moon.next_full`, so a
  lunation is never inferred from a natal contact.
- Each carries its own `dt`, `sign`, `deg` and `sun_sign`. The retraction noted
  that the Full Moon had been reported in Capricorn, the Moon's sign on the
  queried day, when it perfects in Aquarius two days later. The outer `moon`
  fields describe the queried moment only; the lunation now describes itself.

Server-side fixes are pinned by `tests/test_bugreports.py` and
`tests/test_south_node.py`; the Moon-phase reasoning rule now lives in
`astrologer.agent.md` under "Derived Quantities (Compute, Never Estimate)".
