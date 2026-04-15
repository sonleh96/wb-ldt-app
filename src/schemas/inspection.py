"""Typed schemas for run inspection and observability endpoints."""

from pydantic import BaseModel, Field


class RunTraceResponse(BaseModel):
    """Trace payload for a workflow run."""

    run_id: str
    route: list[str] = Field(default_factory=list)
    nodes: list[dict[str, object]] = Field(default_factory=list)
    model_traces: list[dict[str, object]] = Field(default_factory=list)
    retrieval_traces: list[dict[str, object]] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    ranking_snapshot: dict[str, object] = Field(default_factory=dict)
    validation_report: dict[str, object] = Field(default_factory=dict)
    failure: dict[str, object] | None = None


class RunEvidenceResponse(BaseModel):
    """Evidence inspection payload for a workflow run."""

    run_id: str
    evidence_bundle_id: str | None = None
    evidence_items: list[dict[str, object]] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)


class RunValidationResponse(BaseModel):
    """Validation inspection payload for a workflow run."""

    run_id: str
    validation_summary: str
    validation_report: dict[str, object] = Field(default_factory=dict)
    evaluation_report: dict[str, object] = Field(default_factory=dict)
