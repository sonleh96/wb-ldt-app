from pathlib import Path

import pytest

from src.storage.documents import (
    LocalDocumentStore,
    filename_from_uri,
    is_gcs_uri,
    parse_gcs_uri,
    suffix_from_uri,
)


def test_gcs_uri_helpers_parse_bucket_object_and_filename() -> None:
    uri = "gs://ldt-documents/ldt/sources/national/srb/environment/2024/policy__en__2024__v1.pdf"

    assert is_gcs_uri(uri) is True
    assert parse_gcs_uri(uri) == (
        "ldt-documents",
        "ldt/sources/national/srb/environment/2024/policy__en__2024__v1.pdf",
    )
    assert filename_from_uri(uri) == "policy__en__2024__v1.pdf"
    assert suffix_from_uri(uri) == ".pdf"


def test_suffix_from_uri_infers_mirrored_trailing_extension_hint() -> None:
    uri = "gs://ldt-documents/ldt/sources/municipal/bato-ina/general/unknown/bato-ina-local-development-plan__pdf"
    assert filename_from_uri(uri) == "bato-ina-local-development-plan__pdf"
    assert suffix_from_uri(uri) == ".pdf"


def test_gcs_uri_parser_rejects_missing_object_name() -> None:
    with pytest.raises(ValueError):
        parse_gcs_uri("gs://ldt-documents")


def test_local_document_store_rejects_gcs_uri() -> None:
    store = LocalDocumentStore()

    assert store.exists("gs://ldt-documents/source.pdf") is False


def test_local_document_store_yields_existing_path(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    store = LocalDocumentStore()

    with store.as_local_path(str(source)) as path:
        assert path == source
        assert path.read_text(encoding="utf-8") == "content"
