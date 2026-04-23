from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.embeddings.client import DeterministicEmbeddingClient
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.source_registry import SourceRegistry
from src.retrieval.context_windows import RetrievalContextWindowExpander
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.lexical import LexicalRetriever
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.service import RetrievalService
from src.schemas.serbia_dataset import SerbiaDatasetRow
from src.schemas.source_metadata import SourceChunk
from src.services.serbia_dataset_loader import SerbiaDatasetLoaderService
from src.services.serbia_document_mirror import FetchedDocument, SerbiaDocumentMirrorService
from src.services.serbia_source_ingestion import SerbiaSourceIngestionService
from src.storage.serbia_datasets import InMemorySerbiaDatasetRepository
from src.storage.sources import InMemorySourceRepository


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


class FakeFetcher:
    def __init__(self, documents: dict[str, FetchedDocument], html_pages: dict[str, str] | None = None) -> None:
        self._documents = documents
        self._html_pages = html_pages or {}

    def fetch_document(self, url: str, *, timeout_seconds: int, max_retries: int) -> FetchedDocument:
        if url not in self._documents:
            raise RuntimeError(f"not found: {url}")
        return self._documents[url]

    def fetch_text(self, url: str, *, timeout_seconds: int, max_retries: int) -> str:
        return self._html_pages.get(url, "<html></html>")


class FakeMirrorObjectStore:
    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    def upload_bytes(self, *, object_name: str, content: bytes, content_type: str | None) -> str:
        self.uploaded[object_name] = content
        return f"gs://test-bucket/{object_name}"


class FakeRemoteDocumentStore:
    def __init__(self, mapping: dict[str, Path]) -> None:
        self._mapping = mapping

    def exists(self, uri: str) -> bool:
        return uri in self._mapping

    @contextmanager
    def as_local_path(self, uri: str) -> Iterator[Path]:
        yield self._mapping[uri]


def test_loader_parses_all_five_files_and_keeps_serbia_filters_deterministic() -> None:
    repository = InMemorySerbiaDatasetRepository()
    loader = SerbiaDatasetLoaderService(repository=repository)
    summary = loader.load_from_data_dir(_data_dir())

    assert summary.total_rows == 408
    assert summary.family_counts["serbia_national_documents"] == 24
    assert summary.family_counts["serbia_municipal_development_plans"] == 161
    assert summary.family_counts["serbia_lsg_projects"] == 107
    assert summary.family_counts["serbia_wbif_projects"] == 77
    assert summary.family_counts["serbia_wbif_tas"] == 39

    municipal_rows = repository.list_rows(dataset_families={"serbia_municipal_development_plans"})
    missing_links = [row for row in municipal_rows if row.ingestion_readiness == "missing_url"]
    assert len(missing_links) == 10


def test_mirror_stage_mirrors_direct_document_to_gcs_and_updates_row_metadata() -> None:
    repository = InMemorySerbiaDatasetRepository()
    row = SerbiaDatasetRow(
        id="row-1",
        dataset_family="serbia_national_documents",
        dataset_name="serbia_national_documents",
        source_file_name="national_strategy_policies_law.xlsx",
        source_row_number=2,
        title="Air Quality Law",
        source_url="https://example.org/air-quality-law.pdf",
        resolved_document_url=None,
        landing_page_url=None,
        url_kind="direct_document",
        ingestion_readiness="ready",
        mirror_status="not_started",
        raw_payload={},
    )
    repository.upsert_row(row)

    mirror = SerbiaDocumentMirrorService(
        repository=repository,
        fetcher=FakeFetcher(
            {
                "https://example.org/air-quality-law.pdf": FetchedDocument(
                    content=b"%PDF-1.4 fake content",
                    final_url="https://example.org/air-quality-law.pdf",
                    mime_type="application/pdf",
                )
            }
        ),
        object_store=FakeMirrorObjectStore(),
        gcs_prefix="ldt/sources",
        timeout_seconds=10,
        max_retries=0,
    )
    summary = mirror.mirror_pending_rows(batch_size=10)

    assert summary.mirrored_rows == 1
    stored = repository.get_row(dataset_family="serbia_national_documents", row_id="row-1")
    assert stored is not None
    assert stored.mirror_status == "mirrored"
    assert stored.gcs_uri and stored.gcs_uri.startswith("gs://test-bucket/ldt/sources/national/srb/")
    assert stored.document_checksum_sha256
    assert stored.document_size_bytes == len(b"%PDF-1.4 fake content")


