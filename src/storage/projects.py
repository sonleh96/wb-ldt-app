"""Storage abstractions and project repository implementations."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Protocol

from src.ingestion.serbia_operational import canonical_serbia_municipality_id

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


SERBIA_PROJECT_TABLES: tuple[str, ...] = (
    "serbia_lsg_projects",
    "serbia_wbif_projects",
    "serbia_wbif_tas",
)


@dataclass(frozen=True)
class ProjectRecord:
    """Typed schema for ProjectRecord."""

    project_id: str
    title: str
    category: str
    municipality_id: str | None
    status: str
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class ProjectRepository(Protocol):
    """Repository interface for ranking project records."""

    def list_by_category(self, category: str) -> list[ProjectRecord]:
        """Return projects compatible with one category."""


class InMemoryProjectRepository:
    """In-memory implementation for ProjectRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory seed projects."""

        self._projects = [
            ProjectRecord(
                project_id="proj-001",
                title="Urban Air Monitoring Expansion",
                category="Environment",
                municipality_id=None,
                status="pipeline",
                description="Expand municipal air-quality sensors and monitoring coverage.",
                metadata={
                    "indicator_keywords": ["air", "air_quality", "pollution", "monitoring"],
                    "development_plan_alignment": 0.9,
                    "readiness": 0.75,
                    "financing_plausibility": 0.8,
                    "public_investment_types": ["capital_program"],
                },
            ),
            ProjectRecord(
                project_id="proj-002",
                title="Regional Waste Transfer Modernization",
                category="Environment",
                municipality_id=None,
                status="pipeline",
                description="Upgrade transfer stations and collection logistics for waste services.",
                metadata={
                    "indicator_keywords": ["waste", "sanitation", "recycling", "transfer"],
                    "development_plan_alignment": 0.82,
                    "readiness": 0.7,
                    "financing_plausibility": 0.72,
                    "public_investment_types": ["capital_program"],
                },
            ),
            ProjectRecord(
                project_id="proj-003",
                title="Riverbank Flood Resilience Works",
                category="Environment",
                municipality_id="srb-belgrade",
                status="concept",
                description="Localized resilience and drainage works for flood-prone corridors.",
                metadata={
                    "indicator_keywords": ["flood", "drainage", "resilience", "water"],
                    "development_plan_alignment": 0.78,
                    "readiness": 0.45,
                    "financing_plausibility": 0.65,
                    "public_investment_types": ["capital_program"],
                },
            ),
            ProjectRecord(
                project_id="proj-004",
                title="Legacy Industrial Emissions Audit",
                category="Environment",
                municipality_id="other-city",
                status="cancelled",
                description="Legacy audit program retained only for exclusion-path testing.",
                metadata={
                    "indicator_keywords": ["air", "emissions", "industrial"],
                    "development_plan_alignment": 0.55,
                    "readiness": 0.2,
                    "financing_plausibility": 0.3,
                    "public_investment_types": ["operating_program"],
                },
            ),
        ]

    def list_by_category(self, category: str) -> list[ProjectRecord]:
        """List projects by category."""

        return [project for project in self._projects if project.category == category]


class PostgresProjectRepository:
    """Postgres-backed project repository mapped from Serbia staged SQL tables."""

    def __init__(self, *, database_url: str) -> None:
        """Initialize the repository."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresProjectRepository")
        self._database_url = database_url

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a PostgreSQL connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def list_by_category(self, category: str) -> list[ProjectRecord]:
        """Return ranking-ready projects sourced from staged Serbia tables."""

        normalized_requested = _normalize_category(category)
        by_project_id: dict[str, ProjectRecord] = {}
        for table_name in SERBIA_PROJECT_TABLES:
            for row in self._load_rows(table_name):
                project = self._to_project_record(row=row, table_name=table_name)
                if _normalize_category(project.category) != normalized_requested:
                    continue
                existing = by_project_id.get(project.project_id)
                if existing is None or _record_information_score(project) > _record_information_score(existing):
                    by_project_id[project.project_id] = project
        return sorted(by_project_id.values(), key=lambda item: (item.title.lower(), item.project_id))

    def _load_rows(self, table_name: str) -> list[tuple[object, ...]]:
        """Load one staged-table row set, returning an empty list on missing-table paths."""

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT
                            id,
                            title,
                            category,
                            municipality_name,
                            sector,
                            project_code,
                            beneficiary_body,
                            raw_payload
                        FROM {table_name}
                        ORDER BY source_row_number, id
                        """
                    )
                    return list(cursor.fetchall())
        except Exception:
            return []

    def _to_project_record(self, *, row: tuple[object, ...], table_name: str) -> ProjectRecord:
        """Map one staged SQL row into a ranking-ready project record."""

        (
            row_id,
            title,
            category,
            municipality_name,
            sector,
            project_code,
            beneficiary_body,
            raw_payload,
        ) = row
        payload = raw_payload if isinstance(raw_payload, dict) else _safe_json_load(raw_payload)
        attributes = payload.get("attributes", {}) if isinstance(payload.get("attributes"), dict) else {}
        normalized_title = str(title or "").strip() or str(row_id)
        municipality = str(municipality_name).strip() if municipality_name is not None else ""
        municipality_id = canonical_serbia_municipality_id(municipality or attributes.get("lsg"))
        resolved_category = _resolve_category(
            explicit_category=category,
            sector=sector,
            title=normalized_title,
            attributes=attributes,
        )
        status = _derive_status(table_name=table_name, attributes=attributes)

        development_plan_alignment = _derive_development_plan_alignment(
            table_name=table_name,
            municipality_id=municipality_id,
            attributes=attributes,
        )
        readiness = _derive_readiness_score(status=status, attributes=attributes)
        financing_plausibility = _derive_financing_plausibility(attributes=attributes)
        indicator_keywords = _derive_indicator_keywords(
            title=normalized_title,
            category=resolved_category,
            sector=sector,
            attributes=attributes,
        )
        public_investment_types = _derive_public_investment_types(
            table_name=table_name,
            category=resolved_category,
            attributes=attributes,
        )
        summary_text = str(payload.get("summary_text") or "").strip()
        description = summary_text or str(payload.get("display_title") or normalized_title)

        return ProjectRecord(
            project_id=str(row_id),
            title=normalized_title,
            category=resolved_category,
            municipality_id=municipality_id,
            status=status,
            description=description,
            metadata={
                "source_dataset_family": table_name,
                "project_code": str(project_code) if project_code is not None else "",
                "sector": str(sector) if sector is not None else "",
                "beneficiary_body": str(beneficiary_body) if beneficiary_body is not None else "",
                "indicator_keywords": indicator_keywords,
                "development_plan_alignment": development_plan_alignment,
                "readiness": readiness,
                "financing_plausibility": financing_plausibility,
                "public_investment_types": public_investment_types,
                "agreement_signed": bool(
                    attributes.get("ga_signed") is True or attributes.get("decision_signed") is True
                ),
                "grant_amount_eur": _first_numeric(attributes, "grant_agreement_value_eur", "grant_amount_eur"),
                "cofinancing_amount_eur": _first_numeric(
                    attributes,
                    "cofinancing_amount_eur",
                    "co_funding_pledged_for_year_1_eur",
                ),
                "investment_amount_eur": _first_numeric(
                    attributes,
                    "investment_amount_eur",
                    "total_project_cost_eur",
                    "contracted_amount_eur",
                ),
            },
        )


def _safe_json_load(raw_payload: object) -> dict[str, object]:
    """Safely parse a JSON-like payload into a dictionary."""

    if isinstance(raw_payload, dict):
        return raw_payload
    try:
        loaded = json.loads(str(raw_payload))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _record_information_score(record: ProjectRecord) -> float:
    """Return a simple score used to prefer richer duplicates."""

    metadata = record.metadata
    score = 0.0
    score += 1.0 if record.description else 0.0
    score += 1.0 if metadata.get("project_code") else 0.0
    score += 1.0 if metadata.get("sector") else 0.0
    score += 1.0 if metadata.get("beneficiary_body") else 0.0
    score += 0.5 if metadata.get("grant_amount_eur") else 0.0
    score += 0.5 if metadata.get("investment_amount_eur") else 0.0
    return score


def _normalize_category(category: str) -> str:
    """Normalize category values for deterministic matching."""

    return category.strip().lower()


def _resolve_category(
    *,
    explicit_category: object,
    sector: object,
    title: str,
    attributes: dict[str, object],
) -> str:
    """Resolve retrieval/ranking category from explicit and inferred fields."""

    raw_values = [
        str(explicit_category or ""),
        str(sector or ""),
        title,
        str(attributes.get("project_sector_code") or ""),
        str(attributes.get("investment_sector") or ""),
    ]
    normalized = " ".join(raw_values).lower()
    if "transport" in normalized or "mobility" in normalized or "rail" in normalized or "road" in normalized:
        return "Sustainable Transport"
    if "energy" in normalized or "renewable" in normalized or "electric" in normalized:
        return "Energy"
    if "social" in normalized or "health" in normalized or "education" in normalized:
        return "Social"
    if "environment" in normalized or "waste" in normalized or "air" in normalized or "water" in normalized:
        return "Environment"
    category_text = str(explicit_category or "").strip()
    return category_text or "Environment"


def _derive_status(*, table_name: str, attributes: dict[str, object]) -> str:
    """Derive deterministic project status from staged fields."""

    status_text = " ".join(
        str(attributes.get(key) or "")
        for key in (
            "completion_status",
            "status",
            "ga_signed",
            "decision_signed",
        )
    ).lower()
    if "cancel" in status_text or "archiv" in status_text or "closed" in status_text:
        return "cancelled"
    if "complete" in status_text or "operational" in status_text:
        return "ready"
    if attributes.get("ga_signed") is True:
        return "ready"
    if table_name == "serbia_wbif_tas":
        return "concept"
    return "pipeline"


def _derive_development_plan_alignment(
    *,
    table_name: str,
    municipality_id: str | None,
    attributes: dict[str, object],
) -> float:
    """Compute development-plan alignment from staged project metadata."""

    if table_name == "serbia_lsg_projects":
        score = 0.82
    elif table_name == "serbia_wbif_projects":
        score = 0.75
    else:
        score = 0.68
    if municipality_id:
        score += 0.06
    if attributes.get("ga_signed") is True or attributes.get("decision_signed") is True:
        score += 0.08
    return max(0.0, min(1.0, round(score, 4)))


def _derive_readiness_score(*, status: str, attributes: dict[str, object]) -> float:
    """Compute readiness from status and agreement milestones."""

    base_by_status = {
        "ready": 0.9,
        "pipeline": 0.68,
        "concept": 0.52,
        "cancelled": 0.0,
    }
    score = base_by_status.get(status, 0.6)
    if attributes.get("ga_signed") is True:
        score += 0.08
    if attributes.get("decision_signed") is True:
        score += 0.04
    if attributes.get("completion_status") and "ongoing" in str(attributes.get("completion_status")).lower():
        score += 0.03
    return max(0.0, min(1.0, round(score, 4)))


def _derive_financing_plausibility(*, attributes: dict[str, object]) -> float:
    """Compute financing plausibility from staged monetary fields."""

    grant = _first_numeric(attributes, "grant_agreement_value_eur", "grant_amount_eur")
    cofinancing = _first_numeric(attributes, "cofinancing_amount_eur", "co_funding_pledged_for_year_1_eur")
    total = _first_numeric(
        attributes,
        "investment_amount_eur",
        "total_project_cost_eur",
        "contracted_amount_eur",
    )
    baseline = 0.55
    if total and total > 0:
        share = max(0.0, min(1.0, ((grant or 0.0) + (cofinancing or 0.0)) / total))
        baseline = 0.45 + (share * 0.5)
    elif grant or cofinancing:
        baseline = 0.7
    return max(0.0, min(1.0, round(baseline, 4)))


def _derive_public_investment_types(
    *,
    table_name: str,
    category: str,
    attributes: dict[str, object],
) -> list[str]:
    """Map staged project fields into deterministic investment types."""

    if table_name == "serbia_wbif_tas":
        return ["capacity_program", "technical_assistance"]
    if str(attributes.get("project_type") or "").lower().startswith("technical"):
        return ["capacity_program", "technical_assistance"]
    if category == "Sustainable Transport":
        return ["capital_program", "infrastructure_program"]
    return ["capital_program"]


def _derive_indicator_keywords(
    *,
    title: str,
    category: str,
    sector: object,
    attributes: dict[str, object],
) -> list[str]:
    """Build ranking keywords from title, category, sector, and selected attributes."""

    seed_tokens = [title, category, str(sector or ""), str(attributes.get("project_sector_code") or "")]
    for key in ("investment_sector", "benefits", "description", "beneficiary_body"):
        value = attributes.get(key)
        if value is not None:
            seed_tokens.append(str(value))
    joined = " ".join(seed_tokens).lower()
    tokens = re.findall(r"[a-z0-9]{3,}", joined)
    ordered = list(dict.fromkeys(tokens))
    return ordered[:40]


def _coerce_float(value: object) -> float | None:
    """Convert an arbitrary value into a float when possible."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_numeric(attributes: dict[str, object], *keys: str) -> float | None:
    """Return the first parsable numeric attribute from a list of keys."""

    for key in keys:
        value = _coerce_float(attributes.get(key))
        if value is not None:
            return value
    return None
