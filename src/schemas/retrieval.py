"""Typed schema definitions used across API and workflow boundaries."""

from pydantic import BaseModel, Field

from src.schemas.source_metadata import SourceType


class RetrievalResult(BaseModel):
    """Typed schema for RetrievalResult."""
    source_id: str
    chunk_id: str
    source_type: SourceType
    score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    fused_rank: int | None = None
    fusion_score: float = 0.0
    municipality_id: str | None = None
    category: str | None = None
    snippet: str
    citation_title: str | None = None
    citation_uri: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    """Typed schema for RetrievalResponse."""
    mode: str
    query: str
    total_results: int
    results: list[RetrievalResult] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)