def test_mirror_stage_leaves_unresolved_landing_page_as_needs_resolver_and_not_failed() -> None:
    repository = InMemorySerbiaDatasetRepository()
    row = SerbiaDatasetRow(
        id="row-landing",
        dataset_family="serbia_wbif_projects",
        dataset_name="serbia_wbif_projects",
        source_file_name="wbif_projects.csv",
        source_row_number=5,
        title="WBIF Project Landing",
        source_url="https://example.org/project-detail/123",
        landing_page_url="https://example.org/project-detail/123",
        url_kind="landing_page",
        ingestion_readiness="needs_resolver",
        mirror_status="not_started",
        raw_payload={},
    )
    repository.upsert_row(row)
    mirror = SerbiaDocumentMirrorService(
        repository=repository,
        fetcher=FakeFetcher(documents={}, html_pages={"https://example.org/project-detail/123": "<html>No file</html>"}),
        object_store=FakeMirrorObjectStore(),
        gcs_prefix="ldt/sources",
        timeout_seconds=10,
        max_retries=0,
    )
    summary = mirror.mirror_pending_rows(batch_size=10)

    assert summary.skipped_rows == 1
    stored = repository.get_row(dataset_family="serbia_wbif_projects", row_id="row-landing")
    assert stored is not None
    assert stored.mirror_status == "skipped"
    assert stored.ingestion_readiness == "needs_resolver"


def test_mirror_stage_marks_failed_when_direct_url_download_errors() -> None:
    repository = InMemorySerbiaDatasetRepository()
    row = SerbiaDatasetRow(
        id="row-fail",
        dataset_family="serbia_national_documents",
        dataset_name="serbia_national_documents",
        source_file_name="national_strategy_policies_law.xlsx",
        source_row_number=3,
        title="Missing Law",
        source_url="https://example.org/missing.pdf",
        url_kind="direct_document",
        ingestion_readiness="ready",
        mirror_status="not_started",
        raw_payload={},
    )
    repository.upsert_row(row)
    mirror = SerbiaDocumentMirrorService(
        repository=repository,
        fetcher=FakeFetcher(documents={}),
        object_store=FakeMirrorObjectStore(),
        gcs_prefix="ldt/sources",
        timeout_seconds=10,
        max_retries=0,
    )
    summary = mirror.mirror_pending_rows(batch_size=10)

    assert summary.failed_rows == 1
    stored = repository.get_row(dataset_family="serbia_national_documents", row_id="row-fail")
    assert stored is not None
    assert stored.mirror_status == "failed"
    assert stored.mirror_error


def test_mirror_pending_only_prioritizes_not_started_and_reserves_national_rows() -> None:
    repository = InMemorySerbiaDatasetRepository()
    documents: dict[str, FetchedDocument] = {}

    for idx in range(8):
        url = f"https://example.org/national-{idx}.pdf"
        repository.upsert_row(
            SerbiaDatasetRow(
                id=f"national-{idx}",
                dataset_family="serbia_national_documents",
                dataset_name="serbia_national_documents",
                source_file_name="national_strategy_policies_law.xlsx",
                source_row_number=idx + 2,
                title=f"National Row {idx}",
                source_url=url,
                url_kind="direct_document",
                ingestion_readiness="ready",
                mirror_status="not_started",
                raw_payload={},
            )
        )
        documents[url] = FetchedDocument(
            content=f"national-{idx}".encode("utf-8"),
            final_url=url,
            mime_type="application/pdf",
        )

    for idx in range(8):
        url = f"https://example.org/municipal-failed-{idx}.pdf"
        repository.upsert_row(
            SerbiaDatasetRow(
                id=f"municipal-failed-{idx}",
                dataset_family="serbia_municipal_development_plans",
                dataset_name="serbia_municipal_development_plans",
                source_file_name="serbia_local_dev_plans_final.csv",
                source_row_number=idx + 2,
                title=f"Municipal Failed Row {idx}",
                municipality_name="Belgrade",
                source_url=url,
                url_kind="direct_document",
                ingestion_readiness="ready",
                mirror_status="failed",
                raw_payload={},
            )
        )
        documents[url] = FetchedDocument(
            content=f"municipal-{idx}".encode("utf-8"),
            final_url=url,
            mime_type="application/pdf",
        )

    mirror = SerbiaDocumentMirrorService(
        repository=repository,
        fetcher=FakeFetcher(documents=documents),
        object_store=FakeMirrorObjectStore(),
        gcs_prefix="ldt/sources",
        timeout_seconds=10,
        max_retries=0,
    )
    summary = mirror.mirror_pending_rows(batch_size=8)

    assert summary.scanned_rows == 8
    assert summary.mirrored_rows == 8
    mirrored_national = repository.list_rows(
        dataset_families={"serbia_national_documents"},
        mirror_statuses={"mirrored"},
    )
    assert len(mirrored_national) == 8
    still_failed_municipal = repository.list_rows(
        dataset_families={"serbia_municipal_development_plans"},
        mirror_statuses={"failed"},
    )
    assert len(still_failed_municipal) == 8


