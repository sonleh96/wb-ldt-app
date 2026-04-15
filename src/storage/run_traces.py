"""Run trace storage interfaces and implementations."""

from __future__ import annotations

import json
from contextlib import contextmanager
from threading import Lock
from typing import Iterator, Protocol

from src.observability.tracing import RunTrace

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


class RunTraceStore(Protocol):
    """Repository interface for persisted run traces."""

    def upsert(self, trace: RunTrace) -> RunTrace:
        """Store or replace one run trace."""

    def get(self, run_id: str) -> RunTrace | None:
        """Return one run trace by id."""


class InMemoryRunTraceStore:
    """In-memory implementation for RunTraceStore."""

    def __init__(self) -> None:
        """Initialize the trace store."""

        self._traces: dict[str, RunTrace] = {}
        self._lock = Lock()

    def upsert(self, trace: RunTrace) -> RunTrace:
        """Store or replace one run trace."""

        with self._lock:
            self._traces[trace.run_id] = trace
            return trace

    def get(self, run_id: str) -> RunTrace | None:
        """Return one run trace by id."""

        with self._lock:
            return self._traces.get(run_id)


class PostgresRunTraceStore:
    """PostgreSQL-backed trace store using JSONB payloads."""

    def __init__(self, *, database_url: str) -> None:
        """Initialize the trace store and ensure its schema exists."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresRunTraceStore")
        self._database_url = database_url
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a PostgreSQL connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def _ensure_schema(self) -> None:
        """Create the run-traces table if it does not exist."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS run_traces (
                        run_id TEXT PRIMARY KEY,
                        updated_at TIMESTAMPTZ NOT NULL,
                        route JSONB NOT NULL,
                        nodes JSONB NOT NULL,
                        model_traces JSONB NOT NULL,
                        retrieval_traces JSONB NOT NULL,
                        selected_evidence_ids JSONB NOT NULL,
                        ranking_snapshot JSONB NOT NULL,
                        validation_report JSONB NOT NULL,
                        failure JSONB NULL
                    )
                    """
                )
            connection.commit()

    def upsert(self, trace: RunTrace) -> RunTrace:
        """Store or replace one run trace."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO run_traces (
                        run_id,
                        updated_at,
                        route,
                        nodes,
                        model_traces,
                        retrieval_traces,
                        selected_evidence_ids,
                        ranking_snapshot,
                        validation_report,
                        failure
                    ) VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (run_id) DO UPDATE SET
                        updated_at = EXCLUDED.updated_at,
                        route = EXCLUDED.route,
                        nodes = EXCLUDED.nodes,
                        model_traces = EXCLUDED.model_traces,
                        retrieval_traces = EXCLUDED.retrieval_traces,
                        selected_evidence_ids = EXCLUDED.selected_evidence_ids,
                        ranking_snapshot = EXCLUDED.ranking_snapshot,
                        validation_report = EXCLUDED.validation_report,
                        failure = EXCLUDED.failure
                    """,
                    (
                        trace.run_id,
                        trace.updated_at,
                        json.dumps(trace.route),
                        json.dumps([item.model_dump(mode="json") for item in trace.nodes]),
                        json.dumps(trace.model_traces),
                        json.dumps(trace.retrieval_traces),
                        json.dumps(trace.selected_evidence_ids),
                        json.dumps(trace.ranking_snapshot),
                        json.dumps(trace.validation_report),
                        json.dumps(trace.failure),
                    ),
                )
            connection.commit()
        return trace

    def get(self, run_id: str) -> RunTrace | None:
        """Return one run trace by id."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        run_id,
                        updated_at,
                        route,
                        nodes,
                        model_traces,
                        retrieval_traces,
                        selected_evidence_ids,
                        ranking_snapshot,
                        validation_report,
                        failure
                    FROM run_traces
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        (
            stored_run_id,
            updated_at,
            route,
            nodes,
            model_traces,
            retrieval_traces,
            selected_evidence_ids,
            ranking_snapshot,
            validation_report,
            failure,
        ) = row
        return RunTrace.model_validate(
            {
                "run_id": stored_run_id,
                "updated_at": updated_at,
                "route": route,
                "nodes": nodes,
                "model_traces": model_traces,
                "retrieval_traces": retrieval_traces,
                "selected_evidence_ids": selected_evidence_ids,
                "ranking_snapshot": ranking_snapshot,
                "validation_report": validation_report,
                "failure": failure,
            }
        )
