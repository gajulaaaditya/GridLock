"""Validate JSON payloads against the canonical Pydantic contract."""

from __future__ import annotations

from pathlib import Path

from gridlock.models import Payload


def validate_payload(path: Path) -> Payload:
    return Payload.model_validate_json(path.read_text(encoding="utf-8"))

