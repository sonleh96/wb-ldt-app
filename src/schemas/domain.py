"""Typed schema definitions used across API and workflow boundaries."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class CitationRecord(BaseModel):
    """Typed schema for CitationRecord."""
    citation_id: str
    title: str
    url: str
    source_type: Literal["document", "dataset", "web", "internal"]
    published_at: datetime | None = None
    accessed_at: datetime = Field(default_factory=utcnow)


class IndicatorGap(BaseModel):
    """Class representing IndicatorGap."""
    indicator_id: str
    indicator_name: str
    municipality_value: float
    national_value: float
    gap_value: float
    gap_percent: float
    higher_is_better: bool = True
    priority_weight: float = 1.0


class MunicipalityProfile(BaseModel):
    """Typed schema for MunicipalityProfile."""
    municipality_id: str
    municipality_name: str
    country_code: str
    category: str
    year: int
    indicator_values: dict[str, float] = Field(default_factory=dict)
    national_averages: dict[str, float] = Field(default_factory=dict)
    indicator_gaps: list[IndicatorGap] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """Class representing EvidenceItem."""
    evidence_id: str
    origin: Literal["analytics", "local_retrieval", "web_research", "derived_inference"]
    statement: str
    confidence: float = Field(ge=0, le=1)
    source_id: str | None = None
    chunk_id: str | None = None
    municipality_id: str | None = None
    category: str | None = None
    citation: CitationRecord | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    """Typed schema for EvidenceBundle."""
    bundle_id: str
    municipality_id: str
    category: str
    created_at: datetime = Field(default_factory=utcnow)
    items: list[EvidenceItem] = Field(default_factory=list)


class RecommendationCandidate(BaseModel):
    """Typed schema for RecommendationCandidate."""
    candidate_id: str
    title: str
    summary: str
    problem_statement: str
    intended_outcome: str
    category: str
    public_investment_type: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    caveats: list[str] = Field(default_factory=list)


class ProjectCandidate(BaseModel):
    """Typed schema for ProjectCandidate."""
    project_id: str
    title: str
    category: str
    municipality_id: str | None = None
    description: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class RankingBreakdown(BaseModel):
    """Class representing RankingBreakdown."""
    project_id: str
    total_score: float
    municipality_fit: float
    indicator_alignment: float
    development_plan_alignment: float
    readiness: float
    financing_plausibility: float
    evidence_support_strength: float
    exclusion_reasons: list[str] = Field(default_factory=list)


class PrioritySignal(BaseModel):
    """Class representing PrioritySignal."""
    indicator_id: str
    indicator_name: str
    severity: float
    reason: str


class ProjectReview(BaseModel):
    """Class representing ProjectReview."""
    project_id: str
    summary: str
    municipality_relevance: str
    readiness: str
    financing_signals: str
    implementation_considerations: list[str] = Field(default_factory=list)
    risks_and_caveats: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Typed schema for ValidationReport."""
    run_id: str
    status: Literal["passed", "warning", "failed"]
    checks: dict[str, Literal["passed", "warning", "failed"]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    failure_policy: Literal["none", "retry", "downgrade_confidence", "partial_result", "fail_run"] = "none"
    metadata: dict[str, object] = Field(default_factory=dict)
