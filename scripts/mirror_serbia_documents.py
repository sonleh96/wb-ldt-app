#!/usr/bin/env python3
"""Mirror resolvable Serbia dataset documents into GCS."""

from __future__ import annotations

import argparse
import json

from src.core.container import ServiceContainer


def main() -> None:
    """Execute the Serbia document mirroring stage."""

    parser = argparse.ArgumentParser(description="Mirror resolvable Serbia dataset document URLs into GCS.")
    parser.add_argument("--batch-size", type=int, default=0, help="Rows to process in this run.")
    parser.add_argument(
        "--refresh-mode",
        choices=["pending_only", "force_refresh"],
        default="",
        help="Lifecycle refresh behavior.",
    )
    args = parser.parse_args()

    container = ServiceContainer()
    if not container.settings.serbia_document_mirroring_enabled:
        print("Serbia document mirroring is disabled by configuration.")
        return
    if container.serbia_document_mirror_service is None:
        raise ValueError("GCS mirror service is not configured. Set LDT_GCS_BUCKET for mirroring.")

    batch_size = args.batch_size or container.settings.serbia_ingestion_batch_size
    refresh_mode = args.refresh_mode or container.settings.serbia_refresh_mode
    summary = container.serbia_document_mirror_service.mirror_pending_rows(
        batch_size=batch_size,
        refresh_mode=refresh_mode,  # type: ignore[arg-type]
    )
    print(json.dumps(summary.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
