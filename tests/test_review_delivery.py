"""Release gating and strict orb input contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from astro_mcp.schemas import TransitsInput


@pytest.mark.parametrize("orbs", [{"typo": 2}, {"Cnj": -1}, {"Opp": float("nan")},
                                 {"Tri": float("inf")}, {"Sex": 16}])
def test_invalid_orb_overrides_are_rejected(orbs):
    with pytest.raises(ValidationError):
        TransitsInput.model_validate({"birth_date": "1990-01-01", "birth_time": "12:00",
                                     "birth_location": "test", "transit_date": "2026-01-01",
                                     "orbs": orbs})


def test_release_requires_tests_and_frozen_installs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text()
    release = workflow.split("  docker-build:")[1]
    assert "needs: test" in release
    assert "uv sync --frozen --extra dev" in workflow
    assert "uv run --frozen --extra dev pytest" in workflow
    docker = (root / "Dockerfile").read_text()
    assert "uv.lock" in docker
    assert "uv sync --frozen" in docker
