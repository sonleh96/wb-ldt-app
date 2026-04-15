"""Inspection services for run traces, evidence, and validation outputs."""

from src.core.errors import AppError
from src.observability.tracing import RunTraceRecorder
from src.schemas.inspection import RunEvidenceResponse, RunTraceResponse, RunValidationResponse
from src.services.run_registry import RunRegistry


class RunInspectionService:
    """Provide structured inspection views over completed or failed runs."""

    def __init__(self, *, run_registry: RunRegistry, run_trace_recorder: RunTraceRecorder) -> None:
        """Initialize the service."""

        self._run_registry = run_registry
        self._run_trace_recorder = run_trace_recorder

    def get_run_trace(self, run_id: str) -> RunTraceResponse:
        """Return a stored trace payload."""

        self._run_registry.get_run(run_id)
        trace = self._run_trace_recorder.get(run_id)
        if trace is None:
            raise AppError(status_code=404, code="run_trace_not_found", message=f"Trace for run {run_id} was not found.")
        return RunTraceResponse(
            run_id=trace.run_id,
            route=trace.route,
            nodes=[item.model_dump(mode="json") for item in trace.nodes],
            model_traces=trace.model_traces,
            retrieval_traces=trace.retrieval_traces,
            selected_evidence_ids=trace.selected_evidence_ids,
            ranking_snapshot=trace.ranking_snapshot,
            validation_report=trace.validation_report,
            failure=trace.failure,
        )

    def get_run_evidence(self, run_id: str) -> RunEvidenceResponse:
        """Return evidence inspection details for a run."""

        run = self._run_registry.get_run(run_id)
        trace = self._run_trace_recorder.get(run_id)
        evidence_items = run.result.get("evidence_bundle_summary", {}).get("evidence_items", [])
        if not evidence_items:
            evidence_items = run.result.get("node_outputs", {}).get("build_evidence_bundle", {}).get("evidence_items", [])
        return RunEvidenceResponse(
            run_id=run_id,
            evidence_bundle_id=run.result.get("evidence_bundle_id"),
            evidence_items=evidence_items,
            selected_evidence_ids=trace.selected_evidence_ids if trace else [],
        )

    def get_run_validation(self, run_id: str) -> RunValidationResponse:
        """Return validation inspection details for a run."""

        run = self._run_registry.get_run(run_id)
        validation_report = run.result.get("validation_report")
        if not validation_report:
            validation_report = run.result.get("node_outputs", {}).get("validate_output", {}).get("validation_report", {})
        evaluation_report = run.result.get("evaluation_report")
        if not evaluation_report:
            evaluation_report = run.result.get("node_outputs", {}).get("validate_output", {}).get("evaluation_report", {})
        return RunValidationResponse(
            run_id=run_id,
            validation_summary=str(run.result.get("validation_summary", "not_validated")),
            validation_report=validation_report,
            evaluation_report=evaluation_report or {},
        )
