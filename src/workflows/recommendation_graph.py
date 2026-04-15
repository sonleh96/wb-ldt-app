"""Workflow graph routing and execution engine."""

from src.observability.tracing import RunTraceRecorder, utcnow
from src.schemas.run_state import RunState
from src.schemas.workflow import WorkflowState
from src.services.run_registry import RunRegistry
from src.workflows.nodes.recommendation_nodes import RecommendationNodes, WorkflowContext
from src.workflows.router import build_recommendation_route


class RecommendationGraph:
    """Graph orchestrator for Recommendation."""
    def __init__(
        self,
        *,
        run_registry: RunRegistry,
        nodes: RecommendationNodes,
        run_trace_recorder: RunTraceRecorder,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._run_registry = run_registry
        self._nodes = nodes
        self._run_trace_recorder = run_trace_recorder

        self._node_map = {
            "create_run": self._nodes.create_run,
            "resolve_request_context": self._nodes.resolve_request_context,
            "compute_indicator_analysis": self._nodes.compute_indicator_analysis,
            "plan_retrieval": self._nodes.plan_retrieval,
            "retrieve_local_evidence": self._nodes.retrieve_local_evidence,
            "optionally_retrieve_web_evidence": self._nodes.optionally_retrieve_web_evidence,
            "build_evidence_bundle": self._nodes.build_evidence_bundle,
            "generate_recommendation_candidates": self._nodes.generate_recommendation_candidates,
            "rank_candidates": self._nodes.rank_candidates,
            "select_projects": self._nodes.select_projects,
            "generate_explanation": self._nodes.generate_explanation,
            "validate_output": self._nodes.validate_output,
            "finalize_run": self._nodes.finalize_run,
        }

    def execute(self, run_id: str) -> None:
        """Execute the configured workflow graph."""
        current_node = "workflow_start"
        try:
            run = self._run_registry.transition(run_id, RunState.QUEUED, current_node="queue_run")
            run = self._run_registry.transition(run_id, RunState.RUNNING, current_node="workflow_start")
            route = build_recommendation_route(
                include_web_evidence=bool(run.request.get("include_web_evidence", False))
            )
            self._run_trace_recorder.start_run(run_id=run_id, route=route)

            workflow_state = WorkflowState(
                run_id=run_id,
                state=RunState.RUNNING,
                current_node="workflow_start",
                municipality_id=str(run.request["municipality_id"]),
                category=str(run.request["category"]),
            )
            ctx = WorkflowContext(run_id=run_id, request=run.request)

            final_result: dict = {}
            for node_name in route:
                if self._run_registry.get_run(run_id).state == RunState.CANCELLED:
                    return
                current_node = node_name
                if node_name == "validate_output":
                    workflow_state = workflow_state.model_copy(update={"state": RunState.VALIDATING})
                    self._run_registry.transition(run_id, RunState.VALIDATING, current_node=node_name)
                else:
                    self._run_registry.set_current_node(run_id, current_node=node_name)

                workflow_state = workflow_state.model_copy(update={"current_node": node_name})
                started_at = utcnow()
                output = self._node_map[node_name](ctx)
                finished_at = utcnow()
                ctx.node_outputs[node_name] = output
                self._run_trace_recorder.record_node(
                    run_id=run_id,
                    node_name=node_name,
                    status="completed",
                    started_at=started_at,
                    finished_at=finished_at,
                    output=output,
                    retrieval_response=ctx.retrieval_response if node_name == "retrieve_local_evidence" else None,
                    evidence_ids=[item.evidence_id for item in (ctx.evidence_bundle.items if ctx.evidence_bundle else [])]
                    if node_name in {"build_evidence_bundle", "finalize_run"}
                    else None,
                    ranking_snapshot={
                        "ranking": ctx.ranking,
                        "selected_projects": ctx.selected_projects,
                        "excluded_projects": ctx.excluded_projects,
                    }
                    if node_name in {"rank_candidates", "select_projects", "finalize_run"}
                    else None,
                    validation_report=output.get("validation_report", {}) if node_name == "validate_output" else None,
                )
                if node_name == "validate_output" and output.get("validation_report", {}).get("failure_policy") == "fail_run":
                    self._run_registry.set_result(
                        run_id,
                        {
                            "municipality_id": str(run.request["municipality_id"]),
                            "category": str(run.request["category"]),
                            "validation_summary": ctx.validation_summary,
                            "validation_report": output.get("validation_report", {}),
                            "evaluation_report": output.get("evaluation_report", {}),
                            "node_outputs": ctx.node_outputs,
                        },
                        current_node="validate_output",
                    )
                    self._run_registry.fail_run(
                        run_id,
                        "Strict evaluation gate failed.",
                        current_node="validate_output",
                    )
                    return
                if node_name == "finalize_run":
                    final_result = output

            final_result["workflow_state"] = workflow_state.model_dump(mode="json")
            self._run_registry.set_result(run_id, final_result, current_node="finalize_run")
            self._run_registry.transition(run_id, RunState.COMPLETED, current_node="finalize_run")
        except Exception as exc:
            self._run_trace_recorder.record_failure(run_id=run_id, node_name=current_node, message=str(exc))
            self._run_registry.fail_run(run_id, str(exc), current_node=current_node)
