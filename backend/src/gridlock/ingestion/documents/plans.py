"""Config-driven parsers for the DESC and GPC public planning documents."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from gridlock.models.domain import ConstructionWindow, Project, SourceRef, UtilityId
from gridlock.normalization import (
    extract_endpoints,
    extract_voltage_kv,
    infer_project_type,
    normalize_desc,
    normalize_gpc,
    parse_filed_date,
)
from gridlock.settings.loader import ConfigBundle
from gridlock.settings.models import SourceConfig, UtilityConfig


class IngestionError(ValueError):
    """Raised when a configured source does not satisfy its known public layout."""


@dataclass(frozen=True)
class IngestionReport:
    projects_by_utility: dict[str, int]
    null_counts: dict[str, int]
    output_path: Path

    def as_dict(self) -> dict[str, object]:
        return {
            "projects_by_utility": self.projects_by_utility,
            "total_projects": sum(self.projects_by_utility.values()),
            "null_counts": self.null_counts,
            "output_path": str(self.output_path),
        }


def _field(text: str, label: str, next_label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*\n?(.*?)(?=\n\s*{re.escape(next_label)}\b)", text, re.S | re.I)
    return " ".join(match.group(1).split()) if match else None


def _title_before(text: str, marker: str) -> str | None:
    before_marker = text.split(marker, maxsplit=1)[0]
    try:
        after_budget = before_marker.split("5 Year Budget", maxsplit=1)[1]
    except IndexError:
        return None
    lines = [line.strip() for line in after_budget.splitlines() if line.strip()]
    return " ".join(lines) or None


def _parse_currency_from_desc(text: str) -> int | None:
    section = text.split("Estimated Project Cost", maxsplit=1)[-1]
    amounts = re.findall(r"\$([\d,]+)", section)
    return int(amounts[-1].replace(",", "")) if amounts else None


def parse_desc(source_path: Path, source: SourceConfig) -> list[Project]:
    reader = PdfReader(source_path)
    page_start = source.page_start or 1
    page_end = source.page_end or len(reader.pages)
    projects: list[Project] = []
    for page_number in range(page_start, page_end + 1):
        text = reader.pages[page_number - 1].extract_text() or ""
        raw_id = _field(text, "Project ID", "Project Description")
        title = _title_before(text, "Project ID")
        if not raw_id or not title:
            raise IngestionError(f"DESC page {page_number} is missing Project ID or title")
        description = _field(text, "Project Description", "Project Need")
        status = _field(text, "Project Status", "Planned In-Service Date")
        in_service = _field(text, "Planned In-Service Date", "Estimated Project Cost")
        projects.append(
            Project(
                id=normalize_desc(raw_id),
                utility=UtilityId.DESC,
                project_name=title,
                project_type=infer_project_type(title, description),
                description=description,
                voltage_kv=extract_voltage_kv(title) or extract_voltage_kv(description or ""),
                endpoints=extract_endpoints(title),
                status=status,
                planned_in_service_date=parse_filed_date(in_service),
                estimated_cost_usd=_parse_currency_from_desc(text),
                source=SourceRef(
                    document=source.path,
                    project_id_raw=raw_id,
                    page=page_number,
                    raw_text=text,
                ),
            )
        )
    return projects


_SUMMARY_ROW = re.compile(
    r"(?P<zone>\d{3})\s+(?P<year>20\d{2})\s+(?P<team>\d{4,6})\s+"
    r"(?P<name>.*?)\s+(?P<need>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<sponsor>[A-Z]{2,5})\s+REDACTED",
    re.S,
)
_TEAMS_NUMBER = re.compile(r"Teams\s*#\s*(?P<team>\d+)", re.I)
_DETAIL_DATES = re.compile(
    r"Need Date\s+(?P<need>\d{1,2}/\d{1,2}/\d{4})\s+Start Date\s+(?P<start>\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)


def _summary_rows(reader: PdfReader, source: SourceConfig) -> dict[str, dict[str, str]]:
    if source.summary_page_start is None or source.summary_page_end is None:
        raise IngestionError("GPC source requires summary page bounds")
    text = "\n".join(
        reader.pages[index - 1].extract_text() or ""
        for index in range(source.summary_page_start, source.summary_page_end + 1)
    )
    rows = {
        match.group("team"): {
            "name": " ".join(match.group("name").split()),
            "need": match.group("need"),
            "sponsor": match.group("sponsor"),
        }
        for match in _SUMMARY_ROW.finditer(text)
    }
    if not rows:
        raise IngestionError("GPC summary table did not yield any project rows")
    return rows


def _detail_title(text: str, team_match: re.Match[str]) -> str | None:
    lines = [line.strip() for line in text[: team_match.start()].splitlines() if line.strip()]
    ignored = ("CRITICAL ENERGY", "Recipient should", "contents shall", "policy, should", "2024 GA ITS")
    candidates = [line for line in lines if not line.startswith(ignored)]
    return candidates[-1] if candidates else None


def parse_gpc(source_path: Path, source: SourceConfig, utility: UtilityConfig) -> list[Project]:
    reader = PdfReader(source_path)
    summary = _summary_rows(reader, source)
    included_sponsors = set(utility.included_sponsors)
    page_start = source.detail_page_start or 1
    page_end = source.detail_page_end or len(reader.pages)
    details: dict[str, tuple[int, str]] = {}
    for page_number in range(page_start, page_end + 1):
        text = reader.pages[page_number - 1].extract_text() or ""
        match = _TEAMS_NUMBER.search(text)
        if match:
            details[match.group("team")] = (page_number, text)

    projects: list[Project] = []
    for team, row in sorted(summary.items(), key=lambda item: int(item[0])):
        if row["sponsor"] not in included_sponsors:
            continue
        detail = details.get(team)
        if detail is None:
            raise IngestionError(f"GPC summary project {team} has no detail page")
        page_number, text = detail
        team_match = _TEAMS_NUMBER.search(text)
        assert team_match is not None
        title = _detail_title(text, team_match) or row["name"]
        dates = _DETAIL_DATES.search(text)
        start_date = parse_filed_date(dates.group("start")) if dates else None
        need_date = parse_filed_date(dates.group("need")) if dates else parse_filed_date(row["need"])
        projects.append(
            Project(
                id=normalize_gpc(team),
                utility=UtilityId.GPC,
                project_name=title,
                project_type=infer_project_type(title, text),
                sponsor=row["sponsor"],
                voltage_kv=extract_voltage_kv(title) or extract_voltage_kv(text),
                endpoints=extract_endpoints(title),
                construction_window=(ConstructionWindow(start_date=start_date, end_date=need_date)
                                     if start_date and need_date else None),
                source=SourceRef(
                    document=source.path,
                    project_id_raw=team,
                    page=page_number,
                    raw_text=text,
                ),
            )
        )
    return projects


def ingest_plans(bundle: ConfigBundle, repository_root: Path) -> IngestionReport:
    """Parse configured planning sources and write normalized, provenance-rich JSON."""
    projects: list[Project] = []
    raw_dir = repository_root / bundle.root.paths.raw_dir
    utilities_by_id = {utility.id: utility for utility in bundle.utilities}
    for utility in bundle.utilities:
        for source in utility.sources:
            source_path = raw_dir / source.path
            if not source_path.is_file():
                raise IngestionError(f"configured source file is missing: {source_path}")
            if source.parser == "desc_project_descriptions":
                projects.extend(parse_desc(source_path, source))
            elif source.parser == "gpc_irp_ten_year":
                projects.extend(parse_gpc(source_path, source, utilities_by_id[utility.id]))
            else:
                raise IngestionError(f"unsupported parser {source.parser!r}")
    ids = [project.id for project in projects]
    if len(ids) != len(set(ids)):
        duplicate_ids = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
        raise IngestionError(f"normalized project IDs are not unique: {duplicate_ids}")
    output_path = repository_root / bundle.root.paths.normalized_dir / "projects.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([project.model_dump(mode="json", by_alias=True) for project in projects], indent=2) + "\n",
        encoding="utf-8",
    )
    nullable_fields = ("description", "status", "planned_in_service_date", "construction_window", "estimated_cost_usd")
    return IngestionReport(
        projects_by_utility=dict(sorted(Counter(project.utility.value for project in projects).items())),
        null_counts={field: sum(getattr(project, field) is None for project in projects) for field in nullable_fields},
        output_path=output_path,
    )
