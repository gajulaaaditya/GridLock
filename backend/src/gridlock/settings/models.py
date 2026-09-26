"""Pydantic models for the configuration surface used by every pipeline stage."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PathsConfig(BaseModel):
    raw_dir: str
    cache_dir: str
    normalized_dir: str
    output_dir: str
    review_dir: str


class ThresholdsConfig(BaseModel):
    near: float = Field(gt=0)
    local: float = Field(gt=0)
    maximum: float = Field(gt=0)

    @model_validator(mode="after")
    def tiers_are_ordered(self) -> "ThresholdsConfig":
        if not self.near < self.local < self.maximum:
            raise ValueError("thresholds_km must satisfy near < local < maximum")
        return self


class TimelineGapConfig(BaseModel):
    near: int = Field(ge=0)
    moderate: int = Field(ge=0)
    distant: int = Field(ge=0)

    @model_validator(mode="after")
    def buckets_are_ordered(self) -> "TimelineGapConfig":
        if not self.near < self.moderate < self.distant:
            raise ValueError("timeline_gap_days must satisfy near < moderate < distant")
        return self


class DisplayConfig(BaseModel):
    distance_unit: str
    timezone: str

    @model_validator(mode="after")
    def has_supported_distance_unit(self) -> "DisplayConfig":
        if self.distance_unit not in {"km", "mi"}:
            raise ValueError("display.distance_unit must be km or mi")
        return self


class GeometryConfig(BaseModel):
    projected_crs: str
    bbox: tuple[float, float, float, float]
    overpass_timeout_seconds: int = Field(gt=0)
    overpass_max_retries: int = Field(ge=0)

    @model_validator(mode="after")
    def bbox_is_west_south_east_north(self) -> "GeometryConfig":
        west, south, east, north = self.bbox
        if west >= east or south >= north:
            raise ValueError("geometry.bbox must be ordered west, south, east, north")
        return self


class AiConfig(BaseModel):
    enabled: bool = False


class GridlockConfig(BaseModel):
    paths: PathsConfig
    utilities: tuple[str, ...]
    utility_files: tuple[str, ...]
    thresholds_km: ThresholdsConfig
    timeline_gap_days: TimelineGapConfig
    display: DisplayConfig
    geometry: GeometryConfig
    ai: AiConfig

    @model_validator(mode="after")
    def utility_file_count_matches_scope(self) -> "GridlockConfig":
        if len(set(self.utilities)) != len(self.utilities):
            raise ValueError("utilities must not contain duplicates")
        if not self.utilities:
            raise ValueError("at least one utility must be configured")
        if len(self.utility_files) != len(self.utilities):
            raise ValueError("utility_files must provide exactly one file per utility")
        return self


class SourceConfig(BaseModel):
    id: str
    parser: str
    path: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    summary_page_start: int | None = Field(default=None, ge=1)
    summary_page_end: int | None = Field(default=None, ge=1)
    detail_page_start: int | None = Field(default=None, ge=1)
    detail_page_end: int | None = Field(default=None, ge=1)


class UtilityConfig(BaseModel):
    id: str
    display_name: str
    color: str
    states: tuple[str, ...]
    operator_aliases: tuple[str, ...] = ()
    included_sponsors: tuple[str, ...] = ()
    sources: tuple[SourceConfig, ...]
