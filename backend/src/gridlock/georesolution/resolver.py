"""Resolve only high-confidence public OSM matches; preserve every unresolved record."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz.fuzz import ratio

from gridlock.models.domain import Evidence, EvidenceLevel, GeometryMethod, GeometryResolution, Project
from gridlock.settings.loader import ConfigBundle


def _name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"\b(substation|sub|primary|station|usa)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


@dataclass(frozen=True)
class Candidate:
    feature_id: str
    name: str
    score: int
    geometry: dict[str, Any]


def _candidates(endpoint_name: str, features: list[dict[str, Any]], operator_aliases: tuple[str, ...] = ()) -> list[Candidate]:
    target = _name(endpoint_name)
    candidates: list[Candidate] = []
    for feature in features:
        properties = feature.get("properties", {})
        feature_name = properties.get("name")
        if properties.get("power") != "substation" or not isinstance(feature_name, str):
            continue
        operator = properties.get("operator")
        if operator and operator_aliases and _name(str(operator)) not in {_name(alias) for alias in operator_aliases}:
            continue
        score = ratio(target, _name(feature_name))
        if score >= 88:
            candidates.append(Candidate(feature["id"], feature_name, score, feature["geometry"]))
    return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.feature_id))


def _point_for_feature(feature: Candidate) -> list[float] | None:
    geometry = feature.geometry
    if geometry.get("type") == "Point":
        return geometry["coordinates"]
    if geometry.get("type") == "Polygon":
        ring = geometry["coordinates"][0]
        return [sum(point[0] for point in ring) / len(ring), sum(point[1] for point in ring) / len(ring)]
    return None


def _resolve_project(project: Project, features: list[dict[str, Any]], operator_aliases: tuple[str, ...]) -> Project:
    resolved = []
    warnings: list[str] = []
    for endpoint in project.endpoints:
        candidates = _candidates(endpoint.name, features, operator_aliases)
        if not candidates:
            warnings.append(f"No public OSM substation candidate for endpoint {endpoint.name}")
            continue
        best = candidates[0]
        if len(candidates) > 1 and candidates[1].score == best.score:
            warnings.append(f"Ambiguous OSM candidates for endpoint {endpoint.name}")
            continue
        point = _point_for_feature(best)
        if point is None:
            warnings.append(f"Unsupported public OSM geometry for endpoint {endpoint.name}")
            continue
        resolved.append((best, point))

    source_score = 20
    geometry_score = 30 if len(resolved) >= 2 else 15 if len(resolved) == 1 else 0
    timeline_score = 15 if project.construction_window else 10 if project.planned_in_service_date else 0
    score = source_score + geometry_score + timeline_score
    level = EvidenceLevel.HIGH if score >= 80 else EvidenceLevel.MEDIUM if score >= 50 else EvidenceLevel.LOW
    evidence = Evidence(level=level, score=score, reasons=["Official public filing with project identifier"], warnings=warnings)

    if len(resolved) >= 2:
        project.geometry = {"type": "LineString", "coordinates": [point for _, point in resolved]}
        project.geometry_resolution = GeometryResolution(
            method=GeometryMethod.VERIFIED_ENDPOINTS_STRAIGHT_LINE,
            is_approximation=True,
            feature_ids=[candidate.feature_id for candidate, _ in resolved],
            warnings=warnings,
        )
    elif len(resolved) == 1:
        candidate, point = resolved[0]
        project.geometry = {"type": "Point", "coordinates": point}
        project.geometry_resolution = GeometryResolution(
            method=GeometryMethod.VERIFIED_SINGLE_ENDPOINT,
            is_approximation=True,
            feature_ids=[candidate.feature_id],
            warnings=warnings,
        )
    else:
        project.geometry_resolution = GeometryResolution(
            method=GeometryMethod.UNRESOLVED,
            is_approximation=False,
            warnings=warnings,
        )
    project.evidence = evidence
    return project


@dataclass(frozen=True)
class ResolutionReport:
    output_path: Path
    review_path: Path
    geometry_methods: dict[str, int]
    evidence_levels: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "output_path": str(self.output_path),
            "review_path": str(self.review_path),
            "geometry_methods": self.geometry_methods,
            "evidence_levels": self.evidence_levels,
        }


def resolve_projects(bundle: ConfigBundle, repository_root: Path) -> ResolutionReport:
    normalized_path = repository_root / bundle.root.paths.normalized_dir / "projects.json"
    cache_path = repository_root / bundle.root.paths.cache_dir / "osm_power.geojson"
    projects = [Project.model_validate(item) for item in json.loads(normalized_path.read_text(encoding="utf-8"))]
    features = json.loads(cache_path.read_text(encoding="utf-8"))["features"]
    aliases = {utility.id.casefold(): utility.operator_aliases for utility in bundle.utilities}
    resolved_projects = [_resolve_project(project, features, aliases[project.utility.value.casefold()]) for project in projects]
    output_path = repository_root / bundle.root.paths.normalized_dir / "projects_resolved.json"
    output_path.write_text(json.dumps([item.model_dump(mode="json", by_alias=True) for item in resolved_projects], indent=2) + "\n", encoding="utf-8")
    review_path = repository_root / bundle.root.paths.review_dir / "unresolved.csv"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["project_id", "project_name", "warnings"])
        for project in resolved_projects:
            if project.geometry_resolution and project.geometry_resolution.method == GeometryMethod.UNRESOLVED:
                writer.writerow([project.id, project.project_name, " | ".join(project.geometry_resolution.warnings)])
    return ResolutionReport(
        output_path=output_path,
        review_path=review_path,
        geometry_methods=dict(Counter(item.geometry_resolution.method.value for item in resolved_projects if item.geometry_resolution)),
        evidence_levels=dict(Counter(item.evidence.level.value for item in resolved_projects if item.evidence)),
    )
