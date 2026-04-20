"""Typed schemas for canonical Serbia context ingestion records."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.source_metadata import SourceType


SerbiaSourceFamily = Literal[
    "national_policy_document",
    "municipal_development_plan",
    "local_project_record",
    "wbif_project_record",
    "wbif_ta_record",
]

SerbiaUrlKind = Literal[
    "direct_document",
    "landing_page",
    "cloud_drive",
    "office_doc",
    "archive",
    "unknown",
]

SerbiaIngestionReadiness = Literal[
    "ready",
    "needs_resolver",
    "metadata_only",
    "missing_url",
]

SerbiaOperationalDocumentStatus = Literal[
    "ingested",
    "skipped_unresolved",
    "skipped_missing_uri",
    "failed",
]


class SerbiaRecordProvenance(BaseModel):
    """Original dataset provenance for one canonical record."""

    source_file: str
    source_sheet: str | None = None
    source_row_number: int


class SerbiaContextRecord(BaseModel):
    """One normalized Serbia context record."""

    canonical_id: str
    source_family: SerbiaSourceFamily
    title: str
    display_title: str
    country_code: str = "SRB"
    country_name: str = "Serbia"
    municipality_name: str | None = None
    municipality_code: str | None = None
    district_name: str | None = None
    region_name: str | None = None
    category_tags: list[str] = Field(default_factory=list)
    sector_tags: list[str] = Field(default_factory=list)
    source_url: str | None = None
    document_url: str | None = None
    landing_page_url: str | None = None
    url_kind: SerbiaUrlKind = "unknown"
    ingestion_readiness: SerbiaIngestionReadiness
    provenance: SerbiaRecordProvenance
    summary_text: str
    attributes: dict[str, object] = Field(default_factory=dict)


class SerbiaDocumentRegistrationCandidate(BaseModel):
    """Candidate document registration derived from canonical records."""

    canonical_id: str
    source_family: SerbiaSourceFamily
    source_type: SourceType
    title: str
    uri: str
    municipality_name: str | None = None
    source_url: str | None = None
    document_url: str | None = None
    landing_page_url: str | None = None
    url_kind: SerbiaUrlKind
    ingestion_readiness: SerbiaIngestionReadiness
    municipality_id: str | None = None
    category: str | None = None
    normalized_metadata: dict[str, str] = Field(default_factory=dict)


class SerbiaStructuredContextRecord(BaseModel):
    """Row-oriented structured context prepared for embedding/RAG."""

    canonical_id: str
    source_family: SerbiaSourceFamily
    title: str
    municipality_name: str | None = None
    district_name: str | None = None
    region_name: str | None = None
    category_tags: list[str] = Field(default_factory=list)
    sector_tags: list[str] = Field(default_factory=list)
    searchable_text: str
    attributes: dict[str, object] = Field(default_factory=dict)
    provenance: SerbiaRecordProvenance


class SerbiaCanonicalIngestionBundle(BaseModel):
    """Canonical Serbia context output and derived ingestion views."""

    records: list[SerbiaContextRecord] = Field(default_factory=list)
    document_registration_candidates: list[SerbiaDocumentRegistrationCandidate] = Field(default_factory=list)
    structured_context_records: list[SerbiaStructuredContextRecord] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class SerbiaDocumentIngestionResult(BaseModel):
    """Status for one document candidate in operational ingestion."""

    canonical_id: str
    status: SerbiaOperationalDocumentStatus
    source_id: str | None = None
    resolved_uri: str | None = None
    reason: str | None = None


class SerbiaOperationalIngestionReport(BaseModel):
    """Operational ingestion summary for canonical Serbia bundles."""

    document_candidates_total: int = 0
    document_candidates_resolved: int = 0
    document_sources_registered: int = 0
    document_sources_ingested: int = 0
    document_candidates_skipped_unresolved: int = 0
    document_candidates_skipped_missing_uri: int = 0
    document_candidates_failed: int = 0
    structured_records_total: int = 0
    structured_sources_upserted: int = 0
    structured_chunks_indexed: int = 0
    document_results: list[SerbiaDocumentIngestionResult] = Field(default_factory=list)