def test_source_ingestion_backfills_source_id_and_indexes_document_and_structured_rows(tmp_path: Path) -> None:
    document_path = tmp_path / "belgrade-plan.txt"
    document_path.write_text("Belgrade municipal development plan for environment.", encoding="utf-8")
    gcs_uri = "gs://test-bucket/ldt/sources/municipal/srb-belgrade/environment/2024/plan__txt"

    dataset_repository = InMemorySerbiaDatasetRepository()
    dataset_repository.upsert_row(
        SerbiaDatasetRow(
            id="doc-row",
            dataset_family="serbia_municipal_development_plans",
            dataset_name="serbia_municipal_development_plans",
            source_file_name="serbia_local_dev_plans_final.csv",
            source_row_number=20,
            title="Belgrade Development Plan",
            municipality_name="Belgrade",
            district_name="Belgrade District",
            category="Environment",
            source_url="https://example.org/belgrade-plan.pdf",
            resolved_document_url="https://example.org/belgrade-plan.pdf",
            url_kind="direct_document",
            ingestion_readiness="ready",
            mirror_status="mirrored",
            gcs_uri=gcs_uri,
            raw_payload={},
        )
    )
    dataset_repository.upsert_row(
        SerbiaDatasetRow(
            id="structured-row",
            dataset_family="serbia_wbif_tas",
            dataset_name="serbia_wbif_tas",
            source_file_name="wbif_TAs.csv",
            source_row_number=10,
            title="TA Program for Serbia Rail",
            project_code="WBIF-TA-01",
            beneficiary_country="Serbia",
            sector="transport",
            category="Sustainable Transport",
            source_url="https://example.org/project-detail/ta-1",
            landing_page_url="https://example.org/project-detail/ta-1",
            url_kind="landing_page",
            ingestion_readiness="needs_resolver",
            mirror_status="skipped",
            raw_payload={"description": "Rail modernization support"},
        )
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    ingestion_pipeline = IngestionPipeline(
        source_repository,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=FakeRemoteDocumentStore({gcs_uri: document_path}),
    )
    service = SerbiaSourceIngestionService(
        dataset_repository=dataset_repository,
        source_registry=source_registry,
        ingestion_pipeline=ingestion_pipeline,
        source_repository=source_repository,
        embedding_client=DeterministicEmbeddingClient(),
    )
    summary = service.ingest_pending_rows(batch_size=50)

    assert summary.ingested_document_rows == 1
    assert summary.ingested_structured_rows >= 1
    stored_doc = dataset_repository.get_row(
        dataset_family="serbia_municipal_development_plans",
        row_id="doc-row",
    )
    assert stored_doc is not None and stored_doc.source_id
    doc_chunks = source_repository.list_chunks_for_source(source_id=stored_doc.source_id)
    assert doc_chunks and doc_chunks[0].embedding

    stored_structured = dataset_repository.get_row(
        dataset_family="serbia_wbif_tas",
        row_id="structured-row",
    )
    assert stored_structured is not None and stored_structured.source_id
    structured_chunks = source_repository.list_chunks_for_source(source_id=stored_structured.source_id)
    assert structured_chunks and "Project Code: WBIF-TA-01" in structured_chunks[0].text


def test_retrieval_can_find_municipal_document_and_structured_wbif_context(tmp_path: Path) -> None:
    document_path = tmp_path / "municipal.txt"
    document_path.write_text("Belgrade municipality environment action plan and waste policy.", encoding="utf-8")
    gcs_uri = "gs://test-bucket/ldt/sources/municipal/srb-belgrade/environment/2024/plan__txt"

    dataset_repository = InMemorySerbiaDatasetRepository()
    dataset_repository.upsert_row(
        SerbiaDatasetRow(
            id="doc-2",
            dataset_family="serbia_municipal_development_plans",
            dataset_name="serbia_municipal_development_plans",
            source_file_name="serbia_local_dev_plans_final.csv",
            source_row_number=30,
            title="Belgrade Environment Plan",
            municipality_name="Belgrade",
            category="Environment",
            source_url="https://example.org/belgrade-environment-plan.pdf",
            resolved_document_url="https://example.org/belgrade-environment-plan.pdf",
            url_kind="direct_document",
            ingestion_readiness="ready",
            mirror_status="mirrored",
            gcs_uri=gcs_uri,
            raw_payload={},
        )
    )
    dataset_repository.upsert_row(
        SerbiaDatasetRow(
            id="wbif-1",
            dataset_family="serbia_wbif_projects",
            dataset_name="serbia_wbif_projects",
            source_file_name="wbif_projects.csv",
            source_row_number=15,
            title="Serbia Rail Corridor Upgrade",
            project_code="WBIF-PRJ-001",
            beneficiary_country="Serbia",
            sector="transport",
            category="Sustainable Transport",
            source_url="https://example.org/project-detail/wbif-1",
            landing_page_url="https://example.org/project-detail/wbif-1",
            url_kind="landing_page",
            ingestion_readiness="needs_resolver",
            mirror_status="skipped",
            raw_payload={"benefits": "Freight capacity increase"},
        )
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    embedding_client = DeterministicEmbeddingClient()
    ingestion_pipeline = IngestionPipeline(
        source_repository,
        embedding_client=embedding_client,
        document_store=FakeRemoteDocumentStore({gcs_uri: document_path}),
    )
    service = SerbiaSourceIngestionService(
        dataset_repository=dataset_repository,
        source_registry=source_registry,
        ingestion_pipeline=ingestion_pipeline,
        source_repository=source_repository,
        embedding_client=embedding_client,
    )
    summary = service.ingest_pending_rows(batch_size=50)
    assert summary.ingested_document_rows == 1
    assert summary.ingested_structured_rows >= 1
    stored_doc = dataset_repository.get_row(
        dataset_family="serbia_municipal_development_plans",
        row_id="doc-2",
    )
    stored_wbif = dataset_repository.get_row(
        dataset_family="serbia_wbif_projects",
        row_id="wbif-1",
    )
    assert stored_doc is not None and stored_doc.source_id
    assert stored_wbif is not None and stored_wbif.source_id

    retrieval = RetrievalService(
        semantic_retriever=SemanticRetriever(source_repository, embedding_client),
        lexical_retriever=LexicalRetriever(source_repository),
        hybrid_retriever=HybridRetriever(
            lexical_retriever=LexicalRetriever(source_repository),
            semantic_retriever=SemanticRetriever(source_repository, embedding_client),
        ),
        context_window_expander=RetrievalContextWindowExpander(source_repository, neighbor_window=0),
    )
    municipal = retrieval.search(
        query="Belgrade municipal environment plan",
        mode="lexical",
        top_k=5,
        municipality_id="srb-belgrade",
        category="Environment",
    )
    wbif = retrieval.search(
        query="WBIF-PRJ-001 Serbia Rail Corridor Upgrade",
        mode="hybrid",
        top_k=5,
        municipality_id=None,
        category="Sustainable Transport",
    )

    assert municipal.total_results > 0
    assert any(item.source_id == stored_doc.source_id for item in municipal.results)
    assert wbif.total_results > 0
    assert any(item.source_id == stored_wbif.source_id for item in wbif.results)


def test_pipeline_idempotency_prevents_duplicate_rows_mirrors_and_sources(tmp_path: Path) -> None:
    repository = InMemorySerbiaDatasetRepository()
    loader = SerbiaDatasetLoaderService(repository=repository)
    first = loader.load_from_data_dir(_data_dir())
    second = loader.load_from_data_dir(_data_dir())
    assert first.total_rows == second.total_rows
    assert len(repository.list_rows()) == 408

    document_url = "https://example.org/policy.pdf"
    doc_row = SerbiaDatasetRow(
        id="idempotent-doc",
        dataset_family="serbia_national_documents",
        dataset_name="serbia_national_documents",
        source_file_name="national_strategy_policies_law.xlsx",
        source_row_number=1,
        title="Idempotent Policy",
        source_url=document_url,
        url_kind="direct_document",
        ingestion_readiness="ready",
        mirror_status="not_started",
        raw_payload={},
    )
    repository.upsert_row(doc_row)
    object_store = FakeMirrorObjectStore()
    mirror = SerbiaDocumentMirrorService(
        repository=repository,
        fetcher=FakeFetcher(
            {
                document_url: FetchedDocument(
                    content=b"idempotent",
                    final_url=document_url,
                    mime_type="application/pdf",
                )
            }
        ),
        object_store=object_store,
        gcs_prefix="ldt/sources",
        timeout_seconds=10,
        max_retries=0,
    )
    first_mirror = mirror.mirror_pending_rows(batch_size=10)
    second_mirror = mirror.mirror_pending_rows(batch_size=10)
    assert first_mirror.mirrored_rows == 1
    assert second_mirror.mirrored_rows == 0
    assert len(object_store.uploaded) == 1

    stored = repository.get_row(dataset_family="serbia_national_documents", row_id="idempotent-doc")
    assert stored is not None and stored.gcs_uri
    local_file = tmp_path / "idempotent.txt"
    local_file.write_text("idempotent document text", encoding="utf-8")

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    service = SerbiaSourceIngestionService(
        dataset_repository=repository,
        source_registry=source_registry,
        ingestion_pipeline=IngestionPipeline(
            source_repository,
            embedding_client=DeterministicEmbeddingClient(),
            document_store=FakeRemoteDocumentStore({stored.gcs_uri: local_file}),
        ),
        source_repository=source_repository,
        embedding_client=DeterministicEmbeddingClient(),
    )
    first_ingest = service.ingest_pending_rows(batch_size=20)
    second_ingest = service.ingest_pending_rows(batch_size=20)
    assert first_ingest.ingested_document_rows >= 1
    assert second_ingest.ingested_document_rows == 0
    assert len(source_repository.list_sources()) >= 1


def test_document_ingestion_falls_back_to_structured_chunk_when_parser_is_unsupported(tmp_path: Path) -> None:
    gcs_uri = "gs://test-bucket/ldt/sources/national/srb/general/unknown/parser-gap__bin"
    opaque_path = tmp_path / "parser-gap"
    opaque_path.write_bytes(b"\x00\x01\x02\x03\x04")

    dataset_repository = InMemorySerbiaDatasetRepository()
    dataset_repository.upsert_row(
        SerbiaDatasetRow(
            id="parser-gap-row",
            dataset_family="serbia_national_documents",
            dataset_name="serbia_national_documents",
            source_file_name="national_strategy_policies_law.xlsx",
            source_row_number=7,
            title="Parser Gap Policy",
            category="Environment",
            source_url="https://example.org/parser-gap",
            resolved_document_url="https://example.org/parser-gap",
            url_kind="direct_document",
            ingestion_readiness="ready",
            mirror_status="mirrored",
            gcs_uri=gcs_uri,
            document_mime_type="application/octet-stream",
            raw_payload={"note": "No parser available"},
        )
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    service = SerbiaSourceIngestionService(
        dataset_repository=dataset_repository,
        source_registry=source_registry,
        ingestion_pipeline=IngestionPipeline(
            source_repository,
            embedding_client=DeterministicEmbeddingClient(),
            document_store=FakeRemoteDocumentStore({gcs_uri: opaque_path}),
        ),
        source_repository=source_repository,
        embedding_client=DeterministicEmbeddingClient(),
    )

    summary = service.ingest_pending_rows(batch_size=10, refresh_mode="force_refresh")

    assert summary.ingested_document_rows == 0
    assert summary.ingested_structured_rows == 1
    assert summary.failed_rows == 0
    assert summary.row_results and summary.row_results[0].status == "ingested_structured"

    stored = dataset_repository.get_row(
        dataset_family="serbia_national_documents",
        row_id="parser-gap-row",
    )
    assert stored is not None and stored.source_id
    chunks = source_repository.list_chunks_for_source(source_id=stored.source_id)
    assert chunks
    assert "Dataset Family: serbia_national_documents" in chunks[0].text
    assert "Unsupported parser for" not in chunks[0].text


def test_rebuild_all_rows_deletes_stale_serbia_chunks_and_reingests_clean_content(tmp_path: Path) -> None:
    gcs_uri = "gs://test-bucket/ldt/sources/municipal/test/general/unknown/rebuild-plan__txt"
    local_path = tmp_path / "rebuild-plan.txt"
    local_path.write_text("Fresh rebuilt municipal content for retrieval.", encoding="utf-8")

    dataset_repository = InMemorySerbiaDatasetRepository()
    dataset_repository.upsert_row(
        SerbiaDatasetRow(
            id="rebuild-row",
            dataset_family="serbia_municipal_development_plans",
            dataset_name="serbia_municipal_development_plans",
            source_file_name="serbia_local_dev_plans_final.csv",
            source_row_number=10,
            title="Rebuild Municipal Plan",
            municipality_name="Uzice",
            source_url="https://example.org/rebuild-plan.txt",
            resolved_document_url="https://example.org/rebuild-plan.txt",
            url_kind="direct_document",
            ingestion_readiness="ready",
            mirror_status="mirrored",
            gcs_uri=gcs_uri,
            source_id="serbia-serbia_municipal_development_plans-rebuild-row",
            document_mime_type="text/plain",
            raw_payload={"note": "stale placeholder should be removed"},
        )
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    stale_source = source_registry.register_source(
        source_type="municipal_development_plan",
        title="Rebuild Municipal Plan",
        uri=gcs_uri,
        source_id="serbia-serbia_municipal_development_plans-rebuild-row",
        municipality_id="srb-uzice",
        category="Development",
        mime_type="text/plain",
    )
    source_repository.replace_chunks(
        stale_source.source_id,
        [
            SourceChunk(
                chunk_id=f"{stale_source.source_id}:0",
                source_id=stale_source.source_id,
                chunk_index=0,
                text="Document Title: Rebuild Municipal Plan\nUnsupported parser for rebuild-plan__txt. Binary size: 7 bytes.",
                token_count=12,
                embedding=[0.1, 0.2, 0.3],
                embedding_model="deterministic",
                municipality_id="srb-uzice",
                category="Development",
                source_type="municipal_development_plan",
            )
        ],
    )

    service = SerbiaSourceIngestionService(
        dataset_repository=dataset_repository,
        source_registry=source_registry,
        ingestion_pipeline=IngestionPipeline(
            source_repository,
            embedding_client=DeterministicEmbeddingClient(),
            document_store=FakeRemoteDocumentStore({gcs_uri: local_path}),
        ),
        source_repository=source_repository,
        embedding_client=DeterministicEmbeddingClient(),
    )

    summary = service.rebuild_all_rows(batch_size=10)

    assert summary.cleared_source_ids == 1
    assert summary.deleted_existing_sources == 1
    assert summary.placeholder_chunks_remaining == 0
    assert summary.ingested_document_rows == 1

    chunks = source_repository.list_chunks_for_source(source_id=stale_source.source_id)
    assert len(chunks) >= 1
    assert all("Unsupported parser for" not in chunk.text for chunk in chunks)
    assert "Fresh rebuilt municipal content for retrieval." in chunks[0].text
