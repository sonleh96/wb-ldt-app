"""Register and ingest Serbia dataset rows into source/chunk storage."""

from __future__ import annotations

import argparse
import json

from src.core.container import ServiceContainer


def main() -> None:
    """Execute the Serbia source-registration and embedding stage."""

    parser = argparse.ArgumentParser(description="Register and ingest Serbia dataset rows into source/chunk stores.")
    parser.add_argument("--batch-size", type=int, default=0, help="Rows to process in this run.")
    parser.add_argument(
        "--refresh-mode",
        choices=["pending_only", "force_refresh"],
        default="",
        help="Lifecycle refresh behavior.",
    )
    parser.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Delete existing Serbia sources/chunks and rebuild all rows from dataset tables.",
    )
    args = parser.parse_args()

    container = ServiceContainer()
    batch_size = args.batch_size or container.settings.serbia_ingestion_batch_size
    if args.refresh_mode and args.refresh_mode != container.settings.serbia_refresh_mode:
        raise ValueError(
            "Conflicting Serbia refresh-mode configuration. "
            f"CLI requested {args.refresh_mode!r} but settings resolve to "
            f"{container.settings.serbia_refresh_mode!r}. Make the job args and env match."
        )

    refresh_mode = args.refresh_mode or container.settings.serbia_refresh_mode
    if args.rebuild_all:
        summary = container.serbia_source_ingestion_service.rebuild_all_rows(batch_size=batch_size)
    else:
        summary = container.serbia_source_ingestion_service.ingest_pending_rows(
            batch_size=batch_size,
            refresh_mode=refresh_mode,  # type: ignore[arg-type]
        )
    print(json.dumps(summary.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
