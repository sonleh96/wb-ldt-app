from pathlib import Path

from src.ingestion.serbia_context import (
    build_serbia_canonical_context_bundle,
    classify_url_kind,
    export_serbia_canonical_context_bundle,
    normalize_local_project_records,
    normalize_municipal_development_plan_records,
    normalize_national_policy_records,
    normalize_wbif_project_records,
    normalize_wbif_ta_records,
)
from src.schemas.api import SourceRegistrationRequest


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def test_national_policy_workbook_normalizes_to_typed_document_records() -> None:
    records = normalize_national_policy_records(_data_dir() / "national_strategy_policies_law.xlsx")

    assert len(records) == 24
    assert all(record.source_family == "national_policy_document" for record in records)
    assert all(record.title for record in records)
    assert all(record.provenance.source_file == "national_strategy_policies_law.xlsx" for record in records)


def test_municipal_plans_produce_161_records_and_flag_10_missing_links() -> None:
    records = normalize_municipal_development_plan_records(_data_dir() / "serbia_local_dev_plans_final.csv")
    missing = [record for record in records if record.ingestion_readiness == "missing_url"]

    assert len(records) == 161
    assert len(missing) == 10
    assert all(record.source_family == "municipal_development_plan" for record in records)


def test_lsg_projects_normalize_numeric_date_and_flag_fields_without_row_loss() -> None:
    records = normalize_local_project_records(_data_dir() / "serbia_lsg_projects.xlsx")

    assert len(records) == 107
    assert all(record.source_family == "local_project_record" for record in records)
    assert any(record.attributes.get("investment_amount_eur") is not None for record in records)
    assert any(record.attributes.get("decision_signed") is True for record in records)
    assert any(record.attributes.get("ga_signature_date") for record in records)


def test_wbif_project_filter_returns_consistent_serbia_slice() -> None:
    records = normalize_wbif_project_records(_data_dir() / "wbif_projects.csv")

    assert len(records) == 77
    assert all(record.source_family == "wbif_project_record" for record in records)
    assert all("serb" in str(record.attributes.get("beneficiary_country", "")).lower() for record in records)


def test_wbif_ta_filter_returns_consistent_serbia_slice() -> None:
    records = normalize_wbif_ta_records(_data_dir() / "wbif_TAs.csv")

    assert len(records) == 39
    assert all(record.source_family == "wbif_ta_record" for record in records)
    assert all(
        "serb" in str(record.attributes.get("beneficiaries", "")).lower()
        or "serb" in record.title.lower()
        for record in records
    )


def test_url_classification_covers_document_drive_landing_and_blank_links() -> None:
    assert classify_url_kind("https://example.org/policy.pdf") == "direct_document"
    assert classify_url_kind("https://example.org/plan.docx") == "office_doc"
    assert classify_url_kind("https://example.org/archive.zip") == "archive"
    assert classify_url_kind("https://drive.google.com/file/d/abc/view") == "cloud_drive"
    assert classify_url_kind("https://www.wbif.eu/project-detail/PRJ-SRB-TRA-001") == "landing_page"
    assert classify_url_kind("") == "unknown"


def test_document_like_records_can_be_transformed_into_source_registration_requests() -> None:
    bundle = build_serbia_canonical_context_bundle(_data_dir())

    assert bundle.document_registration_candidates
    candidate = bundle.document_registration_candidates[0]
    request = SourceRegistrationRequest(
        source_type=candidate.source_type,
        title=candidate.title,
        uri=candidate.uri,
        source_url=candidate.source_url,
        document_url=candidate.document_url,
        landing_page_url=candidate.landing_page_url,
        url_kind=candidate.url_kind,
        ingestion_readiness=candidate.ingestion_readiness,
        municipality_id=candidate.municipality_id,
        category=candidate.category,
        source_id=candidate.canonical_id,
    )
    assert request.uri


def test_metadata_only_and_missing_link_records_are_retained_in_structured_context_view() -> None:
    bundle = build_serbia_canonical_context_bundle(_data_dir())

    assert bundle.structured_context_records
    assert len(bundle.structured_context_records) == len(bundle.records)
    assert any(record.source_family == "local_project_record" for record in bundle.structured_context_records)
    assert any(record.source_family == "wbif_project_record" for record in bundle.structured_context_records)
    assert any(
        record.source_family == "municipal_development_plan" and record.ingestion_readiness == "missing_url"
        for record in bundle.records
    )


def test_structured_project_records_are_searchable_by_key_dimensions() -> None:
    bundle = build_serbia_canonical_context_bundle(_data_dir())
    local_project = next(record for record in bundle.structured_context_records if record.source_family == "local_project_record")
    wbif_project = next(record for record in bundle.structured_context_records if record.source_family == "wbif_project_record")
    wbif_ta = next(record for record in bundle.structured_context_records if record.source_family == "wbif_ta_record")

    assert local_project.municipality_name
    assert local_project.municipality_name.lower() in local_project.searchable_text.lower()
    assert wbif_project.title.lower() in wbif_project.searchable_text.lower()
    assert "beneficiary_country" in wbif_project.searchable_text
    assert "project_code" in wbif_ta.searchable_text
    assert "beneficiaries" in wbif_ta.searchable_text


def test_municipal_plans_and_national_policies_keep_retrieval_oriented_context_fields() -> None:
    bundle = build_serbia_canonical_context_bundle(_data_dir())
    municipal = next(record for record in bundle.structured_context_records if record.source_family == "municipal_development_plan")
    national = next(record for record in bundle.structured_context_records if record.source_family == "national_policy_document")

    if municipal.district_name:
        assert municipal.district_name.lower() in municipal.searchable_text.lower()
    if municipal.municipality_name:
        assert municipal.municipality_name.lower() in municipal.searchable_text.lower()
    assert national.title.lower() in national.searchable_text.lower()
    assert "national-policy" in national.searchable_text.lower()


def test_export_bundle_writes_canonical_and_derived_json_files(tmp_path: Path) -> None:
    bundle = build_serbia_canonical_context_bundle(_data_dir())
    export_serbia_canonical_context_bundle(bundle, tmp_path)

    records_file = tmp_path / "serbia_context_records.jsonl"
    candidates_file = tmp_path / "serbia_document_registration_candidates.jsonl"
    structured_file = tmp_path / "serbia_structured_context_records.jsonl"
    stats_file = tmp_path / "serbia_context_stats.json"

    assert records_file.is_file()
    assert candidates_file.is_file()
    assert structured_file.is_file()
    assert stats_file.is_file()
    assert records_file.read_text(encoding="utf-8").splitlines()
    assert structured_file.read_text(encoding="utf-8").splitlines()
