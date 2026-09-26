"""Pure normalizers for project records extracted from public filings."""

from __future__ import annotations

import re
from datetime import datetime

from gridlock.models.domain import Endpoint, EndpointRole, ProjectType


def parse_filed_date(value: str | None):
    if not value:
        return None
    for format_string in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), format_string).date()
        except ValueError:
            pass
    return None


def normalize_desc(raw_id: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", raw_id.upper())
    return "DESC-" + "-".join(tokens)


def normalize_gpc(raw_id: str) -> str:
    return "GPC-" + "".join(re.findall(r"\d+", raw_id))


def extract_voltage_kv(text: str) -> list[int]:
    return sorted({int(value) for value in re.findall(r"\b(\d{2,3})\s*kV\b", text, re.I)})


def infer_project_type(name: str, description: str | None) -> ProjectType:
    text = f"{name} {description or ''}".upper()
    if "REACTOR" in text:
        return ProjectType.REACTOR
    if "SUBSTATION" in text or "PRIMARY" in text:
        return ProjectType.SUBSTATION
    if any(token in text for token in ("LINE", "REBUILD", "RECONDUCTOR", "CONDUCTOR")):
        return ProjectType.TRANSMISSION_LINE
    return ProjectType.OTHER


def extract_endpoints(name: str) -> list[Endpoint]:
    """Extract only explicit, separator-delimited endpoints; ambiguous titles stay empty."""
    clean_name = re.sub(r"^(?:[A-Z]{2,5}:\s*)", "", name.strip())
    clean_name = re.sub(r"\s+\d{2,3}\s*K[Vv].*$", "", clean_name).strip()
    parts = re.split(r"\s+[–-]\s+", clean_name, maxsplit=1)
    if len(parts) != 2 or not all(parts):
        return []
    right = re.sub(r"\s+(?:LINE|REACTORS?|REBUILD|PROJECT).*$", "", parts[1], flags=re.I).strip()
    if not right:
        return []
    return [Endpoint(name=parts[0].strip(), role=EndpointRole.FROM), Endpoint(name=right, role=EndpointRole.TO)]
