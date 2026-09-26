from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gridlock.contract import export_contract, validate_payload


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "data" / "fixtures" / "demo_payload.json"


def test_fixture_validates_against_contract() -> None:
    payload = validate_payload(FIXTURE_PATH)

    assert payload.metadata.fixture is True
    assert payload.relationships[0].distance_km == 4.7
    assert payload.relationships[0].timeline.isd_within_filed_span is True


def test_contract_export_is_deterministic(tmp_path: Path) -> None:
    first_schema, first_types = export_contract(tmp_path)
    first_contents = (first_schema.read_bytes(), first_types.read_bytes())
    second_schema, second_types = export_contract(tmp_path)

    assert first_contents == (second_schema.read_bytes(), second_types.read_bytes())
    assert '"distanceKm"' in first_schema.read_text(encoding="utf-8")
    assert "distanceKm: number;" in first_types.read_text(encoding="utf-8")


def test_unknown_spatial_tier_is_rejected(tmp_path: Path) -> None:
    invalid_fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    invalid_fixture["relationships"][0]["spatialTier"] = "FOO"
    invalid_path = tmp_path / "invalid_payload.json"
    invalid_path.write_text(json.dumps(invalid_fixture), encoding="utf-8")

    with pytest.raises(ValidationError):
        validate_payload(invalid_path)

