"""Internal admin service for Serbia dataset staging operations."""

from __future__ import annotations

from src.core.errors import AppError
from src.schemas.serbia_dataset import (
    SerbiaDatasetFamily,
    SerbiaDatasetIngestionReadiness,
    SerbiaDatasetMirrorStatus,
    SerbiaDatasetRow,
    SerbiaDatasetToSourceResult,
    SerbiaDocumentMirrorRowResult,
    SerbiaIngestionJobRefreshMode,
)
from src.services.serbia_document_mirror import SerbiaDocumentMirrorService
from src.services.serbia_source_ingestion import SerbiaSourceIngestionService
from src.storage.serbia_datasets import SerbiaDatasetRepository


class SerbiaDatasetAdminService:
    """Admin operations for Serbia dataset rows and staged ingestion."""

    def __init__(
        self,
        *,
        repository: SerbiaDatasetRepository,
        document_mirror_service: SerbiaDocumentMirrorService | None,
        source_ingestion_service: SerbiaSourceIngestionService,
    ) -> None:
        """Initialize the admin service."""

        self._repository = repository
        self._document_mirror_service = document_mirror_service
        self._source_ingestion_service = source_ingestion_service

    def list_rows(
        self,
        *,
        dataset_family: SerbiaDatasetFamily | None = None,
        ingestion_readiness: SerbiaDatasetIngestionReadiness | None = None,
        mirror_status: SerbiaDatasetMirrorStatus | None = None,
        has_source_id: bool | None = None,
        require_gcs_uri: bool | None = None,
        limit: int = 100,
    ) -> list[SerbiaDatasetRow]:
        """List Serbia dataset rows with lifecycle-state filters."""

        return self._repository.list_rows(
            dataset_families={dataset_family} if dataset_family else None,
            ingestion_readinesses={ingestion_readiness} if ingestion_readiness else None,
            mirror_statuses={mirror_status} if mirror_status else None,
            has_source_id=has_source_id,
            require_gcs_uri=require_gcs_uri,
            limit=limit,
        )

    def list_failed_mirroring_rows(
        self,
        *,
        dataset_family: SerbiaDatasetFamily | None = None,
        limit: int = 100,
    ) -> list[SerbiaDatasetRow]:
        """List rows whose mirror stage failed."""

        return self._repository.list_rows(
            dataset_families={dataset_family} if dataset_family else None,
            mirror_statuses={"failed"},
            limit=limit,
        )

    def mirror_row(
        self,
        *,
        dataset_family: SerbiaDatasetFamily,
        row_id: str,
        refresh_mode: SerbiaIngestionJobRefreshMode = "pending_only",
    ) -> SerbiaDocumentMirrorRowResult:
        """Trigger document mirroring for one row."""

        if self._document_mirror_service is None:
            raise AppError(
                status_code=409,
                code="dataset_mirror_not_configured",
                message="Serbia document mirroring is not configured.",
            )
        try:
            return self._document_mirror_service.mirror_row(
                dataset_family=dataset_family,
                row_id=row_id,
                refresh_mode=refresh_mode,
            )
        except ValueError as exc:
            raise AppError(
                status_code=404,
                code="dataset_row_not_found",
                message=str(exc),
                target="row_id",
            ) from exc

    def ingest_row(
        self,
        *,
        dataset_family: SerbiaDatasetFamily,
        row_id: str,
        refresh_mode: SerbiaIngestionJobRefreshMode = "pending_only",
    ) -> SerbiaDatasetToSourceResult:
        """Trigger source registration/ingestion for one row."""

        try:
            return self._source_ingestion_service.ingest_row(
                dataset_family=dataset_family,
                row_id=row_id,
                refresh_mode=refresh_mode,
            )
        except ValueError as exc:
            raise AppError(
                status_code=404,
                code="dataset_row_not_found",
                message=str(exc),
                target="row_id",
            ) from exc
