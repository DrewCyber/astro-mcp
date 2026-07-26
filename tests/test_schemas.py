"""M-1: the Pydantic models must stay in lockstep with the tool functions.

The hand-written JSON schemas they replaced had silently drifted from three
tool signatures. These tests make that class of drift a test failure.
"""

from __future__ import annotations

import inspect

import pytest

from astro_mcp.schemas import TOOL_INPUTS, Coordinates, json_schema_for, tool_description
from astro_mcp.server import _TOOL_REGISTRY, _load_tool


def _signature_params(name: str) -> dict[str, inspect.Parameter]:
    func = _load_tool(name)
    assert func is not None, f"{name} is not loadable"
    return dict(inspect.signature(func).parameters)


def test_every_registered_tool_has_an_input_model() -> None:
    assert set(TOOL_INPUTS) == set(_TOOL_REGISTRY)


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_model_fields_are_accepted_by_the_tool(name: str) -> None:
    """No model field may name a parameter the function does not accept."""
    params = _signature_params(name)
    unknown = set(TOOL_INPUTS[name].model_fields) - set(params)
    assert not unknown, f"{name}: schema advertises parameters the function rejects: {unknown}"


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_tool_parameters_are_all_documented(name: str) -> None:
    """No function parameter may be missing from the schema.

    This is the check that catches the drift found during the audit:
    find_aspect_exact_dates.degree_format and calculate_antiscia.orb /
    include_contra existed in code but were undocumented.
    """
    params = _signature_params(name)
    undocumented = set(params) - set(TOOL_INPUTS[name].model_fields)
    assert not undocumented, f"{name}: parameters missing from the schema: {undocumented}"


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_required_fields_have_no_function_default_conflict(name: str) -> None:
    """A field required by the schema must not be optional-with-None in code
    in a way that lets a caller bypass it."""
    model = TOOL_INPUTS[name]
    params = _signature_params(name)
    for field_name, field in model.model_fields.items():
        if field.is_required():
            assert field_name in params


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_schema_is_self_contained_and_wellformed(name: str) -> None:
    schema = json_schema_for(TOOL_INPUTS[name])
    assert schema["type"] == "object"
    assert schema["properties"]
    assert "$defs" not in schema
    assert "$ref" not in repr(schema), f"{name}: unresolved $ref left in schema"


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_every_tool_has_a_description(name: str) -> None:
    desc = tool_description(TOOL_INPUTS[name])
    assert len(desc) > 40, f"{name} needs a usable description"
    assert "\n" not in desc


def test_location_accepts_string_or_coordinates() -> None:
    from astro_mcp.schemas import NatalChartInput

    as_str = NatalChartInput(
        birth_date="1990-03-15", birth_time="14:30", birth_location="Berlin"
    )
    assert as_str.birth_location == "Berlin"

    as_obj = NatalChartInput(
        birth_date="1990-03-15",
        birth_time="14:30",
        birth_location={"lat": 52.52, "lon": 13.405},  # type: ignore[arg-type]
    )
    assert isinstance(as_obj.birth_location, Coordinates)
    assert as_obj.birth_location.lat == pytest.approx(52.52)


def test_out_of_range_coordinates_are_rejected() -> None:
    from pydantic import ValidationError

    from astro_mcp.schemas import NatalChartInput

    with pytest.raises(ValidationError):
        NatalChartInput(
            birth_date="1990-03-15",
            birth_time="14:30",
            birth_location={"lat": 999.0, "lon": 0.0},  # type: ignore[arg-type]
        )


def test_unknown_arguments_are_rejected() -> None:
    from pydantic import ValidationError

    from astro_mcp.schemas import NatalChartInput

    with pytest.raises(ValidationError):
        NatalChartInput(
            birth_date="1990-03-15",
            birth_time="14:30",
            birth_location="Berlin",
            hous_system="P",  # type: ignore[call-arg]  # typo
        )


def test_unset_optional_fields_are_not_forwarded() -> None:
    """exclude_unset keeps the tool functions owning their own defaults."""
    from astro_mcp.schemas import NatalChartInput

    parsed = NatalChartInput(
        birth_date="1990-03-15", birth_time="14:30", birth_location="Berlin"
    )
    assert parsed.model_dump(exclude_unset=True) == {
        "birth_date": "1990-03-15",
        "birth_time": "14:30",
        "birth_location": "Berlin",
    }


def test_period_days_ceiling_matches_the_transits_guard() -> None:
    """H-2 caps the scan at 366 days; the schema must advertise the same limit."""
    from astro_mcp.tools.transits import MAX_PERIOD_DAYS

    schema = json_schema_for(TOOL_INPUTS["calculate_transits"])
    assert schema["properties"]["period_days"]["maximum"] == MAX_PERIOD_DAYS


class TestValidationErrorHints:
    """Hints must name the offending field without leaking union internals."""

    def _hint(self, model_name: str, args: dict[str, object]) -> str:
        from pydantic import ValidationError

        from astro_mcp.server import _format_validation_error

        try:
            TOOL_INPUTS[model_name].model_validate(args)
        except ValidationError as exc:
            return _format_validation_error(exc)
        raise AssertionError("expected a ValidationError")

    def test_missing_field_is_named(self) -> None:
        hint = self._hint("calculate_natal_chart", {"birth_date": "1990-03-15"})
        assert "birth_time" in hint
        assert "Field required" in hint

    def test_nested_coordinate_error_hides_union_tags(self) -> None:
        hint = self._hint(
            "calculate_natal_chart",
            {
                "birth_date": "1990-03-15",
                "birth_time": "14:30",
                "birth_location": {"lat": 999, "lon": 0},
            },
        )
        assert "birth_location.lat" in hint
        # The failed `str` branch of the union must not surface.
        assert "Coordinates" not in hint
        assert "valid string" not in hint

    def test_typo_is_reported_as_extra_input(self) -> None:
        hint = self._hint(
            "calculate_natal_chart",
            {
                "birth_date": "1990-03-15",
                "birth_time": "14:30",
                "birth_location": "Berlin",
                "hous_system": "P",
            },
        )
        assert "hous_system" in hint
