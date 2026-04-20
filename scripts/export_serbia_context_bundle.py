#!/usr/bin/env python3
"""Build and export canonical Serbia context records from data files."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.ingestion.serbia_context import (
    build_serbia_canonical_context_bundle,
    export_serbia_canonical_context_bundle,
)


def main() -> None:
    """Build canonical Serbia context data and export machine-readable files."""

    parser = argparse.ArgumentParser(description="Export canonical Serbia context ingestion bundle.")
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing source datasets.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/normalized",
        help="Directory for canonical JSON exports.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    bundle = build_serbia_canonical_context_bundle(data_dir)
    export_serbia_canonical_context_bundle(bundle, output_dir)
    print(f"Exported canonical Serbia context bundle to: {output_dir}")
    print(bundle.stats)


if __name__ == "__main__":
    main()
