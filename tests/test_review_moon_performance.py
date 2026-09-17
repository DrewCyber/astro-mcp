"""R21: operation-local lunar reuse preserves raw results and refinement calls."""

from collections.abc import Callable
from unittest.mock import patch

import pytest

from astro_mcp.core import ephemeris_provider as ep
from astro_mcp.core import moon


@pytest.mark.parametrize(
    ("iso", "aspect_calls", "lunation_calls", "voc_calls", "refinement_calls"),
    [
        ("2026-01-09T00:00:00Z", (1200, 140), (550, 390), (1304, 244), 216),
        ("2026-07-07T15:30:00Z", (1140, 133), (470, 358), (1243, 236), 216),
        ("2026-11-30T06:00:00Z", (1080, 126), (532, 388), (1182, 228), 180),
    ],
)
@pytest.mark.parametrize("operation_name", ["aspects", "lunations", "voc"])
def test_lunar_reuse_preserves_results_and_reduces_calls(
    iso: str,
    aspect_calls: tuple[int, int],
    lunation_calls: tuple[int, int],
    voc_calls: tuple[int, int],
    refinement_calls: int,
    operation_name: str,
) -> None:
    """Compare with uncached execution, including unrounded perfection JDs.

    Baseline counts were measured before remediation. Disabling only the local
    cache reproduces that evaluation path without maintaining a second scanner.
    January covers an already-void Moon just before ingress; July/November are
    nonvoid. The two lunations also exercise the directed-arc discontinuities.
    """
    jd = ep.to_jd(iso)
    start = moon._sign_boundary_jd(jd, forward=False)
    end = moon._sign_boundary_jd(jd, forward=True)
    operations: dict[str, tuple[Callable[[], object], tuple[int, int], int]] = {
        "aspects": (lambda: moon._aspect_times(start, end), aspect_calls, refinement_calls),
        "lunations": (lambda: moon.next_lunations(jd), lunation_calls, 72),
        "voc": (lambda: moon.moon_void_of_course(jd), voc_calls, refinement_calls),
    }
    operation, (before, after), expected_refinements = operations[operation_name]
    calculate = ep.calc_planet

    with (
        patch.object(moon, "cache", lambda function: function),
        patch.object(moon, "calc_planet", wraps=calculate) as scan,
        patch.object(ep, "calc_planet", wraps=calculate) as refinement,
    ):
        expected = operation()
        assert scan.call_count == before
        assert refinement.call_count == expected_refinements
        expected_refinement_calls = refinement.call_args_list

    # Repeat the same operation: each call must have its own cache, not inherit
    # values from an earlier request (or a different ephemeris configuration).
    for _ in range(2):
        with (
            patch.object(moon, "calc_planet", wraps=calculate) as scan,
            patch.object(ep, "calc_planet", wraps=calculate) as refinement,
        ):
            actual = operation()
            assert actual == expected  # Exact floats/dicts, not rounded/approximate comparisons.
            assert scan.call_count == after
            assert refinement.call_args_list == expected_refinement_calls
            assert after < before
            if operation_name in ("aspects", "lunations"):
                # Each raw (JD, body) sample is calculated once per operation.
                assert len({call.args for call in scan.call_args_list}) == after

    print(
        f"{iso} {operation_name}: total calc_planet calls "
        f"{before + expected_refinements} -> {after + expected_refinements}; "
        "exact outputs and refinement trace unchanged"
    )
