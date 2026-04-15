"""In-memory run tracing and inspection models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.observability.logging import summarize_node_output
from src.schemas.retrieval import RetrievalResponse

if TYPE_CHECKING:
    from src.storage.run_traces import RunTraceStore


def utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


class NodeTrace(BaseModel):
    """Trace entry for a workflow node execution."""

    node_name: str
    status: str
    started_at: datetime
    finished_at: datetime
    output_summary: dict[str, object] = Field(default_factory=dict)


class RunTrace(BaseModel):
    """Stored trace for a recommendation run."""

    run_id: str
    route: list[str] = Field(default_factory=list)
    nodes: list[NodeTrace] = Field(default_factory=list)
    model_traces: list[dict[str, object]] = Field(default_factory=list)
    retrieval_traces: list[dict[str, object]] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    ranking_snapshot: dict[str, object] = Field(default_factory=dict)
    validation_report: dict[str, object] = Field(default_factory=dict)
    failure: dict[str, object] | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class RunTraceRecorder:
    """Persist lightweight run traces for later inspection."""

    def __init__(self, store: RunTraceStore | None = None) -> None:
        """Initialize the trace recorder."""

        if store is None:
            from src.storage.run_traces import InMemoryRunTraceStore

            store = InMemoryRunTraceStore()
        self._store = store

    def start_run(self, *, run_id: str, route: list[str]) -> None:
        """Initialize trace storage for a run."""

        self._store.upsert(RunTrace(run_id=run_id, route=route, updated_at=utcnow()))

    def record_node(
        self,
        *,
        run_id: str,
        node_name: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        output: dict[str, object],
        retrieval_response: RetrievalResponse | None = None,
        evidence_ids: list[str] | None = None,
        ranking_snapshot: dict[str, object] | None = None,
        validation_report: dict[str, object] | None = None,
    ) -> None:
        """Record a node trace and any derived observability artifacts."""

        trace = self._store.get(run_id) or RunTrace(run_id=run_id)
        trace.nodes.append(
            NodeTrace(
                node_name=node_name,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                output_summary=summarize_node_output(output),
            )
        )
        if "model_name" in output or "prompt_version" in output:
            trace.model_traces.append(
                {
                    "node_name": node_name,
                    "model_name": output.get("model_name", ""),
                    "prompt_version": output.get("prompt_version", ""),
                }
            )
        if retrieval_response is not None:
            trace.retrieval_traces.append(
                {
                    "node_name": node_name,
                    "mode": retrieval_response.mode,
                    "query": retrieval_response.query,
                    "source_ids": [item.source_id for item in retrieval_response.results],
                    "chunk_ids": [item.chunk_id for item in retrieval_response.results],
                }
            )
        if evidence_ids is not None:
            trace.selected_evidence_ids = evidence_ids
        if ranking_snapshot is not None:
            trace.ranking_snapshot = ranking_snapshot
        if validation_report is not None:
            trace.validation_report = validation_report
        trace.updated_at = utcnow()
        self._store.upsert(trace)

    def record_failure(self, *, run_id: str, node_name: str, message: str) -> None:
        """Record a run failure against the trace."""

        trace = self._store.get(run_id) or RunTrace(run_id=run_id)
        trace.failure = {"node_name": node_name, "message": message}
        trace.updated_at = utcnow()
        self._store.upsert(trace)

    def get(self, run_id: str) -> RunTrace | None:
        """Return a stored trace by run id."""

        return self._store.get(run_id)
