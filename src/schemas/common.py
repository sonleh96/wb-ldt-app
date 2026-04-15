"""Typed schema definitions used across API and workflow boundaries."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Class representing ErrorDetail."""
    code: str
    message: str
    target: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Typed schema for ErrorResponse."""
    request_id: str = ""
    error: ErrorDetail


class HealthResponse(BaseModel):
    """Typed schema for HealthResponse."""
    status: str


class VersionResponse(BaseModel):
    """Typed schema for VersionResponse."""
    app_name: str
    version: str
    environment: str


class CapabilitiesResponse(BaseModel):
    """Typed schema for CapabilitiesResponse."""
    recommendation_runs: bool
    project_review: bool
    web_research_policy_control: bool
    retrieval_modes: list[str]
    notes: str
