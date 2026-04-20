"""Register mirrored and structured Serbia dataset rows into source/chunk storage."""

from __future__ import annotations

import re

from src.embeddings.client import EmbeddingClient
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.serbia_operational import canonical_serbia_municipality_id
from src.ingestion.source_registry import SourceRegistry
from src.schemas.serbia_dataset import (
    SerbiaDatasetFamily,
    SerbiaDatasetRow,
    SerbiaDatasetToSourceResult,
    SerbiaIngestionJobRefreshMode,
    SerbiaSourceIngestionSummary,
)
from src.schemas.source_metadata import SourceChunk, SourceType
from src.storage.serbia_datasets import SerbiaDatasetRepository
from src.storage.sources import SourceRepository


FAMILY_SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "serbia_national_documents": "policy_document",
    "serbia_municipal_development_plans": "municipal_development_plan",
    "serbia_lsg_projects": "dataset",
    "serbia_wbif_projects": "project_page",
    "serbia_wbif_tas": "project_page",
}


class SerbiaSourceIngestionService:
    """Bridge Serbia dataset rows into retrieval-serving source/chunk storage."""

    def __init__(
        self,
        *,
        dataset_repository: SerbiaDatasetRepository,
        source_registry: SourceRegistry,
        ingestion_pipeline: IngestionPipeline,
        source_repository: SourceRepository,
        embedding_client: EmbeddingClient,
    ) -> None:
        """Initialize the source-ingestion service."""

        self._dataset_repository = dataset_repository
        self._source_registry = source_registry
        self._ingestion_pipeline = ingestion_pipeline
        self._source_repository = source_repository
        self._embedding_client = embedding_client

    def ingest_pending_rows(
        self,
        *,
        batch_size: int,
        refresh_mode: SerbiaIngestionJobRefreshMode = "pending_only",
    ) -> SerbiaSourceIngestionSummary:
        """Ingest mirrored documents and metadata rows into the source store."""

        summary = SerbiaSourceIngestionSummary()
        doc_rows = self._dataset_repository.list_rows(
            mirror_statuses={"mirrored"},
            require_gcs_uri=True,
            has_source_id=False if refresh_mode == "pending_only" else None,
            limit=batch_size,
        )
        summary.scanned_rows += len(doc_rows)
        for row in doc_rows:
            result = self._ingest_document_row(row)
            summary.row_results.append(result)
            if result.status == "ingested_document":
                summary.ingested_document_rows += 1
            elif result.status == "failed":
                summary.failed_rows += 1
            else:
                summary.skipped_rows += 1

        structured_rows = self._dataset_repository.list_rows(
            require_gcs_uri=False,
            has_source_id=False if refresh_mode == "pending_only" else None,
            limit=batch_size,
        )
        summary.scanned_rows += len(structured_rows)
        for row in structured_rows:
            result = self._ingest_structured_row(row)
            summary.row_results.append(result)
            if result.status == "ingested_structured":
                summary.ingested_structured_rows += 1
            elif result.status == "failed":
                summary.failed_rows += 1
            else:
                summary.skipped_rows += 1

        return summary

    def ingest_row(
        self,
        *,
        dataset_family: SerbiaDatasetFamily,
        row_id: str,
        refresh_mode: SerbiaIngestionJobRefreshMode = "pending_only",
    ) -> SerbiaDatasetToSourceResult:
        """Ingest one specific dataset row into source/chunk storage."""

        row = self._dataset_repository.get_row(dataset_family=dataset_family, row_id=row_id)
        if row is None:
            raise ValueError(f"Serbia dataset row not found: {dataset_family}/{row_id}")
        if refresh_mode == "pending_only" and row.source_id:
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="skipped",
                source_id=row.source_id,
                source_type=FAMILY_SOURCE_TYPE_MAP[row.dataset_family],
                reason="Row already has a source_id.",
            )
        if row.gcs_uri and row.mirror_status == "mirrored":
            return self._ingest_document_row(row)
        return self._ingest_structured_row(row)

    def _ingest_document_row(self, row: SerbiaDatasetRow) -> SerbiaDatasetToSourceResult:
        """Register and ingest one mirrored document row."""

        if not row.gcs_uri:
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="skipped",
                reason="No GCS URI is available for document ingestion.",
            )

        source_type = FAMILY_SOURCE_TYPE_MAP[row.dataset_family]
        source_id = row.source_id or f"serbia-{row.dataset_family}-{row.id}"
        municipality_id = canonical_serbia_municipality_id(row.municipality_name)
        try:
            source = self._source_registry.register_source(
                source_type=source_type,
                title=row.title,
                uri=row.gcs_uri,
                source_id=source_id,
                source_url=row.source_url,
                document_url=row.resolved_document_url or row.gcs_uri,
                landing_page_url=row.landing_page_url,
                url_kind=row.url_kind,
                ingestion_readiness=row.ingestion_readiness,
                municipality_id=municipality_id,
                category=row.category,
                mime_type=row.document_mime_type,
            )
            self._ingestion_pipeline.ingest_source(source.source_id)
            self._dataset_repository.upsert_row(row.model_copy(update={"source_id": source.source_id}))
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="ingested_document",
                source_id=source.source_id,
                source_type=source_type,
            )
        except Exception as exc:
            self._dataset_repository.upsert_row(row.model_copy(update={"mirror_error": str(exc)}))
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="failed",
                source_id=source_id,
                source_type=source_type,
                reason=str(exc),
            )

    def _ingest_structured_row(self, row: SerbiaDatasetRow) -> SerbiaDatasetToSourceResult:
        """Ingest one row as structured metadata-first retrieval context."""

        source_type = FAMILY_SOURCE_TYPE_MAP[row.dataset_family]
        source_id = row.source_id or f"serbia-{row.dataset_family}-{row.id}"
        municipality_id = canonical_serbia_municipality_id(row.municipality_name)
        structured_uri = f"structured://serbia/{row.dataset_family}/{row.id}.json"
        text = _render_structured_text(row)
        if not text.strip():
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="skipped",
                source_id=source_id,
                source_type=source_type,
                reason="Structured text rendering produced empty content.",
            )

        try:
            source = self._source_registry.register_source(
                source_type=source_type,
                title=row.title,
                uri=structured_uri,
                source_id=source_id,
                source_url=row.source_url,
                document_url=row.resolved_document_url,
                landing_page_url=row.landing_page_url,
                url_kind=row.url_kind,
                ingestion_readiness=row.ingestion_readiness,
                municipality_id=municipality_id,
                category=row.category,
                mime_type="application/json",
            )
            embedding = self._embedding_client.embed_texts([text])[0]
            chunk = SourceChunk(
                chunk_id=f"{source.source_id}:0",
                source_id=source.source_id,
                chunk_index=0,
                text=text,
                body_text=text,
                header_text=f"structured-row | {row.dataset_family} | {row.title}",
                section_path=["serbia-dataset-row", row.dataset_family],
                token_count=max(1, len(re.findall(r"\S+", text))),
                embedding=embedding,
                embedding_model=self._embedding_client.model_name,
                semantic_group_id=0,
                municipality_id=source.municipality_id,
                category=source.category,
                source_type=source.source_type,
            )
            self._source_repository.replace_chunks(source.source_id, [chunk])
            self._dataset_repository.upsert_row(row.model_copy(update={"source_id": source.source_id}))
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="ingested_structured",
                source_id=source.source_id,
                source_type=source_type,
            )
        except Exception as exc:
            return SerbiaDatasetToSourceResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                status="failed",
                source_id=source_id,
                source_type=source_type,
                reason=str(exc),
            )


