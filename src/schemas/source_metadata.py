"""Typed schema definitions used across API and workflow boundaries."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


SourceType = Literal[
    "municipal_development_plan",
    "policy_document",
    "project_page",
    "project_document",
    "reference_case_study_document",
    "dataset",
]


class SourceMetadata(BaseModel):
    """Class representing SourceMetadata."""
    source_id: str
    source_type: SourceType
    title: str
    uri: str
    municipality_id: str | None = None
    category: str | None = None
    mime_type: str | None = None
    registered_at: datetime = Field(default_factory=utcnow)
    normalized_metadata: dict[str, str] = Field(default_factory=dict)


class SourceChunk(BaseModel):
    """Class representing SourceChunk."""
    chunk_id: str
    source_id: str
    chunk_index: int
    text: str
    body_text: str | None = None
    header_text: str | None = None
    section_path: list[str] = Field(default_factory=list)
    token_count: int
    embedding: list[float] | None = None
    embedding_model: str | None = None
    semantic_group_id: int | None = None
    municipality_id: str | None = None
    category: str | None = None
    source_type: SourceType


class IngestionResult(BaseModel):
    """Typed schema for IngestionResult."""
    source_id: str
    parsed_text_length: int
    chunk_count: int
    parser_used: str
