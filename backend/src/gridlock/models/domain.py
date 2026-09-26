"""Pydantic domain contract for GridLock's deterministic pipeline."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _camel_case(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ContractModel(BaseModel):
    """Base model that keeps Python snake_case and API camelCase aligned."""

    model_config = ConfigDict(alias_generator=_camel_case, populate_by_name=True)


class UtilityId(StrEnum):
    DESC = "DESC"
    GPC = "GPC"


class ProjectType(StrEnum):
    TRANSMISSION_LINE = "transmission_line"
    SUBSTATION = "substation"
    REACTOR = "reactor"
    OTHER = "other"


class EndpointRole(StrEnum):
    FROM = "from"
    TO = "to"
    SINGLE = "single"
    UNKNOWN = "unknown"


class GeometryMethod(StrEnum):
    VERIFIED_FULL_LINE = "verified_full_line"
    VERIFIED_ENDPOINTS_STRAIGHT_LINE = "verified_endpoints_straight_line"
    VERIFIED_ENDPOINT_ROUTE = "verified_endpoint_route"
    VERIFIED_SINGLE_ENDPOINT = "verified_single_endpoint"
    APPROXIMATE_AREA_CENTROID = "approximate_area_centroid"
    HUMAN_VERIFIED_OVERRIDE = "human_verified_override"
    UNRESOLVED = "unresolved"


class EvidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNRESOLVED = "UNRESOLVED"


class SpatialTier(StrEnum):
    CROSSING = "CROSSING"
    SITE_LOGISTICS = "SITE_LOGISTICS"
    REGIONAL_COORDINATION = "REGIONAL_COORDINATION"


class TimelineType(StrEnum):
    IN_SERVICE_GAP = "IN_SERVICE_GAP"
    WINDOW_OVERLAP = "WINDOW_OVERLAP"
    UNRESOLVED = "UNRESOLVED"


class TimelineRelevance(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    MEANINGFUL = "MEANINGFUL"
    WATCH = "WATCH"
    UNKNOWN = "UNKNOWN"


class Priority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Endpoint(ContractModel):
    name: str = Field(min_length=1)
    role: EndpointRole = EndpointRole.UNKNOWN


class ConstructionWindow(ContractModel):
    start_date: date
    end_date: date


class SourceRef(ContractModel):
    document: str = Field(min_length=1)
    project_id_raw: str = Field(min_length=1)
    page: int = Field(ge=1)
    raw_text: str | None = None


class Point(ContractModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeometryResolution(ContractModel):
    method: GeometryMethod
    is_approximation: bool
    feature_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Evidence(ContractModel):
    level: EvidenceLevel
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Project(ContractModel):
    id: str = Field(min_length=1)
    utility: UtilityId
    project_name: str = Field(min_length=1)
    project_type: ProjectType
    description: str | None = None
    voltage_kv: list[int] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    status: str | None = None
    planned_in_service_date: date | None = None
    construction_window: ConstructionWindow | None = None
    estimated_cost_usd: int | None = Field(default=None, ge=0)
    source: SourceRef
    geometry: dict[str, Any] | None = None
    geometry_resolution: GeometryResolution | None = None
    evidence: Evidence | None = None


class Timeline(ContractModel):
    type: TimelineType
    gap_days: int | None = Field(default=None, ge=0)
    relevance: TimelineRelevance
    isd_within_filed_span: bool = False


class Relationship(ContractModel):
    id: str = Field(min_length=1)
    project_a: str = Field(min_length=1)
    project_b: str = Field(min_length=1)
    distance_km: float = Field(ge=0)
    closest_points: tuple[Point, Point]
    spatial_tier: SpatialTier
    timeline: Timeline
    opportunity_priority: Priority
    coordination_playbook: list[str] = Field(default_factory=list)
    evidence: Evidence


class Bounds(ContractModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)


class Zone(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    project_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    utilities: list[UtilityId] = Field(default_factory=list)
    closest_distance_km: float = Field(ge=0)
    opportunity_priority: Priority
    evidence_level: EvidenceLevel
    coordination_themes: list[str] = Field(default_factory=list)
    bounds: Bounds


class Metadata(ContractModel):
    schema_version: str = "1.0"
    fixture: bool = False
    distance_unit: str = "km"
    thresholds_km: dict[str, float]
    utility_colors: dict[str, str]


class Payload(ContractModel):
    metadata: Metadata
    projects: list[Project] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
