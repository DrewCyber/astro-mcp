"""Tests for core/formatters.py."""

from astro_mcp.core.formatters import decimal_to_dms, to_compact_json


def test_decimal_to_dms_basic():
    assert decimal_to_dms(24.7534) == "24°45'12\""


def test_decimal_to_dms_zero():
    result = decimal_to_dms(0.0)
    assert result == "00°00'00\""


def test_compact_json_no_whitespace():
    data = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
    output = to_compact_json(data)
    assert " " not in output
    assert "\n" not in output


def test_compact_json_unicode_preserved():
    data = {"name": "Москва"}
    output = to_compact_json(data)
    assert "Москва" in output
