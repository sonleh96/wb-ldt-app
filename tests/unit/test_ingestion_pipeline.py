from pathlib import Path
from typing import Iterator
import zipfile

import pytest
from contextlib import contextmanager

from src.embeddings.client import DeterministicEmbeddingClient
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.source_registry import SourceRegistry
from src.storage.sources import InMemorySourceRepository


class FakeRemoteDocumentStore:
    def __init__(self, mapping: dict[str, Path]) -> None:
        self._mapping = mapping

    def exists(self, uri: str) -> bool:
        return uri in self._mapping

    @contextmanager
    def as_local_path(self, uri: str) -> Iterator[Path]:
        yield self._mapping[uri]


def test_ingestion_pipeline_parses_csv_and_creates_chunks() -> None:
    base_dir = Path(__file__).resolve().parents[2] / ".test-artifacts"
    base_dir.mkdir(exist_ok=True)
    csv_path = base_dir / "sample-ingestion-pipeline.csv"
    csv_path.write_text("col1,col2\nalpha,beta\ngamma,delta\n", encoding="utf-8")

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(source_repo, embedding_client=DeterministicEmbeddingClient())

    source = registry.register_source(
        source_type="dataset",
        title="Sample CSV",
        uri=str(csv_path),
        municipality_id="srb-belgrade",
        category="Environment",
    )

    result = pipeline.ingest_source(source.source_id)

    assert result.parser_used == "csv_parser"
    assert result.chunk_count > 0
    chunks = source_repo.list_chunks(municipality_id="srb-belgrade", category="Environment")
    assert chunks
    assert all(chunk.embedding for chunk in chunks)
    assert all(chunk.header_text for chunk in chunks)
    assert all(chunk.body_text for chunk in chunks)
    combined_body = "\n".join(chunk.body_text or "" for chunk in chunks)
    assert "Dataset Columns: col1, col2" in combined_body
    assert "### Row 1" in combined_body
    assert "col1: alpha" in combined_body
    assert "col2: beta" in combined_body


def test_ingestion_pipeline_uses_pdf_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = Path(__file__).resolve().parents[2] / ".test-artifacts"
    base_dir.mkdir(exist_ok=True)
    pdf_path = base_dir / "sample-ingestion-pipeline.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content")

    monkeypatch.setattr(
        "src.ingestion.pipeline.parse_pdf_to_markdown",
        lambda path: "# PDF Title\n\nPolicy content from PDF parser.",
    )

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(source_repo, embedding_client=DeterministicEmbeddingClient())

    source = registry.register_source(
        source_type="policy_document",
        title="Sample PDF",
        uri=str(pdf_path),
        municipality_id="srb-belgrade",
        category="Environment",
    )

    result = pipeline.ingest_source(source.source_id)

    assert result.parser_used == "pymupdf4llm_markdown_parser"
    assert result.chunk_count > 0


def test_ingestion_pipeline_uses_docx_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = Path(__file__).resolve().parents[2] / ".test-artifacts"
    base_dir.mkdir(exist_ok=True)
    docx_path = base_dir / "sample-ingestion-pipeline.docx"
    docx_path.write_bytes(b"fake docx content")

    monkeypatch.setattr(
        "src.ingestion.pipeline.parse_docx_to_markdownish",
        lambda path: "# DOCX Title\n\nTraining material body from DOCX parser.",
    )

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(source_repo, embedding_client=DeterministicEmbeddingClient())

    source = registry.register_source(
        source_type="project_document",
        title="Sample DOCX",
        uri=str(docx_path),
        municipality_id="srb-belgrade",
        category="Environment",
    )

    result = pipeline.ingest_source(source.source_id)

    assert result.parser_used == "mammoth_docx_parser"
    assert result.chunk_count > 0


def test_ingestion_pipeline_parses_gcs_uri_through_document_store(tmp_path: Path) -> None:
    local_copy = tmp_path / "remote-source.txt"
    local_copy.write_text("Belgrade local policy evidence for air quality.", encoding="utf-8")
    gcs_uri = "gs://ldt-documents/ldt/sources/municipal/srb-belgrade/environment/2024/remote-source__en__2024__v1.txt"

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(
        source_repo,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=FakeRemoteDocumentStore({gcs_uri: local_copy}),
    )

    source = registry.register_source(
        source_type="policy_document",
        title="Remote Source",
        uri=gcs_uri,
        municipality_id="srb-belgrade",
        category="Environment",
    )

    result = pipeline.ingest_source(source.source_id)

    assert result.parser_used == "text_parser"
    assert result.chunk_count > 0
    assert source.normalized_metadata["storage_backend"] == "gcs"


