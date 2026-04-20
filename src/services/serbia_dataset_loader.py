"""Load and normalize raw Serbia datasets into dedicated SQL tables."""

from __future__ import annotations

import re
from pathlib import Path

from src.ingestion.serbia_context import (
    normalize_local_project_records,
    normalize_municipal_development_plan_records,
    normalize_national_policy_records,
    normalize_wbif_project_records,
    normalize_wbif_ta_records,
)
from src.schemas.serbia_context import SerbiaContextRecord, SerbiaSourceFamily
from src.schemas.serbia_dataset import SerbiaDatasetFamily, SerbiaDatasetLoadSummary, SerbiaDatasetRow
from src.storage.serbia_datasets import SerbiaDatasetRepository


SOURCE_FAMILY_TO_DATASET_FAMILY: dict[SerbiaSourceFamily, SerbiaDatasetFamily] = {
    "national_policy_document": "serbia_national_documents",
    "municipal_development_plan": "serbia_municipal_development_plans",
    "local_project_record": "serbia_lsg_projects",
    "wbif_project_record": "serbia_wbif_projects",
    "wbif_ta_record": "serbia_wbif_tas",
}


class SerbiaDatasetLoaderService:
    """Normalize source files and upsert rows into Serbia SQL tables."""

    def __init__(self, *, repository: SerbiaDatasetRepository) -> None:
        """Initialize the dataset loader service."""

        self._repository = repository

    def load_from_data_dir(self, data_dir: Path) -> SerbiaDatasetLoadSummary:
        """Load all five Serbia raw datasets into canonical SQL rows."""

        records: list[SerbiaContextRecord] = []
        records.extend(normalize_national_policy_records(data_dir / "national_strategy_policies_law.xlsx"))
        records.extend(normalize_municipal_development_plan_records(data_dir / "serbia_local_dev_plans_final.csv"))
        records.extend(normalize_local_project_records(data_dir / "serbia_lsg_projects.xlsx"))
        records.extend(normalize_wbif_project_records(data_dir / "wbif_projects.csv"))
        records.extend(normalize_wbif_ta_records(data_dir / "wbif_TAs.csv"))

        summary = SerbiaDatasetLoadSummary()
        for record in records:
            row = self._build_dataset_row(record)
            self._repository.upsert_row(row)
            summary.total_rows += 1
            summary.family_counts[row.dataset_family] = summary.family_counts.get(row.dataset_family, 0) + 1
        return summary

    def _build_dataset_row(self, record: SerbiaContextRecord) -> SerbiaDatasetRow:
        """Map one canonical context record into a SQL dataset row."""

        dataset_family = SOURCE_FAMILY_TO_DATASET_FAMILY[record.source_family]
        year_value = _extract_year(record)
        sector = _extract_sector(record)
        category = _extract_category(record)
        beneficiary_country = _string_attr(record, "beneficiary_country")
        beneficiary_body = _string_attr(record, "beneficiary_body")
        project_code = _string_attr(record, "project_code")

        return SerbiaDatasetRow(
            id=record.canonical_id,
            dataset_family=dataset_family,
            dataset_name=dataset_family,
            source_file_name=record.provenance.source_file,
            source_row_number=record.provenance.source_row_number,
            title=record.title,
            country_code=record.country_code,
            country_name=record.country_name,
            municipality_name=record.municipality_name,
            municipality_code=record.municipality_code,
            district_name=record.district_name,
            region_name=record.region_name,
            beneficiary_country=beneficiary_country,
            beneficiary_body=beneficiary_body,
            project_code=project_code,
            sector=sector,
            category=category,
            year_value=year_value,
            source_url=record.source_url,
            resolved_document_url=record.document_url,
            landing_page_url=record.landing_page_url,
            url_kind=record.url_kind,
            ingestion_readiness=record.ingestion_readiness,
            mirror_status="not_started",
            raw_payload={
                "source_family": record.source_family,
                "display_title": record.display_title,
                "category_tags": record.category_tags,
                "sector_tags": record.sector_tags,
                "summary_text": record.summary_text,
                "attributes": record.attributes,
                "provenance": record.provenance.model_dump(mode="json"),
            },
        )


def _string_attr(record: SerbiaContextRecord, key: str) -> str | None:
    """Return a string attribute value when present and non-empty."""

    value = record.attributes.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_sector(record: SerbiaContextRecord) -> str | None:
    """Return a representative sector string for dataset table rows."""

    if record.sector_tags:
        return record.sector_tags[0]
    for key in ("investment_sector", "sector", "project_sector_code"):
        value = _string_attr(record, key)
        if value:
            return value
    return None


def _extract_category(record: SerbiaContextRecord) -> str | None:
    """Map tags to retrieval categories used by existing query filters."""

    tags = {tag.lower() for tag in [*record.category_tags, *record.sector_tags]}
    if "environment" in tags:
        return "Environment"
    if "transport" in tags or "mobility" in tags:
        return "Sustainable Transport"
    if "energy" in tags:
        return "Energy"
    if "social" in tags:
        return "Social"
    return None


def _extract_year(record: SerbiaContextRecord) -> int | None:
    """Extract a best-effort year value from title or attributes."""

    for key in ("year", "estimated_completion", "date_of_award", "date_of_completion", "ga_signature_date"):
        value = record.attributes.get(key)
        if value is None:
            continue
        match = re.search(r"(19|20)\d{2}", str(value))
        if match:
            return int(match.group(0))
    match = re.search(r"(19|20)\d{2}", record.title)
    if match:
        return int(match.group(0))
    return None
