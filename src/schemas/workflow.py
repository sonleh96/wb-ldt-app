"""Typed schema definitions used across API and workflow boundaries."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.domain import EvidenceBundle, RecommendationCandidate
from src.schemas.run_state import RunState


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class WorkflowState(BaseModel):
    """Typed schema for WorkflowState."""
    run_id: str
    state: RunState
    current_node: str
    municipality_id: str
    category: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    data: dict = Field(default_factory=dict)


class RetrievalPlan(BaseModel):
    """Typed schema for RetrievalPlan."""
    municipality_id: str
    category: str
    query: str
    intent_query: str = ""
    evidence_query: str = ""
    constraint_query: str = ""
    query_terms: dict[str, list[str]] = Field(default_factory=dict)
    retrieval_mode: Literal["semantic", "lexical", "hybrid"] = "hybrid"
    filters: dict[str, str] = Field(default_factory=dict)
    top_k: int = 20


class EvidenceCard(BaseModel):
    """Typed schema for EvidenceCard."""
    card_id: str
    source_id: str
    chunk_id: str
    source_type: str
    relevance_score: float = Field(ge=0.0)
    selection_reason: str
    claim_text: str
    supporting_excerpt: str
    municipality_id: str | None = None
    category: str | None = None
    provenance_complete: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)


class ContextPack(BaseModel):
    """Typed schema for ContextPack."""
    run_id: str
    cards: list[EvidenceCard] = Field(default_factory=list)
    max_cards: int
    token_budget_per_card: int
    provenance_completeness_ratio: float = 0.0
    diagnostics: dict[str, str] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    """Typed schema for EvaluationReport."""
    status: Literal["passed", "failed"]
    checks: dict[str, Literal["passed", "failed"]] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    failed_checks: list[str] = Field(default_factory=list)
    remediation_hints: list[str] = Field(default_factory=list)


class WebResearchOutput(BaseModel):
    """Typed schema for WebResearchOutput."""
    enabled: bool
    policy_reason: str
    findings_count: int = 0
    source_urls: list[str] = Field(default_factory=list)


class RecommendationGenerationOutput(BaseModel):
    """Typed schema for RecommendationGenerationOutput."""
    candidates: list[RecommendationCandidate] = Field(default_factory=list)
    model_name: str = ""
    prompt_version: str = ""


class NarrativeExplanationOutput(BaseModel):
    """Typed schema for NarrativeExplanationOutput."""
    executive_summary: str
    rationale: str
    caveats: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)


class AuditOutput(BaseModel):
    """Typed schema for AuditOutput."""
    run_id: str
    workflow_state: WorkflowState
    evidence_bundle: EvidenceBundle | None = None
    notes: list[str] = Field(default_factory=list)
