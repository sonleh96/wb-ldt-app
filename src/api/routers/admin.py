"""Admin route handlers for source registration and ingestion."""

from fastapi import APIRouter, Depends, Query, Request

from src.api.auth import require_admin_auth
from src.schemas.api import SourceRegistrationRequest
from src.schemas.serbia_dataset import (
    SerbiaDatasetFamily,
    SerbiaDatasetIngestionReadiness,
    SerbiaDatasetMirrorStatus,
    SerbiaDatasetRow,
    SerbiaDatasetToSourceResult,
    SerbiaDocumentMirrorRowResult,
    SerbiaIngestionJobRefreshMode,
)
from src.schemas.source_metadata import IngestionResult, SourceMetadata
from src.services.serbia_dataset_admin_service import SerbiaDatasetAdminService
from src.services.source_admin_service import SourceAdminService

router = APIRouter(dependencies=[Depends(require_admin_auth)])


def _source_admin_service(request: Request) -> SourceAdminService:
    """Return the source admin service from the app container."""

    return request.app.state.container.source_admin_service


def _dataset_admin_service(request: Request) -> SerbiaDatasetAdminService:
    """Return the Serbia dataset admin service from the app container."""

    return request.app.state.container.serbia_dataset_admin_service


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


@router.get("/datasets/rows", response_model=list[SerbiaDatasetRow])
def list_dataset_rows(
    request: Request,
    dataset_family: SerbiaDatasetFamily | None = None,
    ingestion_readiness: SerbiaDatasetIngestionReadiness | None = None,
    mirror_status: SerbiaDatasetMirrorStatus | None = None,
    has_source_id: bool | None = None,
    require_gcs_uri: bool | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[SerbiaDatasetRow]:
    """Return Serbia dataset rows with lifecycle-state filters."""

    return _dataset_admin_service(request).list_rows(
        dataset_family=dataset_family,
        ingestion_readiness=ingestion_readiness,
        mirror_status=mirror_status,
        has_source_id=has_source_id,
        require_gcs_uri=require_gcs_uri,
        limit=limit,
    )


@router.get("/datasets/failures/mirroring", response_model=list[SerbiaDatasetRow])
def list_failed_mirroring_rows(
    request: Request,
    dataset_family: SerbiaDatasetFamily | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[SerbiaDatasetRow]:
    """Return Serbia dataset rows that failed document mirroring."""

    return _dataset_admin_service(request).list_failed_mirroring_rows(
        dataset_family=dataset_family,
        limit=limit,
    )


@router.post("/datasets/{dataset_family}/{row_id}/mirror", response_model=SerbiaDocumentMirrorRowResult)
def mirror_dataset_row(
    dataset_family: SerbiaDatasetFamily,
    row_id: str,
    request: Request,
    force_refresh: bool = False,
) -> SerbiaDocumentMirrorRowResult:
    """Trigger document mirroring for one Serbia dataset row."""

    refresh_mode: SerbiaIngestionJobRefreshMode = "force_refresh" if force_refresh else "pending_only"
    return _dataset_admin_service(request).mirror_row(
        dataset_family=dataset_family,
        row_id=row_id,
        refresh_mode=refresh_mode,
    )


@router.post("/datasets/{dataset_family}/{row_id}/ingest", response_model=SerbiaDatasetToSourceResult)
def ingest_dataset_row(
    dataset_family: SerbiaDatasetFamily,
    row_id: str,
    request: Request,
    force_refresh: bool = False,
) -> SerbiaDatasetToSourceResult:
    """Trigger source registration and ingestion for one Serbia dataset row."""

    refresh_mode: SerbiaIngestionJobRefreshMode = "force_refresh" if force_refresh else "pending_only"
    return _dataset_admin_service(request).ingest_row(
        dataset_family=dataset_family,
        row_id=row_id,
        refresh_mode=refresh_mode,
    )
