"""Structured errors with stable, machine-readable codes.

Every failure that is the caller's fault (bad input, unresolvable city, a date
outside the ephemeris range) must be raised as :class:`AstroError` carrying an
explicit ``code`` from :data:`ERROR_CODES`.  The MCP dispatcher is the only
place that turns these into a wire payload, so error formatting lives in
exactly one place.

Anything that is *not* an ``AstroError`` is by definition an unexpected
internal fault: it is logged server-side and reported to the client as a
generic ``INTERNAL_ERROR`` without the original exception text.
"""

from __future__ import annotations

from typing import Any, Final

# Closed set of codes the server may emit.  Kept explicit so clients (and the
# LLM consuming them) can branch on a known vocabulary instead of parsing prose.
ERROR_CODES: Final[frozenset[str]] = frozenset({
    # Input / validation
    "INPUT_ERROR",
    "UNKNOWN_TOOL",
    "UNKNOWN_PLANET",
    "UNKNOWN_ASPECT",
    "INVALID_COORDINATES",
    "INVALID_DATE",
    "INVALID_TIME",
    "RANGE_TOO_LONG",
    "RANGE_TOO_WIDE",
    "TOO_FEW_EVENTS",
    "WORKLOAD_TOO_LARGE",
    # Resolution
    "GEOCODE_FAILED",
    "TIMEZONE_UNKNOWN",
    # Ephemeris / astronomy
    "EPHEMERIS_UNAVAILABLE",
    "EPHEMERIS_OUT_OF_RANGE",
    "HOUSE_CALC_FAILED",
    "NO_RISE_SET",
    "RETURN_NOT_FOUND",
    # Catch-all
    "INTERNAL_ERROR",
})


class AstroError(Exception):
    """An error that is safe and useful to report to the MCP client."""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"Unknown error code: {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": True,
            "code": self.code,
            "message": self.message,
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload
