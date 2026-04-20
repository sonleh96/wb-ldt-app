#!/usr/bin/env python3
"""Load raw Serbia datasets into canonical Supabase/Postgres tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.container import ServiceContainer


def main() -> None:
    """Execute the Serbia dataset load stage."""

    parser = argparse.ArgumentParser(description="Load Serbia raw datasets into SQL staging tables.")
    parser.add_argument("--data-dir", default="data", help="Directory containing the five Serbia dataset files.")
    args = parser.parse_args()

    container = ServiceContainer()
    if not container.settings.serbia_dataset_loading_enabled:
        print("Serbia dataset loading is disabled by configuration.")
        return

    summary = container.serbia_dataset_loader_service.load_from_data_dir(Path(args.data_dir).resolve())
    print(json.dumps(summary.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
