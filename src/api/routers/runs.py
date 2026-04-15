"""API route handlers and request/response wiring."""

from fastapi import APIRouter, BackgroundTasks, Request, status

from src.api.serializers import serialize_recommendation_result
from src.core.errors import AppError
from src.schemas.api import (
    ProjectReviewRequest,
    ProjectReviewResponse,
    RecommendationRequest,
    RecommendationResponse,
    RunStatusResponse,
)
from src.schemas.inspection import RunEvidenceResponse, RunTraceResponse, RunValidationResponse
from src.schemas.run_state import RunState
from src.services.project_review_service import ProjectReviewService
from src.services.run_inspection_service import RunInspectionService
from src.services.run_registry import RunRegistry
from src.services.workflow_launcher import RecommendationWorkflowLauncher

router = APIRouter()


def _services(
    request: Request,
) -> tuple[RunRegistry, RecommendationWorkflowLauncher, ProjectReviewService, RunInspectionService]:
    """Internal helper to services."""
    container = request.app.state.container
    return (
        container.run_registry,
        container.workflow_launcher,
        container.project_review_service,
        container.run_inspection_service,
    )


@router.post(
    "/runs/recommendations",
    response_model=RunStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_recommendation_run(
    payload: RecommendationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> RunStatusResponse:
    """Handle submit recommendation run."""
    run_registry, launcher, _, _ = _services(request)
    run = run_registry.create_recommendation_run(payload)
    background_tasks.add_task(launcher.launch, run.run_id)
    return run_registry.get_status(run.run_id)


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: str, request: Request) -> RunStatusResponse:
    """Return run status."""
    run_registry, _, _, _ = _services(request)
    return run_registry.get_status(run_id)


@router.get("/runs/{run_id}/result", response_model=RecommendationResponse)
def get_run_result(run_id: str, request: Request) -> RecommendationResponse:
    """Return run result."""
    run_registry, _, _, _ = _services(request)
    run = run_registry.get_run(run_id)

    if run.state != RunState.COMPLETED:
        raise AppError(
            status_code=409,
            code="run_not_completed",
            message=f"Run {run_id} is not completed.",
            metadata={"state": run.state.value},
        )

    return serialize_recommendation_result(run)


@router.post("/runs/{run_id}/cancel", response_model=RunStatusResponse)
def cancel_run(run_id: str, request: Request) -> RunStatusResponse:
    """Cancel run."""
    run_registry, _, _, _ = _services(request)
    run_registry.cancel_run(run_id)
    return run_registry.get_status(run_id)


@router.post("/project-reviews", response_model=ProjectReviewResponse)
def create_project_review(payload: ProjectReviewRequest, request: Request) -> ProjectReviewResponse:
    """Generate or return a cached project review."""

    _, _, project_review_service, _ = _services(request)
    return project_review_service.get_or_create_review(
        run_id=payload.run_id,
        project_id=payload.project_id,
        include_web_evidence=payload.include_web_evidence,
    )


@router.get("/project-reviews/{run_id}/{project_id}", response_model=ProjectReviewResponse)
def get_project_review(
    run_id: str,
    project_id: str,
    request: Request,
    include_web_evidence: bool = False,
) -> ProjectReviewResponse:
    """Return a cached project review or generate it on demand."""
    _, _, project_review_service, _ = _services(request)
    return project_review_service.get_or_create_review(
        run_id=run_id,
        project_id=project_id,
        include_web_evidence=include_web_evidence,
    )


@router.get("/runs/{run_id}/trace", response_model=RunTraceResponse)
def get_run_trace(run_id: str, request: Request) -> RunTraceResponse:
    """Return persisted trace details for a run."""

    _, _, _, run_inspection_service = _services(request)
    return run_inspection_service.get_run_trace(run_id)


@router.get("/runs/{run_id}/evidence", response_model=RunEvidenceResponse)
def get_run_evidence(run_id: str, request: Request) -> RunEvidenceResponse:
    """Return evidence inspection details for a run."""

    _, _, _, run_inspection_service = _services(request)
    return run_inspection_service.get_run_evidence(run_id)


@router.get("/runs/{run_id}/validation", response_model=RunValidationResponse)
def get_run_validation(run_id: str, request: Request) -> RunValidationResponse:
    """Return validation inspection details for a run."""

    _, _, _, run_inspection_service = _services(request)
    return run_inspection_service.get_run_validation(run_id)
