"""Admin-facing source registration and ingestion services."""

from __future__ import annotations

from pathlib import Path

from src.core.errors import AppError
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.source_registry import SourceRegistry
from src.schemas.api import SourceRegistrationRequest
from src.schemas.source_metadata import IngestionResult, SourceMetadata
from src.storage.documents import DocumentStore, is_gcs_uri


class SourceAdminService:
    """Provide explicit source registration, listing, and ingestion operations."""

    def __init__(
        self,
        *,
        source_registry: SourceRegistry,
        ingestion_pipeline: IngestionPipeline,
        document_store: DocumentStore,
    ) -> None:
        """Initialize the admin service."""

        self._source_registry = source_registry
        self._ingestion_pipeline = ingestion_pipeline
        self._document_store = document_store

    def list_sources(self) -> list[SourceMetadata]:
        """Return registered sources."""

        return self._source_registry.list_sources()

    def register_source(self, payload: SourceRegistrationRequest) -> SourceMetadata:
        """Register one source after validating its backing document URI."""

        uri = payload.uri.strip()
        if not self._document_store.exists(uri):
            raise AppError(
                status_code=422,
                code="source_uri_invalid",
                message=(
                    f"Source URI must point to an existing {'GCS object' if is_gcs_uri(uri) else 'local file'}: "
                    f"{payload.uri}"
                ),
                target="uri",
            )
        normalized_uri = uri if is_gcs_uri(uri) else str(Path(uri).expanduser())
        return self._source_registry.register_source(
            source_type=payload.source_type,
            title=payload.title,
            uri=normalized_uri,
            source_url=payload.source_url,
            document_url=payload.document_url,
            landing_page_url=payload.landing_page_url,
            url_kind=payload.url_kind,
            ingestion_readiness=payload.ingestion_readiness,
            municipality_id=payload.municipality_id,
            category=payload.category,
            mime_type=payload.mime_type,
            source_id=payload.source_id,
        )

    def ingest_source(self, source_id: str) -> IngestionResult:
        """Parse, chunk, embed, and persist one registered source."""

        source = self._source_registry.get_source(source_id)
        if source is None:
            raise AppError(
                status_code=404,
                code="source_not_found",
                message=f"Source {source_id} was not found.",
                target="source_id",
            )
        if not self._document_store.exists(source.uri):
            raise AppError(
                status_code=422,
                code="source_uri_invalid",
                message=(
                    f"Source URI must point to an existing "
                    f"{'GCS object' if is_gcs_uri(source.uri) else 'local file'}: {source.uri}"
                ),
                target="source_id",
            )
        return self._ingestion_pipeline.ingest_source(source_id)
