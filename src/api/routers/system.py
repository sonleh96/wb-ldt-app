"""API route handlers and request/response wiring."""

from fastapi import APIRouter, Request

from src.schemas.common import CapabilitiesResponse, HealthResponse, VersionResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Handle health."""
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
def version(request: Request) -> VersionResponse:
    """Handle version."""
    settings = request.app.state.settings
    return VersionResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities() -> CapabilitiesResponse:
    """Handle capabilities."""
    return CapabilitiesResponse(
        recommendation_runs=True,
        project_review=True,
        web_research_policy_control=False,
        retrieval_modes=["semantic", "lexical", "hybrid"],
        notes="Recommendation runs, project reviews, inspection endpoints, and admin source ingestion are available.",
    )
