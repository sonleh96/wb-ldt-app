#!/usr/bin/env python3
"""Local Serbia chunking + retrieval smoke workflow (no Cloud Run required)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.embeddings.client import DeterministicEmbeddingClient
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.serbia_operational import canonical_serbia_municipality_id
from src.ingestion.source_registry import SourceRegistry
from src.retrieval.context_windows import RetrievalContextWindowExpander
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.lexical import LexicalRetriever
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.service import RetrievalService
from src.schemas.serbia_dataset import SerbiaDatasetRow
from src.services.serbia_dataset_loader import SerbiaDatasetLoaderService
from src.services.serbia_source_ingestion import SerbiaSourceIngestionService
from src.storage.serbia_datasets import InMemorySerbiaDatasetRepository
from src.storage.sources import InMemorySourceRepository


def _write_sample_document(path: Path, *, title: str, focus: str) -> None:
    """Write one deterministic local text document for ingestion smoke tests."""

    body = [
        f"# {title}",
        "",
        f"This local smoke-test document summarizes priorities for {focus}.",
        "Strategic priorities include resilient infrastructure, climate adaptation, and public services.",
        "Planned investments include water systems, transport links, schools, and digital administration.",
        "Implementation emphasizes financing readiness, procurement discipline, and project monitoring.",
    ]
    path.write_text("\n".join(body), encoding="utf-8")


def _pick_first(rows: list[SerbiaDatasetRow], family: str) -> SerbiaDatasetRow:
    """Return first row for a dataset family or raise with a clear message."""

    for row in rows:
        if row.dataset_family == family:
            return row
    raise ValueError(f"No rows found for dataset family: {family}")


def main() -> None:
    """Run local chunk creation + retrieval smoke test and write local artifacts."""

    parser = argparse.ArgumentParser(description="Run a local Serbia chunking and RAG smoke test.")
    parser.add_argument("--data-dir", default="data", help="Directory containing raw Serbia datasets.")
    parser.add_argument(
        "--output-dir",
        default=".local/serbia-smoke",
        help="Directory for generated local documents and chunk dumps.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    docs_dir = output_dir / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    dataset_repository = InMemorySerbiaDatasetRepository()
    loader = SerbiaDatasetLoaderService(repository=dataset_repository)
    load_summary = loader.load_from_data_dir(data_dir)
    all_rows = dataset_repository.list_rows()

    municipal_row = _pick_first(all_rows, "serbia_municipal_development_plans")
    national_row = _pick_first(all_rows, "serbia_national_documents")

    municipal_doc_path = docs_dir / "municipal-smoke-plan.txt"
    national_doc_path = docs_dir / "national-smoke-policy.txt"
    _write_sample_document(
        municipal_doc_path,
        title=municipal_row.title,
        focus=municipal_row.municipality_name or "municipal development",
    )
    _write_sample_document(
        national_doc_path,
        title=national_row.title,
        focus="national policy planning in Serbia",
    )

    dataset_repository.upsert_row(
        municipal_row.model_copy(
            update={
                "ingestion_readiness": "ready",
                "mirror_status": "mirrored",
                "resolved_document_url": municipal_row.resolved_document_url or municipal_row.source_url,
                "gcs_uri": str(municipal_doc_path),
                "document_mime_type": "text/plain",
                "source_id": None,
                "mirror_error": None,
            }
        )
    )
    dataset_repository.upsert_row(
        national_row.model_copy(
            update={
                "ingestion_readiness": "ready",
                "mirror_status": "mirrored",
                "resolved_document_url": national_row.resolved_document_url or national_row.source_url,
                "gcs_uri": str(national_doc_path),
                "document_mime_type": "text/plain",
                "source_id": None,
                "mirror_error": None,
            }
        )
    )

    source_repository = InMemorySourceRepository()
    source_registry = SourceRegistry(source_repository)
    embedding_client = DeterministicEmbeddingClient()
    ingestion_pipeline = IngestionPipeline(source_repository, embedding_client=embedding_client)
    ingestion_service = SerbiaSourceIngestionService(
        dataset_repository=dataset_repository,
        source_registry=source_registry,
        ingestion_pipeline=ingestion_pipeline,
        source_repository=source_repository,
        embedding_client=embedding_client,
    )
    ingest_summary = ingestion_service.ingest_pending_rows(
        batch_size=1000,
        refresh_mode="force_refresh",
    )

    retrieval = RetrievalService(
        semantic_retriever=SemanticRetriever(source_repository, embedding_client),
        lexical_retriever=LexicalRetriever(source_repository),
        hybrid_retriever=HybridRetriever(
            lexical_retriever=LexicalRetriever(source_repository),
            semantic_retriever=SemanticRetriever(source_repository, embedding_client),
        ),
        context_window_expander=RetrievalContextWindowExpander(source_repository, neighbor_window=0),
    )

    municipality_id = canonical_serbia_municipality_id(municipal_row.municipality_name)
    municipal_query = "What are the main local development priorities and planned investments in this municipality?"
    national_query = "What are Serbia's national policy priorities for sustainable development and public investment?"
    municipal_results = retrieval.search(
        query=municipal_query,
        mode="semantic",
        top_k=5,
        municipality_id=municipality_id,
        source_types={"municipal_development_plan"},
    )
    national_results = retrieval.search(
        query=national_query,
        mode="semantic",
        top_k=5,
        source_types={"policy_document"},
    )

    all_chunks = source_repository.list_chunks()
    chunk_dump_path = output_dir / "chunks.json"
    chunk_dump_path.write_text(
        json.dumps([chunk.model_dump(mode="json") for chunk in all_chunks], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    full_report = {
        "load_summary": load_summary.model_dump(mode="json"),
        "ingest_summary": ingest_summary.model_dump(mode="json"),
        "chunk_count": len(all_chunks),
        "municipal_result_count": municipal_results.total_results,
        "national_result_count": national_results.total_results,
        "municipal_top_source_ids": [item.source_id for item in municipal_results.results[:3]],
        "national_top_source_ids": [item.source_id for item in national_results.results[:3]],
        "chunk_dump_path": str(chunk_dump_path),
    }
    full_report_path = output_dir / "smoke_report_full.json"
    full_report_path.write_text(json.dumps(full_report, ensure_ascii=True, indent=2), encoding="utf-8")
    report = {
        "load_summary": full_report["load_summary"],
        "ingest_summary_counts": {
            "scanned_rows": ingest_summary.scanned_rows,
            "ingested_document_rows": ingest_summary.ingested_document_rows,
            "ingested_structured_rows": ingest_summary.ingested_structured_rows,
            "failed_rows": ingest_summary.failed_rows,
            "skipped_rows": ingest_summary.skipped_rows,
        },
        "chunk_count": full_report["chunk_count"],
        "municipal_result_count": full_report["municipal_result_count"],
        "national_result_count": full_report["national_result_count"],
        "municipal_top_source_ids": full_report["municipal_top_source_ids"],
        "national_top_source_ids": full_report["national_top_source_ids"],
        "chunk_dump_path": full_report["chunk_dump_path"],
        "full_report_path": str(full_report_path),
    }
    report_path = output_dir / "smoke_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
