"""Schema-defaults vs function-defaults lockstep (R-8).

``server.call_tool`` forwards ``model_dump(exclude_unset=True)``, so a field
omitted by the client takes the FUNCTION's default at runtime, while
``json_schema_for`` advertises the MODEL's default to clients. If the two
drift apart, clients see defaults that never take effect.
"""

import inspect

import pytest

from astro_mcp.schemas import TOOL_INPUTS
from astro_mcp.tools.antiscia import calculate_antiscia
from astro_mcp.tools.arabic_parts import calculate_arabic_parts
from astro_mcp.tools.ephemeris import find_aspect_exact_dates, get_ephemeris
from astro_mcp.tools.natal import calculate_natal_chart
from astro_mcp.tools.planetary_hours import get_planetary_hours
from astro_mcp.tools.profections import calculate_profections
from astro_mcp.tools.progressions import calculate_secondary_progressions
from astro_mcp.tools.rectification import calculate_rectification_hints
from astro_mcp.tools.returns import calculate_lunar_return, calculate_solar_return
from astro_mcp.tools.synastry import calculate_composite_chart, calculate_synastry
from astro_mcp.tools.transits import calculate_transits

TOOL_FUNCTIONS = {
    "calculate_natal_chart": calculate_natal_chart,
    "calculate_transits": calculate_transits,
    "calculate_secondary_progressions": calculate_secondary_progressions,
    "calculate_solar_return": calculate_solar_return,
    "calculate_lunar_return": calculate_lunar_return,
    "calculate_rectification_hints": calculate_rectification_hints,
    "calculate_synastry": calculate_synastry,
    "calculate_composite_chart": calculate_composite_chart,
    "calculate_profections": calculate_profections,
    "get_planetary_hours": get_planetary_hours,
    "calculate_arabic_parts": calculate_arabic_parts,
    "get_ephemeris": get_ephemeris,
    "find_aspect_exact_dates": find_aspect_exact_dates,
    "calculate_antiscia": calculate_antiscia,
}


def test_every_tool_has_a_function():
    assert set(TOOL_FUNCTIONS) == set(TOOL_INPUTS)


@pytest.mark.parametrize("tool_name", sorted(TOOL_INPUTS))
def test_optional_field_defaults_match_function_defaults(tool_name):
    model = TOOL_INPUTS[tool_name]
    func = TOOL_FUNCTIONS[tool_name]
    params = inspect.signature(func).parameters

    for field_name, field in model.model_fields.items():
        if field.is_required() or field_name not in params:
            continue
        param = params[field_name]
        if param.default is inspect.Parameter.empty:
            # Function relies on its own None-handling while the schema
            # advertises a concrete default — exactly the drift R-8 warns of.
            pytest.fail(
                f"{tool_name}.{field_name}: schema default "
                f"{field.get_default()!r} but function parameter is required"
            )
        schema_default = field.get_default(call_default_factory=True)
        assert param.default == schema_default, (
            f"{tool_name}.{field_name}: schema advertises default "
            f"{schema_default!r} but function uses {param.default!r}"
        )
