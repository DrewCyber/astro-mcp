"""Compatibility weights must stay nonnegative under custom orbs."""

import pytest
from pydantic import ValidationError

from astro_mcp.core.models import Aspect
from astro_mcp.schemas import SynastryInput
from astro_mcp.tools.synastry import calculate_synastry


def test_wide_custom_orbs_never_subtract_from_scores(monkeypatch):
    monkeypatch.setattr("astro_mcp.tools.synastry.find_aspects", lambda *args, **kwargs: [
        Aspect("Su", "Mo", "Cnj", 10.0, False),
        Aspect("Me", "Ma", "Opp", 9.0, False),
    ])
    result = calculate_synastry(
        person1_date="1990-01-01", person1_time="12:00",
        person1_location={"lat": 35.7, "lon": 139.7, "tz": "UTC"},
        person2_date="1992-03-03", person2_time="06:00",
        person2_location={"lat": 52.5, "lon": 13.4, "tz": "UTC"},
        orbs={"Cnj": 2, "Opp": 2, "Tri": 2, "Squ": 2, "Sex": 2},
    )
    indicators = result["compatibility_indicators"]
    assert indicators["harmony_score"] >= 0
    assert indicators["tension_score"] >= 0


def test_synastry_input_rejects_out_of_range_orbs():
    with pytest.raises(ValidationError):
        SynastryInput.model_validate({
            "person1_date": "1990-01-01", "person1_time": "12:00",
            "person1_location": "test", "person2_date": "1992-03-03",
            "person2_time": "06:00", "person2_location": "test",
            "orbs": {"Cnj": 20},
        })
