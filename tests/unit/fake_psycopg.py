"""Fake psycopg module used for unit tests without a live PostgreSQL server."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FakePostgresDatabase:
    """Shared in-memory database state for fake psycopg connections."""

    runs: dict[str, dict[str, object]] = field(default_factory=dict)
    project_reviews: dict[tuple[str, str, bool], dict[str, object]] = field(default_factory=dict)
    run_traces: dict[str, dict[str, object]] = field(default_factory=dict)


class FakeCursor:
    """Minimal DB-API-like cursor for the runtime persistence tests."""

    def __init__(self, database: FakePostgresDatabase) -> None:
        """Initialize the cursor."""

        self._database = database
        self._one: tuple[object, ...] | None = None
        self._many: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeCursor:
        """Enter the cursor context."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Exit the cursor context."""

        return False

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        """Execute a supported SQL statement against the fake database."""

        normalized = " ".join(query.split()).lower()
        params = params or tuple()
        self._one = None
        self._many = []

        if normalized.startswith("create table") or normalized.startswith("create index") or normalized.startswith(
            "create extension"
        ):
            return

        if normalized.startswith("insert into runs "):
            self._database.runs[str(params[0])] = {
                "run_id": params[0],
                "state": params[1],
                "current_node": params[2],
                "error_message": params[3],
                "created_at": params[4],
                "updated_at": params[5],
                "request_payload": json.loads(str(params[6])),
                "result_payload": json.loads(str(params[7])),
                "transitions_payload": json.loads(str(params[8])),
            }
            return

        if "from runs" in normalized and "where run_id = %s" in normalized:
            row = self._database.runs.get(str(params[0]))
            self._one = _run_row(row) if row else None
            return

        if "from runs" in normalized and "order by created_at" in normalized:
            self._many = [_run_row(row) for row in self._database.runs.values()]
            return

        if normalized.startswith("insert into project_reviews "):
            key = (str(params[0]), str(params[1]), bool(params[2]))
            self._database.project_reviews[key] = {
                "run_id": params[0],
                "project_id": params[1],
                "include_web_evidence": params[2],
                "validation_summary": params[3],
                "evidence_ids": json.loads(str(params[4])),
                "cached_at": params[5],
                "review_payload": json.loads(str(params[6])),
            }
            return

        if "from project_reviews" in normalized and "where run_id = %s and project_id = %s and include_web_evidence = %s" in normalized:
            key = (str(params[0]), str(params[1]), bool(params[2]))
            row = self._database.project_reviews.get(key)
            self._one = _project_review_row(row) if row else None
            return

        if normalized.startswith("insert into run_traces "):
            self._database.run_traces[str(params[0])] = {
                "run_id": params[0],
                "updated_at": params[1],
                "route": json.loads(str(params[2])),
                "nodes": json.loads(str(params[3])),
                "model_traces": json.loads(str(params[4])),
                "retrieval_traces": json.loads(str(params[5])),
                "selected_evidence_ids": json.loads(str(params[6])),
                "ranking_snapshot": json.loads(str(params[7])),
                "validation_report": json.loads(str(params[8])),
                "failure": json.loads(str(params[9])),
            }
            return

        if "from run_traces" in normalized and "where run_id = %s" in normalized:
            row = self._database.run_traces.get(str(params[0]))
            self._one = _run_trace_row(row) if row else None
            return

        raise AssertionError(f"Unsupported fake SQL: {query}")

    def fetchone(self) -> tuple[object, ...] | None:
        """Return one result row."""

        return self._one

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all result rows."""

        return list(self._many)


class FakeConnection:
    """Minimal DB-API-like connection for the runtime persistence tests."""

    def __init__(self, database: FakePostgresDatabase) -> None:
        """Initialize the connection."""

        self._database = database

    def __enter__(self) -> FakeConnection:
        """Enter the connection context."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Exit the connection context."""

        return False

    def cursor(self) -> FakeCursor:
        """Return a new fake cursor."""

        return FakeCursor(self._database)

    def commit(self) -> None:
        """Commit the current transaction."""

        return None


class FakePsycopg:
    """Minimal psycopg-compatible facade with shared in-memory state."""

    def __init__(self, database: FakePostgresDatabase | None = None) -> None:
        """Initialize the fake psycopg facade."""

        self.database = database or FakePostgresDatabase()

    def connect(self, _: str) -> FakeConnection:
        """Return a fake connection."""

        return FakeConnection(self.database)


def _run_row(row: dict[str, object] | None) -> tuple[object, ...] | None:
    """Return one fake result row for the runs table."""

    if row is None:
        return None
    return (
        row["run_id"],
        row["state"],
        row["current_node"],
        row["error_message"],
        row["created_at"],
        row["updated_at"],
        row["request_payload"],
        row["result_payload"],
        row["transitions_payload"],
    )


def _project_review_row(row: dict[str, object] | None) -> tuple[object, ...] | None:
    """Return one fake result row for the project_reviews table."""

    if row is None:
        return None
    return (
        row["run_id"],
        row["project_id"],
        row["include_web_evidence"],
        row["validation_summary"],
        row["evidence_ids"],
        row["cached_at"],
        row["review_payload"],
    )


def _run_trace_row(row: dict[str, object] | None) -> tuple[object, ...] | None:
    """Return one fake result row for the run_traces table."""

    if row is None:
        return None
    return (
        row["run_id"],
        row["updated_at"],
        row["route"],
        row["nodes"],
        row["model_traces"],
        row["retrieval_traces"],
        row["selected_evidence_ids"],
        row["ranking_snapshot"],
        row["validation_report"],
        row["failure"],
    )
