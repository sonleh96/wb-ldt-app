"""Operational ingestion helpers for canonical Serbia context bundles."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from src.embeddings.client import EmbeddingClient
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.serbia_context import classify_url_kind
from src.ingestion.source_registry import SourceRegistry
from src.schemas.serbia_context import (
    SerbiaCanonicalIngestionBundle,
    SerbiaContextRecord,
    SerbiaDocumentIngestionResult,
    SerbiaDocumentRegistrationCandidate,
    SerbiaOperationalIngestionReport,
    SerbiaSourceFamily,
    SerbiaStructuredContextRecord,
)
from src.schemas.source_metadata import SourceChunk, SourceMetadata, SourceType
from src.storage.documents import DocumentStore
from src.storage.sources import SourceRepository


DEFAULT_MUNICIPALITY_ID_ALIASES: dict[str, str] = {
    "belgrade": "srb-belgrade",
    "beograd": "srb-belgrade",
    "grad beograd": "srb-belgrade",
    "nis": "srb-nis",
    "grad nis": "srb-nis",
}


def _normalize_alias_key(value: str) -> str:
    """Return a normalized key for municipality alias matching."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return normalized


def _slugify_ascii(value: str) -> str:
    """Return an ASCII slug for fallback municipality-id construction."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized


def canonical_serbia_municipality_id(
    municipality_name: str | None,
    *,
    aliases: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a canonical municipality id from a name with alias fallback."""

    name = (municipality_name or "").strip()
    if not name:
        return None

    alias_map: dict[str, str] = dict(DEFAULT_MUNICIPALITY_ID_ALIASES)
    if aliases:
        alias_map.update({_normalize_alias_key(key): value for key, value in aliases.items() if key and value})

    key = _normalize_alias_key(name)
    if key in alias_map:
        return alias_map[key]

    for prefix in ("city of ", "municipality of ", "grad ", "opstina "):
        if key.startswith(prefix):
            stripped = key[len(prefix) :].strip()
            if stripped in alias_map:
                return alias_map[stripped]
            key = stripped
            break

    slug = _slugify_ascii(key)
    if not slug:
        return None
    return f"srb-{slug}"


def build_uri_resolution_index(
    mapping_payload: Mapping[str, str] | list[dict[str, str]] | None,
) -> dict[str, str]:
    """Build a URI-resolution index from map or row-style mapping payloads."""

    index: dict[str, str] = {}
    if mapping_payload is None:
        return index

    if isinstance(mapping_payload, Mapping):
        for key, value in mapping_payload.items():
            normalized_key = str(key).strip()
            normalized_value = str(value).strip()
            if normalized_key and normalized_value:
                index[normalized_key] = normalized_value
        return index

    for row in mapping_payload:
        resolved_uri = str(row.get("resolved_uri") or row.get("uri") or "").strip()
        if not resolved_uri:
            continue
        for key_name in ("canonical_id", "source_url", "document_url", "landing_page_url", "original_url"):
            key = str(row.get(key_name) or "").strip()
            if key:
                index[key] = resolved_uri
    return index


