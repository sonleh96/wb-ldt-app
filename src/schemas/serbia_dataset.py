"""Typed contracts for Serbia dataset storage and staged ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.source_metadata import SourceType


def utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


SerbiaDatasetFamily = Literal[
    "serbia_national_documents",
    "serbia_municipal_development_plans",
    "serbia_lsg_projects",
    "serbia_wbif_projects",
    "serbia_wbif_tas",
]

SerbiaDatasetUrlKind = Literal[
    "direct_document",
    "landing_page",
    "cloud_drive",
    "office_doc",
    "archive",
    "unknown",
]

SerbiaDatasetIngestionReadiness = Literal[
    "ready",
    "needs_resolver",
    "metadata_only",
    "missing_url",
]

SerbiaDatasetMirrorStatus = Literal[
    "not_started",
    "skipped",
    "mirrored",
    "failed",
]

SerbiaIngestionJobRefreshMode = Literal[
    "pending_only",
    "force_refresh",
]

SerbiaDatasetToSourceStatus = Literal[
    "ingested_document",
    "ingested_structured",
    "skipped",
    "failed",
]


class SerbiaDatasetRow(BaseModel):
    """One normalized Serbia dataset row stored in SQL tables."""

    id: str
    dataset_family: SerbiaDatasetFamily
    dataset_name: str
    source_file_name: str
    source_row_number: int
    title: str
    country_code: str = "SRB"
    country_name: str = "Serbia"
    municipality_name: str | None = None
    municipality_code: str | None = None
    district_name: str | None = None
    region_name: str | None = None
    beneficiary_country: str | None = None
    beneficiary_body: str | None = None
    project_code: str | None = None
    sector: str | None = None
    category: str | None = None
    year_value: int | None = None
    source_url: str | None = None
    resolved_document_url: str | None = None
    landing_page_url: str | None = None
    url_kind: SerbiaDatasetUrlKind = "unknown"
    ingestion_readiness: SerbiaDatasetIngestionReadiness
    mirror_status: SerbiaDatasetMirrorStatus = "not_started"
    mirror_error: str | None = None
    gcs_uri: str | None = None
    source_id: str | None = None
    document_checksum_sha256: str | None = None
    document_size_bytes: int | None = None
    document_mime_type: str | None = None
    raw_payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SerbiaDatasetLoadSummary(BaseModel):
    """Summary for the raw-dataset load stage."""

    total_rows: int = 0
    family_counts: dict[SerbiaDatasetFamily, int] = Field(default_factory=dict)


class SerbiaDocumentMirrorRowResult(BaseModel):
    """Per-row mirror result details."""

    dataset_family: SerbiaDatasetFamily
    row_id: str
    mirror_status: SerbiaDatasetMirrorStatus
    resolved_document_url: str | None = None
    gcs_uri: str | None = None
    error: str | None = None


class SerbiaDocumentMirrorSummary(BaseModel):
    """Summary for the document mirroring stage."""

    scanned_rows: int = 0
    mirrored_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    row_results: list[SerbiaDocumentMirrorRowResult] = Field(default_factory=list)


class SerbiaDatasetToSourceResult(BaseModel):
    """Per-row registration/ingestion result from dataset rows to sources."""

    dataset_family: SerbiaDatasetFamily
    row_id: str
    status: SerbiaDatasetToSourceStatus
    source_id: str | None = None
    source_type: SourceType | None = None
    reason: str | None = None


class SerbiaSourceIngestionSummary(BaseModel):
    """Summary for the source-registration and embedding ingestion stage."""

    scanned_rows: int = 0
    ingested_document_rows: int = 0
    ingested_structured_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    cleared_source_ids: int = 0
    deleted_existing_sources: int = 0
    placeholder_chunks_remaining: int = 0
    row_results: list[SerbiaDatasetToSourceResult] = Field(default_factory=list)