def _render_structured_text(row: SerbiaDatasetRow) -> str:
    """Render one dataset row into searchable structured text."""

    common_lines = [
        f"Dataset Family: {row.dataset_family}",
        f"Title: {row.title}",
    ]
    if row.country_name:
        common_lines.append(f"Country: {row.country_name}")
    if row.municipality_name:
        common_lines.append(f"Municipality: {row.municipality_name}")
    if row.district_name:
        common_lines.append(f"District: {row.district_name}")
    if row.region_name:
        common_lines.append(f"Region: {row.region_name}")
    if row.category:
        common_lines.append(f"Category: {row.category}")
    if row.sector:
        common_lines.append(f"Sector: {row.sector}")
    if row.project_code:
        common_lines.append(f"Project Code: {row.project_code}")
    if row.beneficiary_country:
        common_lines.append(f"Beneficiary Country: {row.beneficiary_country}")
    if row.beneficiary_body:
        common_lines.append(f"Beneficiary Body: {row.beneficiary_body}")
    if row.year_value:
        common_lines.append(f"Year: {row.year_value}")
    if row.source_url:
        common_lines.append(f"Source URL: {row.source_url}")
    if row.resolved_document_url:
        common_lines.append(f"Resolved Document URL: {row.resolved_document_url}")
    if row.landing_page_url:
        common_lines.append(f"Landing Page URL: {row.landing_page_url}")
    common_lines.append(f"URL Kind: {row.url_kind}")
    common_lines.append(f"Ingestion Readiness: {row.ingestion_readiness}")
    common_lines.append("Raw Payload:")
    for key, value in sorted(row.raw_payload.items()):
        common_lines.append(f"{key}: {value}")
    return "\n".join(common_lines).strip()
