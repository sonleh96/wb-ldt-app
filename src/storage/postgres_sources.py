"""Optional PostgreSQL + pgvector source repository."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

from src.schemas.source_metadata import SourceChunk, SourceMetadata
from src.storage.sources import SimilarChunkMatch

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


class PostgresSourceRepository:
    """PostgreSQL-backed chunk repository with pgvector similarity search."""

    def __init__(self, *, database_url: str, embedding_dimensions: int) -> None:
        """Initialize the repository."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresSourceRepository")
        self._database_url = database_url
        self._embedding_dimensions = embedding_dimensions
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a database connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def _ensure_schema(self) -> None:
        """Create required tables and extension if absent."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sources (
                        source_id TEXT PRIMARY KEY,
                        source_payload JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS source_chunks (
                        chunk_id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                        chunk_index INTEGER NOT NULL,
                        municipality_id TEXT NULL,
                        category TEXT NULL,
                        source_type TEXT NOT NULL,
                        text TEXT NOT NULL,
                        token_count INTEGER NOT NULL,
                        embedding_model TEXT NULL,
                        semantic_group_id INTEGER NULL,
                        embedding vector({self._embedding_dimensions}) NULL,
                        chunk_payload JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_source_chunks_filters
                    ON source_chunks (municipality_id, category, source_type)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_source_chunks_embedding_hnsw
                    ON source_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    """
                )
            connection.commit()

    @staticmethod
    def _serialize_embedding(embedding: list[float] | None) -> str | None:
        """Serialize an embedding for pgvector input."""

        if embedding is None:
            return None
        return "[" + ",".join(f"{value:.12f}" for value in embedding) + "]"

    def upsert_source(self, source: SourceMetadata) -> SourceMetadata:
        """Insert or update one source."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sources (source_id, source_payload)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (source_id) DO UPDATE SET source_payload = EXCLUDED.source_payload
                    """,
                    (source.source_id, json.dumps(source.model_dump(mode="json"))),
                )
            connection.commit()
        return source

    def get_source(self, source_id: str) -> SourceMetadata | None:
        """Return one source or None."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT source_payload FROM sources WHERE source_id = %s", (source_id,))
                row = cursor.fetchone()
        if row is None:
            return None
        return SourceMetadata.model_validate(row[0])

    def list_sources(self) -> list[SourceMetadata]:
        """Return all sources."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT source_payload FROM sources ORDER BY source_id")
                rows = cursor.fetchall()
        return [SourceMetadata.model_validate(row[0]) for row in rows]

    def replace_chunks(self, source_id: str, chunks: list[SourceChunk]) -> None:
        """Replace chunks for one source."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM source_chunks WHERE source_id = %s", (source_id,))
                for chunk in chunks:
                    cursor.execute(
                        """
                        INSERT INTO source_chunks (
                            chunk_id,
                            source_id,
                            chunk_index,
                            municipality_id,
                            category,
                            source_type,
                            text,
                            token_count,
                            embedding_model,
                            semantic_group_id,
                            embedding,
                            chunk_payload
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb
                        )
                        """,
                        (
                            chunk.chunk_id,
                            chunk.source_id,
                            chunk.chunk_index,
                            chunk.municipality_id,
                            chunk.category,
                            chunk.source_type,
                            chunk.text,
                            chunk.token_count,
                            chunk.embedding_model,
                            chunk.semantic_group_id,
                            self._serialize_embedding(chunk.embedding),
                            json.dumps(chunk.model_dump(mode="json")),
                        ),
                    )
            connection.commit()

    def list_chunks(
        self,
        *,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> list[SourceChunk]:
        """Return chunks using metadata filters."""

        clauses = ["1=1"]
        params: list[object] = []
        if municipality_id:
            clauses.append("(municipality_id = %s OR municipality_id IS NULL)")
            params.append(municipality_id)
        if category:
            clauses.append("(category = %s OR category IS NULL)")
            params.append(category)
        if source_types:
            clauses.append("source_type = ANY(%s)")
            params.append(list(source_types))

        query = f"SELECT chunk_payload FROM source_chunks WHERE {' AND '.join(clauses)} ORDER BY chunk_index"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [SourceChunk.model_validate(row[0]) for row in rows]

    def search_similar_chunks(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> list[SimilarChunkMatch]:
        """Return nearest chunks using pgvector cosine distance."""

        clauses = ["embedding IS NOT NULL"]
        params: list[object] = [self._serialize_embedding(query_embedding)]
        if municipality_id:
            clauses.append("(municipality_id = %s OR municipality_id IS NULL)")
            params.append(municipality_id)
        if category:
            clauses.append("(category = %s OR category IS NULL)")
            params.append(category)
        if source_types:
            clauses.append("source_type = ANY(%s)")
            params.append(list(source_types))
        params.append(top_k)

        query = f"""
            SELECT
                c.chunk_payload,
                s.source_payload,
                1 - (c.embedding <=> %s::vector) AS score
            FROM source_chunks c
            JOIN sources s ON s.source_id = c.source_id
            WHERE {' AND '.join(clauses)}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        query_params = [params[0], *params[1:-1], params[0], params[-1]]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, query_params)
                rows = cursor.fetchall()
        return [
            SimilarChunkMatch(
                chunk=SourceChunk.model_validate(chunk_payload),
                source=SourceMetadata.model_validate(source_payload),
                score=float(score),
            )
            for chunk_payload, source_payload, score in rows
            if float(score) > 0
        ]

    def list_chunks_for_source(
        self,
        *,
        source_id: str,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> list[SourceChunk]:
        """Return ordered chunks for one source with optional chunk-index bounds."""

        clauses = ["source_id = %s"]
        params: list[object] = [source_id]
        if start_index is not None:
            clauses.append("chunk_index >= %s")
            params.append(start_index)
        if end_index is not None:
            clauses.append("chunk_index <= %s")
            params.append(end_index)
        query = f"""
            SELECT chunk_payload
            FROM source_chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY chunk_index
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [SourceChunk.model_validate(row[0]) for row in rows]
