from pathlib import Path

from src.embeddings.client import DeterministicEmbeddingClient
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.serbia_operational import (
    build_uri_resolution_index,
    canonical_serbia_municipality_id,
    ingest_serbia_context_bundle,
    resolve_document_candidate_uri,
)
from src.ingestion.source_registry import SourceRegistry
from src.schemas.serbia_context import (
    SerbiaCanonicalIngestionBundle,
    SerbiaDocumentRegistrationCandidate,
    SerbiaRecordProvenance,
    SerbiaStructuredContextRecord,
)
from src.storage.documents import LocalDocumentStore
from src.storage.sources import InMemorySourceRepository


def _document_candidate() -> SerbiaDocumentRegistrationCandidate:
    return SerbiaDocumentRegistrationCandidate(
        canonical_id="cand-1",
        source_family="municipal_development_plan",
        source_type="municipal_development_plan",
        title="Belgrade Local Development Plan",
        uri="https://example.org/municipal-plan",
        municipality_name="Belgrade",
        source_url="https://example.org/municipal-plan",
        document_url=None,
        landing_page_url="https://example.org/municipal-plan",
        url_kind="landing_page",
        ingestion_readiness="needs_resolver",
        municipality_id=None,
        category="Environment",
        normalized_metadata={},
    )


def test_canonical_municipality_mapping_handles_aliases_and_fallback() -> None:
    assert canonical_serbia_municipality_id("Niš") == "srb-nis"
    assert canonical_serbia_municipality_id("City of Belgrade") == "srb-belgrade"
    assert canonical_serbia_municipality_id("Nova Varoš") == "srb-nova-varos"


def test_document_candidate_resolution_supports_uploaded_uri_mapping() -> None:
    candidate = _document_candidate()
    resolution_index = build_uri_resolution_index(
        [
            {
                "canonical_id": candidate.canonical_id,
                "source_url": candidate.source_url or "",
                "resolved_uri": "/tmp/municipal-plan.pdf",
            }
        ]
    )

    assert resolve_document_candidate_uri(candidate, uri_resolution_index=resolution_index) == "/tmp/municipal-plan.pdf"


def test_operational_document_ingestion_registers_and_ingests_resolved_candidate(tmp_path: Path) -> None:
    local_document = tmp_path / "belgrade-plan.txt"
    local_document.write_text("Belgrade municipal development plan evidence.", encoding="utf-8")
    candidate = _document_candidate()
    bundle = SerbiaCanonicalIngestionBundle(
        records=[],
        document_registration_candidates=[candidate],
        structured_context_records=[],
        stats={},
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    ingestion_pipeline = IngestionPipeline(
        source_repository,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=LocalDocumentStore(),
    )

    report = ingest_serbia_context_bundle(
        bundle=bundle,
        source_registry=source_registry,
        ingestion_pipeline=ingestion_pipeline,
        source_repository=source_repository,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=LocalDocumentStore(),
        uri_resolution_map={candidate.canonical_id: str(local_document)},
        ingest_structured=False,
    )

    assert report.document_candidates_total == 1
    assert report.document_sources_registered == 1
    assert report.document_sources_ingested == 1
    assert report.document_candidates_failed == 0
    source = source_repository.get_source(candidate.canonical_id)
    assert source is not None
    assert source.uri == str(local_document)
    assert source_repository.list_chunks_for_source(source_id=candidate.canonical_id)


def test_operational_structured_ingestion_indexes_metadata_only_rows() -> None:
    structured_record = SerbiaStructuredContextRecord(
        canonical_id="structured-1",
        source_family="local_project_record",
        title="Nis Wastewater Upgrade",
        municipality_name="Niš",
        district_name=None,
        region_name="South Serbia",
        category_tags=["serbia", "local-project"],
        sector_tags=["environment", "water"],
        searchable_text="Nis wastewater project beneficiaries and financing context.",
        attributes={"project_code": "WB-TA-001", "beneficiaries": "City of Nis"},
        provenance=SerbiaRecordProvenance(
            source_file="serbia_lsg_projects.xlsx",
            source_sheet="Sheet1",
            source_row_number=2,
        ),
    )
    bundle = SerbiaCanonicalIngestionBundle(
        records=[],
        document_registration_candidates=[],
        structured_context_records=[structured_record],
        stats={},
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    ingestion_pipeline = IngestionPipeline(
        source_repository,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=LocalDocumentStore(),
    )
    report = ingest_serbia_context_bundle(
        bundle=bundle,
        source_registry=source_registry,
        ingestion_pipeline=ingestion_pipeline,
        source_repository=source_repository,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=LocalDocumentStore(),
        ingest_documents=False,
    )

    assert report.structured_records_total == 1
    assert report.structured_sources_upserted == 1
    assert report.structured_chunks_indexed == 1
    source = source_repository.get_source("serbia-structured-structured-1")
    assert source is not None
    assert source.municipality_id == "srb-nis"
    chunks = source_repository.list_chunks(municipality_id="srb-nis")
    assert len(chunks) == 1
    assert "project_code: WB-TA-001" in chunks[0].text
