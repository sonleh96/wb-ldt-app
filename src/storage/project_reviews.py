"""Project-review storage interfaces and implementations."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterator, Protocol

from src.schemas.domain import ProjectReview

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


def utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProjectReviewRecord:
    """Cached project review entry."""

    run_id: str
    project_id: str
    include_web_evidence: bool
    review: ProjectReview
    validation_summary: str
    evidence_ids: list[str]
    cached_at: datetime


class ProjectReviewStore(Protocol):
    """Repository interface for persisted project reviews."""

    def get(self, *, run_id: str, project_id: str, include_web_evidence: bool) -> ProjectReviewRecord | None:
        """Return one cached project review if present."""

    def upsert(self, record: ProjectReviewRecord) -> ProjectReviewRecord:
        """Store or replace one cached project review."""


class InMemoryProjectReviewStore:
    """In-memory cache for project review results."""

    def __init__(self) -> None:
        """Initialize the store."""

        self._records: dict[tuple[str, str, bool], ProjectReviewRecord] = {}
        self._lock = Lock()

    def get(self, *, run_id: str, project_id: str, include_web_evidence: bool) -> ProjectReviewRecord | None:
        """Return a cached review if present."""

        with self._lock:
            return self._records.get((run_id, project_id, include_web_evidence))

    def upsert(self, record: ProjectReviewRecord) -> ProjectReviewRecord:
        """Store or replace a cached review."""

        with self._lock:
            self._records[(record.run_id, record.project_id, record.include_web_evidence)] = record
            return record


class PostgresProjectReviewStore:
    """PostgreSQL-backed cache for generated project reviews."""

    def __init__(self, *, database_url: str) -> None:
        """Initialize the review store and ensure its schema exists."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresProjectReviewStore")
        self._database_url = database_url
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a PostgreSQL connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def _ensure_schema(self) -> None:
        """Create the project-reviews table if it does not exist."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS project_reviews (
                        run_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        include_web_evidence BOOLEAN NOT NULL,
                        validation_summary TEXT NOT NULL,
                        evidence_ids JSONB NOT NULL,
                        cached_at TIMESTAMPTZ NOT NULL,
                        review_payload JSONB NOT NULL,
                        PRIMARY KEY (run_id, project_id, include_web_evidence)
                    )
                    """
                )
            connection.commit()

    def get(self, *, run_id: str, project_id: str, include_web_evidence: bool) -> ProjectReviewRecord | None:
        """Return one cached project review if present."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        run_id,
                        project_id,
                        include_web_evidence,
                        validation_summary,
                        evidence_ids,
                        cached_at,
                        review_payload
                    FROM project_reviews
                    WHERE run_id = %s AND project_id = %s AND include_web_evidence = %s
                    """,
                    (run_id, project_id, include_web_evidence),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return ProjectReviewRecord(
            run_id=str(row[0]),
            project_id=str(row[1]),
            include_web_evidence=bool(row[2]),
            validation_summary=str(row[3]),
            evidence_ids=[str(item) for item in row[4]],
            cached_at=row[5],
            review=ProjectReview.model_validate(row[6]),
        )

    def upsert(self, record: ProjectReviewRecord) -> ProjectReviewRecord:
        """Store or replace one cached project review."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO project_reviews (
                        run_id,
                        project_id,
                        include_web_evidence,
                        validation_summary,
                        evidence_ids,
                        cached_at,
                        review_payload
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                    ON CONFLICT (run_id, project_id, include_web_evidence) DO UPDATE SET
                        validation_summary = EXCLUDED.validation_summary,
                        evidence_ids = EXCLUDED.evidence_ids,
                        cached_at = EXCLUDED.cached_at,
                        review_payload = EXCLUDED.review_payload
                    """,
                    (
                        record.run_id,
                        record.project_id,
                        record.include_web_evidence,
                        record.validation_summary,
                        json.dumps(record.evidence_ids),
                        record.cached_at,
                        json.dumps(record.review.model_dump(mode="json")),
                    ),
                )
            connection.commit()
        return record
