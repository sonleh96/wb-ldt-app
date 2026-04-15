"""Admin route handlers for source registration and ingestion."""

from fastapi import APIRouter, Request

from src.schemas.api import SourceRegistrationRequest
from src.schemas.source_metadata import IngestionResult, SourceMetadata
from src.services.source_admin_service import SourceAdminService

router = APIRouter()


def _source_admin_service(request: Request) -> SourceAdminService:
    """Return the source admin service from the app container."""

    return request.app.state.container.source_admin_service


@router.get("/sources", response_model=list[SourceMetadata])
def list_sources(request: Request) -> list[SourceMetadata]:
    """Return registered sources."""

    return _source_admin_service(request).list_sources()


@router.post("/sources", response_model=SourceMetadata)
def register_source(payload: SourceRegistrationRequest, request: Request) -> SourceMetadata:
    """Register one local source."""

    return _source_admin_service(request).register_source(payload)


@router.post("/sources/{source_id}/ingest", response_model=IngestionResult)
def ingest_source(source_id: str, request: Request) -> IngestionResult:
    """Ingest one previously registered source."""

    return _source_admin_service(request).ingest_source(source_id)
