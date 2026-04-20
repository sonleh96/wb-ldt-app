"""Typed schema definitions used across API and workflow boundaries."""

from pydantic import BaseModel, Field

from src.schemas.domain import ProjectReview
from src.schemas.run_state import RunState
from src.schemas.source_metadata import SourceIngestionReadiness, SourceType, SourceUrlKind


class ProgressInfo(BaseModel):
    """Typed schema for run progress details."""

    completed_steps: int = 0
    total_steps: int = 0
    percent: float = 0.0
    current_node: str = ""


class RecommendationRequest(BaseModel):
    """Typed schema for RecommendationRequest."""
    municipality_id: str
    category: str
    year: int
    include_web_evidence: bool = False
    language: str = "en"
    top_n_projects: int = Field(default=3, ge=1, le=20)


class RecommendationResponse(BaseModel):
    """Typed schema for RecommendationResponse."""
    run_id: str
    status: RunState
    municipality_id: str
    category: str
    run_metadata: dict[str, object] = Field(default_factory=dict)
    context: dict[str, object] = Field(default_factory=dict)
    indicator_summary: list[dict[str, object]] = Field(default_factory=list)
    recommendation_candidates: list[dict] = Field(default_factory=list)
    selected_projects: list[dict] = Field(default_factory=list)
    ranking: list[dict] = Field(default_factory=list)
    explanation: str = ""
    explanation_narrative: dict[str, object] = Field(default_factory=dict)
    evidence_bundle_id: str | None = None
    evidence_bundle_summary: dict[str, object] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    validation_summary: str = "not_validated"
    validation_report: dict[str, object] = Field(default_factory=dict)
    context_pack_summary: dict[str, object] = Field(default_factory=dict)
    retrieval_diagnostics: dict[str, object] = Field(default_factory=dict)
    evaluation_report: dict[str, object] = Field(default_factory=dict)


class RunStatusResponse(BaseModel):
    """Typed schema for RunStatusResponse."""
    run_id: str
    state: RunState
    created_at: str
    updated_at: str
    current_node: str
    progress: ProgressInfo = Field(default_factory=ProgressInfo)
    message: str | None = None


class ProjectReviewRequest(BaseModel):
    """Typed schema for ProjectReviewRequest."""
    run_id: str
    project_id: str
    include_web_evidence: bool = False


class ProjectReviewResponse(BaseModel):
    """Typed schema for ProjectReviewResponse."""
    run_id: str
    project_review: ProjectReview
    validation_summary: str


class SourceRegistrationRequest(BaseModel):
    """Typed schema for registering one source."""

    source_type: SourceType
    title: str
    uri: str
    source_url: str | None = None
    document_url: str | None = None
    landing_page_url: str | None = None
    url_kind: SourceUrlKind | None = None
    ingestion_readiness: SourceIngestionReadiness | None = None
    municipality_id: str | None = None
    category: str | None = None
    mime_type: str | None = None
    source_id: str | None = None