def resolve_document_candidate_uri(
    candidate: SerbiaDocumentRegistrationCandidate,
    *,
    uri_resolution_index: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a candidate URI, using a mapping for non-direct source links."""

    index = uri_resolution_index or {}
    if candidate.ingestion_readiness == "ready" and candidate.uri.strip():
        return candidate.uri.strip()

    lookup_keys = [
        candidate.canonical_id,
        candidate.document_url,
        candidate.source_url,
        candidate.landing_page_url,
        candidate.uri,
    ]
    for key in lookup_keys:
        normalized = (key or "").strip()
        if not normalized:
            continue
        resolved = index.get(normalized)
        if resolved and resolved.strip():
            return resolved.strip()

    if candidate.uri.strip() and classify_url_kind(candidate.uri) == "direct_document":
        return candidate.uri.strip()
    return None


def _structured_source_type(source_family: SerbiaSourceFamily) -> SourceType:
    """Map a canonical Serbia family to an existing source type."""

    if source_family == "national_policy_document":
        return "policy_document"
    if source_family == "municipal_development_plan":
        return "municipal_development_plan"
    return "project_page"


def _category_from_tags(record: SerbiaContextRecord | SerbiaStructuredContextRecord) -> str | None:
    """Map normalized tags to retrieval categories used by request filters."""

    tags = [*(record.sector_tags or []), *(record.category_tags or [])]
    normalized = {_slugify_ascii(tag) for tag in tags if tag}
    if "environment" in normalized:
        return "Environment"
    if "transport" in normalized or "mobility" in normalized:
        return "Sustainable Transport"
    if "energy" in normalized:
        return "Energy"
    if "social" in normalized:
        return "Social"
    return None


def _render_structured_chunk_text(record: SerbiaStructuredContextRecord) -> str:
    """Render one structured record as a retrieval-friendly canonical text row."""

    lines = [
        f"Source Family: {record.source_family}",
        f"Title: {record.title}",
    ]
    if record.municipality_name:
        lines.append(f"Municipality: {record.municipality_name}")
    if record.district_name:
        lines.append(f"District: {record.district_name}")
    if record.region_name:
        lines.append(f"Region: {record.region_name}")
    if record.category_tags:
        lines.append(f"Category Tags: {', '.join(record.category_tags)}")
    if record.sector_tags:
        lines.append(f"Sector Tags: {', '.join(record.sector_tags)}")
    lines.append("Searchable Text:")
    lines.append(record.searchable_text)
    for key, value in sorted(record.attributes.items()):
        lines.append(f"{key}: {value}")
    return "\n".join(lines).strip()


def _estimate_token_count(text: str) -> int:
    """Estimate token count for lightweight structured context chunks."""

    return max(1, len(re.findall(r"\S+", text)))


def ingest_document_registration_candidates(
    *,
    candidates: list[SerbiaDocumentRegistrationCandidate],
    source_registry: SourceRegistry,
    ingestion_pipeline: IngestionPipeline,
    document_store: DocumentStore,
    uri_resolution_map: Mapping[str, str] | list[dict[str, str]] | None = None,
    municipality_id_aliases: Mapping[str, str] | None = None,
) -> SerbiaOperationalIngestionReport:
    """Register and ingest document candidates, with optional URI resolution."""

    report = SerbiaOperationalIngestionReport(document_candidates_total=len(candidates))
    resolution_index = build_uri_resolution_index(uri_resolution_map)

    for candidate in candidates:
        resolved_uri = resolve_document_candidate_uri(candidate, uri_resolution_index=resolution_index)
        if not resolved_uri:
            report.document_candidates_skipped_unresolved += 1
            report.document_results.append(
                SerbiaDocumentIngestionResult(
                    canonical_id=candidate.canonical_id,
                    status="skipped_unresolved",
                    reason="No resolvable URI for document candidate.",
                )
            )
            continue

        report.document_candidates_resolved += 1
        if not document_store.exists(resolved_uri):
            report.document_candidates_skipped_missing_uri += 1
            report.document_results.append(
                SerbiaDocumentIngestionResult(
                    canonical_id=candidate.canonical_id,
                    status="skipped_missing_uri",
                    resolved_uri=resolved_uri,
                    reason="Resolved URI does not exist in configured document store.",
                )
            )
            continue

        municipality_id = candidate.municipality_id or canonical_serbia_municipality_id(
            candidate.municipality_name,
            aliases=municipality_id_aliases,
        )
        resolved_kind = classify_url_kind(resolved_uri)

        try:
            registered = source_registry.register_source(
                source_type=candidate.source_type,
                title=candidate.title,
                uri=resolved_uri,
                source_url=candidate.source_url or candidate.uri,
                document_url=resolved_uri if resolved_kind in {"direct_document", "office_doc"} else candidate.document_url,
                landing_page_url=candidate.landing_page_url,
                url_kind=resolved_kind,
                ingestion_readiness="ready",
                municipality_id=municipality_id,
                category=candidate.category,
                source_id=candidate.canonical_id,
            )
            report.document_sources_registered += 1
            ingestion_pipeline.ingest_source(registered.source_id)
            report.document_sources_ingested += 1
            report.document_results.append(
                SerbiaDocumentIngestionResult(
                    canonical_id=candidate.canonical_id,
                    status="ingested",
                    source_id=registered.source_id,
                    resolved_uri=resolved_uri,
                )
            )
        except Exception as exc:  # pragma: no cover - guard path
            report.document_candidates_failed += 1
            report.document_results.append(
                SerbiaDocumentIngestionResult(
                    canonical_id=candidate.canonical_id,
                    status="failed",
                    resolved_uri=resolved_uri,
                    reason=str(exc),
                )
            )

    return report


def ingest_structured_context_records(
    *,
    records: list[SerbiaStructuredContextRecord],
    source_repository: SourceRepository,
    embedding_client: EmbeddingClient,
    municipality_id_aliases: Mapping[str, str] | None = None,
) -> tuple[int, int]:
    """Ingest metadata-first structured context records into source chunks."""

    if not records:
        return 0, 0

    rendered_texts = [_render_structured_chunk_text(record) for record in records]
    embeddings = embedding_client.embed_texts(rendered_texts)

    sources_upserted = 0
    chunks_indexed = 0
    for record, chunk_text, embedding in zip(records, rendered_texts, embeddings, strict=False):
        source_id = f"serbia-structured-{record.canonical_id}"
        source_type = _structured_source_type(record.source_family)
        municipality_id = canonical_serbia_municipality_id(
            record.municipality_name,
            aliases=municipality_id_aliases,
        )

        source = SourceMetadata(
            source_id=source_id,
            source_type=source_type,
            title=record.title,
            uri=f"structured://serbia-context/{record.canonical_id}.json",
            source_url=None,
            document_url=None,
            landing_page_url=None,
            url_kind="unknown",
            ingestion_readiness="metadata_only",
            municipality_id=municipality_id,
            category=_category_from_tags(record),
            mime_type="application/json",
            normalized_metadata={
                "source_family": record.source_family,
                "provenance_file": record.provenance.source_file,
                "provenance_row": str(record.provenance.source_row_number),
                "storage_backend": "structured",
            },
        )
        source_repository.upsert_source(source)
        sources_upserted += 1

        chunk = SourceChunk(
            chunk_id=f"{source_id}:0",
            source_id=source_id,
            chunk_index=0,
            text=chunk_text,
            body_text=chunk_text,
            header_text=f"{record.source_family} | {record.title}",
            section_path=["serbia-context", record.source_family],
            token_count=_estimate_token_count(chunk_text),
            embedding=embedding,
            embedding_model=embedding_client.model_name,
            semantic_group_id=0,
            municipality_id=municipality_id,
            category=source.category,
            source_type=source_type,
        )
        source_repository.replace_chunks(source_id, [chunk])
        chunks_indexed += 1

    return sources_upserted, chunks_indexed


def ingest_serbia_context_bundle(
    *,
    bundle: SerbiaCanonicalIngestionBundle,
    source_registry: SourceRegistry,
    ingestion_pipeline: IngestionPipeline,
    source_repository: SourceRepository,
    embedding_client: EmbeddingClient,
    document_store: DocumentStore,
    uri_resolution_map: Mapping[str, str] | list[dict[str, str]] | None = None,
    municipality_id_aliases: Mapping[str, str] | None = None,
    ingest_documents: bool = True,
    ingest_structured: bool = True,
) -> SerbiaOperationalIngestionReport:
    """Ingest a canonical bundle into document and structured retrieval stores."""

    report = SerbiaOperationalIngestionReport()

    if ingest_documents:
        document_report = ingest_document_registration_candidates(
            candidates=bundle.document_registration_candidates,
            source_registry=source_registry,
            ingestion_pipeline=ingestion_pipeline,
            document_store=document_store,
            uri_resolution_map=uri_resolution_map,
            municipality_id_aliases=municipality_id_aliases,
        )
        report = document_report.model_copy()
    else:
        report.document_candidates_total = len(bundle.document_registration_candidates)

    if ingest_structured:
        report.structured_records_total = len(bundle.structured_context_records)
        sources_upserted, chunks_indexed = ingest_structured_context_records(
            records=bundle.structured_context_records,
            source_repository=source_repository,
            embedding_client=embedding_client,
            municipality_id_aliases=municipality_id_aliases,
        )
        report.structured_sources_upserted = sources_upserted
        report.structured_chunks_indexed = chunks_indexed
    else:
        report.structured_records_total = len(bundle.structured_context_records)

    return report
