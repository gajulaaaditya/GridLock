from __future__ import annotations

import json
from pathlib import Path

from gridlock.ingestion.documents import ingest_plans
from gridlock.settings.loader import load_settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_public_plan_ingestion_matches_known_source_records() -> None:
    bundle = load_settings(REPOSITORY_ROOT / "config" / "gridlock.yaml")
    report = ingest_plans(bundle, REPOSITORY_ROOT)
    projects = json.loads(report.output_path.read_text(encoding="utf-8"))
    by_id = {project["id"]: project for project in projects}

    assert report.projects_by_utility == {"DESC": 44, "GPC": 138}
    assert len(by_id) == 182
    assert by_id["DESC-06367-D-G"]["projectName"] == "Jasper – Okatie 230 kV #2: Construct"
    assert by_id["DESC-06367-D-G"]["voltageKv"] == [230]
    assert by_id["DESC-06367-D-G"]["plannedInServiceDate"] == "2025-12-31"
    assert by_id["DESC-06367-D-G"]["estimatedCostUsd"] == 23787423
    assert by_id["DESC-06367-D-G"]["source"]["page"] == 23
    assert by_id["GPC-20277"]["sponsor"] == "SAV"
    assert by_id["GPC-20277"]["constructionWindow"] == {
        "startDate": "2024-01-01",
        "endDate": "2026-06-01",
    }
    assert by_id["GPC-20277"]["source"]["page"] == 227
    assert by_id["GPC-20793"]["constructionWindow"]["endDate"] == "2033-06-01"
