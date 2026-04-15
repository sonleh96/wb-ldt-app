"""Run storage interfaces and implementations."""

from __future__ import annotations

import json
from contextlib import contextmanager
from threading import Lock
from typing import Iterator, Protocol

from src.schemas.run_state import RunRecord

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


class RunStore(Protocol):
    """Repository interface for recommendation-run persistence."""

    def create(self, run: RunRecord) -> RunRecord:
        """Persist a newly created run."""

    def get(self, run_id: str) -> RunRecord | None:
        """Return one run by id."""

    def update(self, run: RunRecord) -> RunRecord:
        """Persist run changes."""

    def list_runs(self) -> list[RunRecord]:
        """Return all stored runs."""


class InMemoryRunStore:
    """In-memory implementation for RunStore."""

    def __init__(self) -> None:
        """Initialize the run store."""

        self._runs: dict[str, RunRecord] = {}
        self._lock = Lock()

    def create(self, run: RunRecord) -> RunRecord:
        """Persist a newly created run."""

        with self._lock:
            self._runs[run.run_id] = run
            return run

    def get(self, run_id: str) -> RunRecord | None:
        """Return one run by id."""

        with self._lock:
            return self._runs.get(run_id)

    def update(self, run: RunRecord) -> RunRecord:
        """Persist run changes."""

        with self._lock:
            self._runs[run.run_id] = run
            return run

    def list_runs(self) -> list[RunRecord]:
        """Return all stored runs."""

        with self._lock:
            return list(self._runs.values())


class PostgresRunStore:
    """PostgreSQL-backed run store using JSONB for request, result, and transitions."""

    def __init__(self, *, database_url: str) -> None:
        """Initialize the run store and ensure its schema exists."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresRunStore")
        self._database_url = database_url
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a PostgreSQL connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def _ensure_schema(self) -> None:
        """Create the runs table if it does not exist."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        current_node TEXT NOT NULL,
                        error_message TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        request_payload JSONB NOT NULL,
                        result_payload JSONB NOT NULL,
                        transitions_payload JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_runs_state_updated
                    ON runs (state, updated_at DESC)
                    """
                )
            connection.commit()

    @staticmethod
    def _serialize_run(run: RunRecord) -> tuple[object, ...]:
        """Return one run serialized for SQL parameters."""

        return (
            run.run_id,
            run.state.value,
            run.current_node,
            run.error_message,
            run.created_at,
            run.updated_at,
            json.dumps(run.request),
            json.dumps(run.result),
            json.dumps([item.model_dump(mode="json") for item in run.transitions]),
        )

    @staticmethod
    def _deserialize_run(row: tuple[object, ...]) -> RunRecord:
        """Return one run deserialized from a SQL row."""

        (
            run_id,
            state,
            current_node,
            error_message,
            created_at,
            updated_at,
            request_payload,
            result_payload,
            transitions_payload,
        ) = row
        return RunRecord.model_validate(
            {
                "run_id": run_id,
                "state": state,
                "current_node": current_node,
                "error_message": error_message,
                "created_at": created_at,
                "updated_at": updated_at,
                "request": request_payload,
                "result": result_payload,
                "transitions": transitions_payload,
            }
        )

    def create(self, run: RunRecord) -> RunRecord:
        """Persist a newly created run."""

        return self._upsert(run)

    def get(self, run_id: str) -> RunRecord | None:
        """Return one run by id."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        run_id,
                        state,
                        current_node,
                        error_message,
                        created_at,
                        updated_at,
                        request_payload,
                        result_payload,
                        transitions_payload
                    FROM runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return self._deserialize_run(row)

    def update(self, run: RunRecord) -> RunRecord:
        """Persist run changes."""

        return self._upsert(run)

    def list_runs(self) -> list[RunRecord]:
        """Return all stored runs."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        run_id,
                        state,
                        current_node,
                        error_message,
                        created_at,
                        updated_at,
                        request_payload,
                        result_payload,
                        transitions_payload
                    FROM runs
                    ORDER BY created_at
                    """
                )
                rows = cursor.fetchall()
        return [self._deserialize_run(row) for row in rows]

    def _upsert(self, run: RunRecord) -> RunRecord:
        """Insert or update one run row."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO runs (
                        run_id,
                        state,
                        current_node,
                        error_message,
                        created_at,
                        updated_at,
                        request_payload,
                        result_payload,
                        transitions_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (run_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        current_node = EXCLUDED.current_node,
                        error_message = EXCLUDED.error_message,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at,
                        request_payload = EXCLUDED.request_payload,
                        result_payload = EXCLUDED.result_payload,
                        transitions_payload = EXCLUDED.transitions_payload
                    """,
                    self._serialize_run(run),
                )
            connection.commit()
        return run
