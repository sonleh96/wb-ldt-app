#!/usr/bin/env python3
"""Load raw Serbia datasets into canonical Supabase/Postgres tables."""

from __future__ import annotations

from src.jobs.load_serbia_datasets import main


if __name__ == "__main__":
    main()
