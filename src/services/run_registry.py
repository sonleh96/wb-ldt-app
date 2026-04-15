"""Service-layer orchestration and business logic."""

import uuid
from datetime import datetime, timezone

from src.core.errors import AppError
from src.schemas.api import RecommendationRequest, RunStatusResponse
from src.schemas.run_state import RunRecord, RunState, RunTransition
from src.storage.run_store import RunStore
from src.workflows.router import build_recommendation_route


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


ALLOWED_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.PENDING: {RunState.QUEUED, RunState.CANCELLED, RunState.FAILED},
    RunState.QUEUED: {RunState.RUNNING, RunState.CANCELLED, RunState.FAILED},
    RunState.RUNNING: {RunState.VALIDATING, RunState.CANCELLED, RunState.FAILED},
    RunState.VALIDATING: {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED},
    RunState.COMPLETED: set(),
    RunState.FAILED: set(),
    RunState.CANCELLED: set(),
}


class RunRegistry:
    """Registry for Run resources."""
    def __init__(self, run_store: RunStore) -> None:
        """Initialize the instance and its dependencies."""
        self._run_store = run_store

    def create_recommendation_run(self, payload: RecommendationRequest) -> RunRecord:
        """Create recommendation run."""
        run = RunRecord(
            run_id=str(uuid.uuid4()),
            request=payload.model_dump(mode="json"),
            state=RunState.PENDING,
            current_node="create_run",
        )
        return self._run_store.create(run)

    def get_run(self, run_id: str) -> RunRecord:
        """Return run."""
        run = self._run_store.get(run_id)
        if not run:
            raise AppError(
                status_code=404,
                code="run_not_found",
                message=f"Run {run_id} was not found.",
                target="run_id",
            )
        return run

    def get_status(self, run_id: str) -> RunStatusResponse:
        """Return status."""
        run = self.get_run(run_id)
        route = build_recommendation_route(include_web_evidence=bool(run.request.get("include_web_evidence", False)))
        if run.current_node in route:
            completed_steps = route.index(run.current_node) + 1
        elif run.state == RunState.COMPLETED:
            completed_steps = len(route)
        else:
            completed_steps = 0
        total_steps = len(route)
        return RunStatusResponse(
            run_id=run.run_id,
            state=run.state,
            created_at=run.created_at.isoformat(),
            updated_at=run.updated_at.isoformat(),
            current_node=run.current_node,
            progress={
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "percent": round((completed_steps / total_steps) * 100, 1) if total_steps else 0.0,
                "current_node": run.current_node,
            },
            message=run.error_message,
        )

    def transition(self, run_id: str, to_state: RunState, *, current_node: str, note: str | None = None) -> RunRecord:
        """Handle transition."""
        run = self.get_run(run_id)
        allowed = ALLOWED_TRANSITIONS[run.state]
        if to_state not in allowed:
            raise AppError(
                status_code=409,
                code="invalid_run_transition",
                message=f"Invalid transition {run.state.value} -> {to_state.value}.",
                metadata={"run_id": run_id},
            )

        transition = RunTransition(
            from_state=run.state,
            to_state=to_state,
            note=note,
        )

        updated = run.model_copy(
            update={
                "state": to_state,
                "updated_at": utcnow(),
                "current_node": current_node,
                "transitions": [*run.transitions, transition],
            }
        )
        return self._run_store.update(updated)

    def set_result(self, run_id: str, result: dict, *, current_node: str) -> RunRecord:
        """Handle set result."""
        run = self.get_run(run_id)
        updated = run.model_copy(
            update={
                "result": result,
                "updated_at": utcnow(),
                "current_node": current_node,
            }
        )
        return self._run_store.update(updated)

    def set_current_node(self, run_id: str, *, current_node: str) -> RunRecord:
        """Handle set current node."""
        run = self.get_run(run_id)
        updated = run.model_copy(
            update={
                "current_node": current_node,
                "updated_at": utcnow(),
            }
        )
        return self._run_store.update(updated)

    def fail_run(self, run_id: str, message: str, *, current_node: str) -> RunRecord:
        """Handle fail run."""
        run = self.get_run(run_id)
        if run.state in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}:
            return run
        run = self.transition(run_id, RunState.FAILED, current_node=current_node, note=message)
        updated = run.model_copy(update={"error_message": message, "updated_at": utcnow()})
        return self._run_store.update(updated)

    def cancel_run(self, run_id: str) -> RunRecord:
        """Cancel run."""
        run = self.get_run(run_id)
        if run.state in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}:
            raise AppError(
                status_code=409,
                code="run_not_cancellable",
                message=f"Run {run_id} cannot be cancelled from state {run.state.value}.",
            )
        return self.transition(run_id, RunState.CANCELLED, current_node="cancel_run")
