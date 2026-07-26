## 2026-07-17 12:00 UTC
Tool: mcp_astro-mcp_find_aspect_exact_dates
Type: bug
Input summary: {planet1:"Mo", planet2:"Sa|Pl|Ve|SN", aspect:"Squ|Sex|Cnj", date_from:"2026-07-17/19", date_to:"2026-07-17/19", mode:"transit-to-natal", orb:1}
Observed: Returned empty occurrences for multiple Moon transit-to-natal aspects inside a 1-3 day window, while mcp_astro-mcp_calculate_transits for the same dates returned matching Moon aspects with exact-date tags.
Expected: find_aspect_exact_dates should return occurrences consistent with calculate_transits for identical date ranges/aspects when exact hits exist.
Impact: Reduces confidence in intraday timing for fast Moon aspects and requires fallback to broader transit output.
Workaround used: Used calculate_transits (daily snapshots) + get_ephemeris for practical timing windows instead of relying on find_aspect_exact_dates for Moon.## 2026-07-05 00:00 UTC
Tool: mcp_astro-mcp_get_ephemeris
Type: bug
Input summary: {planet:["Su","Mo","Me","Ve","Ma","Ju","Sa","Ur","Ne","Pl","NN"], date_from:"2026-07-06", date_to:"2026-07-12", step:"1d", output_tz:"Europe/Tbilisi"}
Observed: Response returned timezone as "UTC" and date rows without requested local timezone conversion.
Expected: Response timezone and datetime rows should reflect requested output_tz "Europe/Tbilisi".
Impact: Intraday timing and local-day interpretation can shift, especially for Moon phase timing and exact aspect windows.
Workaround used: Interpreted weekly windows by date range and relied on exact-aspect tool for phase peaks.
## 2026-06-20 00:00 UTC
Tool: mcp_astro-mcp_find_aspect_exact_dates
Type: uncertainty
Input summary: {planet1:"Ma", planet2:"Sa", aspect:"SSq", date_from:"2026-06-22", date_to:"2026-06-28", mode:"transit-to-transit", orb:1}
Observed: Returned occurrence with exact_date 2026-06-27 but separation_date 2026-07-27.
Expected: Separation date should likely be within a few days for Ma-Sa semisquare at 1° orb, not ~30 days later.
Impact: Could overstate the active duration window for this aspect in weekly forecasts.
Workaround used: Treated the aspect as peak around 26-28 Jun and interpreted duration conservatively (about 3-7 days) despite tool separation_date.

## 2026-06-19 00:00 UTC
Tool: mcp_astro-mcp_calculate_transits
Type: schema-mismatch
Input summary: {transit_location: {lat: 41.61689, lon: 41.607043, tz: "Europe/Tbilisi"}, transit_date: "2026-06-20"}
Observed: Tool returned INTERNAL_ERROR: "No time zone found with key Europe/Tbilisi".
Expected: Accept common IANA timezone alias or return a validation error with supported values.
Impact: First transit calculation failed; forecast was delayed and required retry.
Workaround used: Re-ran with tz "Asia/Tbilisi", calculation succeeded.# Astrologer MCP Bug Report Log

This file is an append-only log for bugs, uncertainties, and API mismatches found while using astro MCP tools.

## 2026-07-07 15:30 UTC
Tool: Manual Moon phase calculation
Type: logic-error
Input summary: transit_Sun 105.12° (Cancer), transit_Moon 7.62° (Aries)
Observed: Agent concluded Moon was waxing (growing phase)
Expected: phase = (7.62 - 105.12) mod 360 = 262.5° → waning (last quarter)
Impact: Misinterpreted energy (said "beginnings" vs. "completion")
Workaround used: Manual formula applied; AGENT_RULES.md created to enforce explicit calculations

## Entry Template## YYYY-MM-DD HH:MM UTC
Tool: <tool_name>
Type: bug | uncertainty | docs-gap | schema-mismatch
Input summary: <short JSON-like summary>
Observed: <what happened>
Expected: <what should happen>
Impact: <how this affects analysis>
Workaround used: <if any>
