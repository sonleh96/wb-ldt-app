"""Storage abstractions and in-memory repository implementations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from src.schemas.source_metadata import SourceChunk, SourceMetadata


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity between two vectors."""

    if not left or not right:
        return 0.0
    numerator = sum(lv * rv for lv, rv in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass(frozen=True)
class SimilarChunkMatch:
    """Embedding similarity search result."""

    chunk: SourceChunk
    source: SourceMetadata | None
    score: float


class SourceRepository(Protocol):
    """Repository interface for source metadata and chunk storage."""

    def upsert_source(self, source: SourceMetadata) -> SourceMetadata:
        """Insert or update a source record."""

    def get_source(self, source_id: str) -> SourceMetadata | None:
        """Return one source record."""

    def list_sources(self) -> list[SourceMetadata]:
        """Return all source records."""

    def replace_chunks(self, source_id: str, chunks: list[SourceChunk]) -> None:
        """Replace chunks for a source."""

    def list_chunks(
        self,
        *,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> list[SourceChunk]:
        """Return stored chunks with optional filters."""

    def search_similar_chunks(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> list[SimilarChunkMatch]:
        """Return nearest chunks for a query embedding."""

    def list_chunks_for_source(
        self,
        *,
        source_id: str,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> list[SourceChunk]:
        """Return ordered chunks for one source, optionally bounded by chunk index."""


class InMemorySourceRepository:
    """In-memory implementation for SourceRepository."""

    def __init__(self) -> None:
        """Initialize the instance and its dependencies."""

        self._sources: dict[str, SourceMetadata] = {}
        self._chunks_by_source: dict[str, list[SourceChunk]] = {}
        self._lock = Lock()

    def upsert_source(self, source: SourceMetadata) -> SourceMetadata:
        """Handle upsert source."""

        with self._lock:
            self._sources[source.source_id] = source
            if source.source_id not in self._chunks_by_source:
                self._chunks_by_source[source.source_id] = []
            return source

    def get_source(self, source_id: str) -> SourceMetadata | None:
        """Return source."""

        with self._lock:
            return self._sources.get(source_id)

    def list_sources(self) -> list[SourceMetadata]:
        """List sources."""

        with self._lock:
            return list(self._sources.values())

    def replace_chunks(self, source_id: str, chunks: list[SourceChunk]) -> None:
        """Handle replace chunks."""

        with self._lock:
            self._chunks_by_source[source_id] = chunks

    def list_chunks(
        self,
        *,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> list[SourceChunk]:
        """List chunks."""

        with self._lock:
            chunks = [chunk for rows in self._chunks_by_source.values() for chunk in rows]

        filtered: list[SourceChunk] = []
        for chunk in chunks:
            if municipality_id and chunk.municipality_id not in {municipality_id, None}:
                continue
            if category and chunk.category not in {category, None}:
                continue
            if source_types and chunk.source_type not in source_types:
                continue
            filtered.append(chunk)
        return filtered

    def search_similar_chunks(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> list[SimilarChunkMatch]:
        """Return nearest chunks using in-memory cosine similarity."""

        matches: list[SimilarChunkMatch] = []
        for chunk in self.list_chunks(
            municipality_id=municipality_id,
            category=category,
            source_types=source_types,
        ):
            if not chunk.embedding:
                continue
            score = _cosine_similarity(query_embedding, chunk.embedding)
            if score <= 0:
                continue
            matches.append(
                SimilarChunkMatch(
                    chunk=chunk,
                    source=self.get_source(chunk.source_id),
                    score=score,
                )
            )
        return sorted(matches, key=lambda item: item.score, reverse=True)[:top_k]

    def list_chunks_for_source(
        self,
        *,
        source_id: str,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> list[SourceChunk]:
        """Return ordered chunks for one source with optional index bounds."""

        with self._lock:
            chunks = list(self._chunks_by_source.get(source_id, []))
        filtered = []
        for chunk in chunks:
            if start_index is not None and chunk.chunk_index < start_index:
                continue
            if end_index is not None and chunk.chunk_index > end_index:
                continue
            filtered.append(chunk)
        return sorted(filtered, key=lambda item: item.chunk_index)
