#!/usr/bin/env python3
"""Operationally ingest canonical Serbia context into source and chunk stores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.core.container import ServiceContainer
from src.ingestion.serbia_context import build_serbia_canonical_context_bundle
from src.ingestion.serbia_operational import ingest_serbia_context_bundle


def _load_uri_map(path: Path) -> dict[str, str] | list[dict[str, str]]:
    """Load URI-resolution mapping payload from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return {
            str(key): str(value)
            for key, value in payload.items()
            if str(key).strip() and str(value).strip()
        }
    if isinstance(payload, list):
        rows: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            rows.append({str(key): str(value) for key, value in item.items() if str(value).strip()})
        return rows
    raise ValueError("URI map JSON must be an object map or a list of object rows.")


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Ingest canonical Serbia context bundle into document and structured retrieval stores."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing the five Serbia source datasets.",
    )
    parser.add_argument(
        "--uri-map",
        default="",
        help="Optional JSON map for resolving non-direct source URLs to uploaded local/gs:// document URIs.",
    )
    parser.add_argument(
        "--skip-document-ingestion",
        action="store_true",
        help="Skip registration/ingestion of document candidates.",
    )
    parser.add_argument(
        "--skip-structured-ingestion",
        action="store_true",
        help="Skip structured record chunk ingestion.",
    )
    parser.add_argument(
        "--report-path",
        default="data/normalized/serbia_operational_ingestion_report.json",
        help="Output path for the ingestion report JSON.",
    )
    return parser.parse_args()


def _print_summary(report_payload: dict[str, Any]) -> None:
    """Print a compact summary for terminal usage."""

    print("Serbia operational ingestion completed.")
    print(
        "Documents: "
        f"total={report_payload['document_candidates_total']}, "
        f"resolved={report_payload['document_candidates_resolved']}, "
        f"ingested={report_payload['document_sources_ingested']}, "
        f"skipped_unresolved={report_payload['document_candidates_skipped_unresolved']}, "
        f"skipped_missing_uri={report_payload['document_candidates_skipped_missing_uri']}, "
        f"failed={report_payload['document_candidates_failed']}"
    )
    print(
        "Structured: "
        f"total={report_payload['structured_records_total']}, "
        f"sources_upserted={report_payload['structured_sources_upserted']}, "
        f"chunks_indexed={report_payload['structured_chunks_indexed']}"
    )


def main() -> None:
    """Build canonical context and ingest operationally into runtime stores."""

    args = _parse_args()
    data_dir = Path(args.data_dir).resolve()
    uri_map_path = Path(args.uri_map).resolve() if args.uri_map else None
    report_path = Path(args.report_path).resolve()

    uri_map = _load_uri_map(uri_map_path) if uri_map_path else None
    bundle = build_serbia_canonical_context_bundle(data_dir)
    container = ServiceContainer()

    report = ingest_serbia_context_bundle(
        bundle=bundle,
        source_registry=container.source_registry,
        ingestion_pipeline=container.ingestion_pipeline,
        source_repository=container.source_repository,
        embedding_client=container.embedding_client,
        document_store=container.document_store,
        uri_resolution_map=uri_map,
        ingest_documents=not args.skip_document_ingestion,
        ingest_structured=not args.skip_structured_ingestion,
    )
    payload = report.model_dump(mode="json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    _print_summary(payload)
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
