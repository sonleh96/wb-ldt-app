from pathlib import Path
from typing import Iterator

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
