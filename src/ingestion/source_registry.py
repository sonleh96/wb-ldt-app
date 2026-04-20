"""Source ingestion, parsing, and chunking pipeline logic."""

import re
import uuid
from pathlib import Path

from src.schemas.source_metadata import SourceIngestionReadiness, SourceMetadata, SourceType, SourceUrlKind
from src.storage.documents import filename_from_uri, is_gcs_uri, suffix_from_uri
from src.storage.sources import SourceRepository


class SourceRegistry:
    """Registry for Source resources."""
    def __init__(self, source_repository: SourceRepository) -> None:
        """Initialize the instance and its dependencies."""
        self._source_repository = source_repository

    def register_source(
        self,
        *,
        source_type: SourceType,
        title: str,
        uri: str,
        municipality_id: str | None = None,
        category: str | None = None,
        mime_type: str | None = None,
        source_id: str | None = None,
        source_url: str | None = None,
        document_url: str | None = None,
        landing_page_url: str | None = None,
        url_kind: SourceUrlKind | None = None,
        ingestion_readiness: SourceIngestionReadiness | None = None,
    ) -> SourceMetadata:
        """Register source."""
        normalized_title = title.strip()
        normalized_uri = uri.strip()
        if not is_gcs_uri(normalized_uri) and not _has_uri_scheme(normalized_uri):
            normalized_uri = str(Path(normalized_uri).expanduser())
        normalized_source_url = source_url.strip() if source_url and source_url.strip() else normalized_uri
        normalized_document_url = document_url.strip() if document_url and document_url.strip() else None
        normalized_landing_page_url = (
            landing_page_url.strip() if landing_page_url and landing_page_url.strip() else None
        )
        if not normalized_title:
            raise ValueError("title cannot be empty")
        if not normalized_uri:
            raise ValueError("uri cannot be empty")

        existing_source_id = source_id or self._find_existing_source_id(
            source_type=source_type,
            uri=normalized_uri,
            municipality_id=municipality_id,
            category=category,
        )
        normalized_metadata: dict[str, str] = {
            "filename": filename_from_uri(normalized_uri),
            "extension": suffix_from_uri(normalized_uri),
            "storage_backend": "gcs" if is_gcs_uri(normalized_uri) else "local",
        }
        source = SourceMetadata(
            source_id=existing_source_id or str(uuid.uuid4()),
            source_type=source_type,
            title=normalized_title,
            uri=normalized_uri,
            source_url=normalized_source_url,
            document_url=normalized_document_url,
            landing_page_url=normalized_landing_page_url,
            url_kind=url_kind or "unknown",
            ingestion_readiness=ingestion_readiness or "ready",
            municipality_id=municipality_id,
            category=category,
            mime_type=mime_type,
            normalized_metadata=normalized_metadata,
        )
        return self._source_repository.upsert_source(source)

    def list_sources(self) -> list[SourceMetadata]:
        """List sources."""
        return self._source_repository.list_sources()

    def get_source(self, source_id: str) -> SourceMetadata | None:
        """Return one source by id."""

        return self._source_repository.get_source(source_id)

    def reindex_all(self) -> dict[str, int]:
        """Handle reindex all."""
        return {"source_count": len(self._source_repository.list_sources())}

    def _find_existing_source_id(
        self,
        *,
        source_type: SourceType,
        uri: str,
        municipality_id: str | None,
        category: str | None,
    ) -> str | None:
        """Return an existing source id for an idempotent registration match."""

        for existing in self._source_repository.list_sources():
            if existing.uri != uri:
                continue
            if existing.source_type != source_type:
                continue
            if existing.municipality_id != municipality_id:
                continue
            if existing.category != category:
                continue
            return existing.source_id
        return None


def _has_uri_scheme(value: str) -> bool:
    """Return whether a value starts with a generic URI scheme."""

    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value))