def test_ingestion_pipeline_uses_pdf_parser_for_mirrored_suffix_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_copy = tmp_path / "mirrored-hint-file"
    local_copy.write_bytes(b"%PDF-1.4 fake content")
    mirrored_uri = "gs://ldt-documents/ldt/sources/municipal/example/general/unknown/example-plan__pdf"

    monkeypatch.setattr(
        "src.ingestion.pipeline.parse_pdf_to_markdown",
        lambda path: "# Mirrored PDF\n\nParsed through suffix hint.",
    )

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(
        source_repo,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=FakeRemoteDocumentStore({mirrored_uri: local_copy}),
    )

    source = registry.register_source(
        source_type="municipal_development_plan",
        title="Mirrored PDF Hint",
        uri=mirrored_uri,
        municipality_id="srb-test",
        category="Development",
        mime_type="application/pdf",
    )

    result = pipeline.ingest_source(source.source_id)
    assert result.parser_used == "pymupdf4llm_markdown_parser"
    assert result.chunk_count > 0


def test_ingestion_pipeline_uses_mime_fallback_when_uri_has_no_suffix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_copy = tmp_path / "suffixless-source"
    local_copy.write_bytes(b"%PDF-1.4 fake content")
    suffixless_uri = "gs://ldt-documents/ldt/sources/national/srb/general/unknown/policy-binary-object"

    monkeypatch.setattr(
        "src.ingestion.pipeline.parse_pdf_to_markdown",
        lambda path: "# MIME Routed PDF\n\nParsed through MIME fallback.",
    )

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(
        source_repo,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=FakeRemoteDocumentStore({suffixless_uri: local_copy}),
    )

    source = registry.register_source(
        source_type="policy_document",
        title="Suffixless PDF",
        uri=suffixless_uri,
        municipality_id="srb-test",
        category="Environment",
        mime_type="application/pdf",
    )

    result = pipeline.ingest_source(source.source_id)
    assert result.parser_used == "pymupdf4llm_markdown_parser"
    assert result.chunk_count > 0


def test_ingestion_pipeline_sniffs_pdf_signature_when_uri_and_mime_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_copy = tmp_path / "signature-only-payload"
    local_copy.write_bytes(b"%PDF-1.4\n% signature-only mock")
    suffixless_uri = "gs://ldt-documents/ldt/sources/national/srb/general/unknown/policy-signature-object"

    monkeypatch.setattr(
        "src.ingestion.pipeline.parse_pdf_to_markdown",
        lambda path: "# Signature Routed PDF\n\nParsed through binary-signature sniffing.",
    )

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(
        source_repo,
        embedding_client=DeterministicEmbeddingClient(),
        document_store=FakeRemoteDocumentStore({suffixless_uri: local_copy}),
    )

    source = registry.register_source(
        source_type="policy_document",
        title="Signature Routed PDF",
        uri=suffixless_uri,
        municipality_id="srb-test",
        category="Environment",
        mime_type=None,
    )

    result = pipeline.ingest_source(source.source_id)
    assert result.parser_used == "pymupdf4llm_markdown_parser"
    assert result.chunk_count > 0


def test_ingestion_pipeline_parses_zip_archive_members(tmp_path: Path) -> None:
    zip_path = tmp_path / "municipal-archive.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plan/overview.txt", "Municipal plan chapter 1.\nChapter 2 implementation.")
        archive.writestr("plan/table.csv", "field,value\nbudget,100\n")

    source_repo = InMemorySourceRepository()
    registry = SourceRegistry(source_repo)
    pipeline = IngestionPipeline(source_repo, embedding_client=DeterministicEmbeddingClient())

    source = registry.register_source(
        source_type="municipal_development_plan",
        title="ZIP Plan",
        uri=str(zip_path),
        municipality_id="srb-zip-test",
        category="Development",
        mime_type="application/zip",
    )

    result = pipeline.ingest_source(source.source_id)
    assert result.parser_used == "zip_archive_parser"
    assert result.chunk_count > 0
    chunks = source_repo.list_chunks_for_source(source_id=source.source_id)
    assert chunks
    combined = "\n".join(chunk.text for chunk in chunks)
    assert "ZIP Member: plan/overview.txt" in combined
