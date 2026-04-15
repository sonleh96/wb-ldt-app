"""Admin-facing source registration and ingestion services."""

from __future__ import annotations

from pathlib import Path

from src.core.errors import AppError
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.source_registry import SourceRegistry
from src.schemas.api import SourceRegistrationRequest
from src.schemas.source_metadata import IngestionResult, SourceMetadata


class SourceAdminService:
    """Provide explicit source registration, listing, and ingestion operations."""

    def __init__(self, *, source_registry: SourceRegistry, ingestion_pipeline: IngestionPipeline) -> None:
        """Initialize the admin service."""

        self._source_registry = source_registry
        self._ingestion_pipeline = ingestion_pipeline

    def list_sources(self) -> list[SourceMetadata]:
        """Return registered sources."""

        return self._source_registry.list_sources()

    def register_source(self, payload: SourceRegistrationRequest) -> SourceMetadata:
        """Register one local source after validating its file-path URI."""

        path = Path(payload.uri).expanduser()
        if not path.is_file():
            raise AppError(
                status_code=422,
                code="source_uri_invalid",
                message=f"Source URI must point to an existing local file: {payload.uri}",
                target="uri",
            )
        return self._source_registry.register_source(
            source_type=payload.source_type,
            title=payload.title,
            uri=str(path),
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
        path = Path(source.uri).expanduser()
        if not path.is_file():
            raise AppError(
                status_code=422,
                code="source_uri_invalid",
                message=f"Source URI must point to an existing local file: {source.uri}",
                target="source_id",
            )
        return self._ingestion_pipeline.ingest_source(source_id)
