from __future__ import annotations

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.core.app import create_app
from src.core.container import ServiceContainer
from src.schemas.serbia_dataset import SerbiaDatasetRow
from src.services.serbia_document_mirror import FetchedDocument, SerbiaDocumentMirrorService
from src.storage.serbia_datasets import InMemorySerbiaDatasetRepository
from src.storage.sources import InMemorySourceRepository


class _FakeFetcher:
    def __init__(self, documents: dict[str, FetchedDocument]) -> None:
        self._documents = documents

    def fetch_document(self, url: str, *, timeout_seconds: int, max_retries: int) -> FetchedDocument:
        if url not in self._documents:
            raise RuntimeError(f"Missing fake document for URL: {url}")
        return self._documents[url]

    def fetch_text(self, url: str, *, timeout_seconds: int, max_retries: int) -> str:
        return "<html></html>"


class _FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, *, object_name: str, content: bytes, content_type: str | None) -> str:
        self.objects[object_name] = content
        return f"gs://fake-bucket/{object_name}"


def test_admin_dataset_endpoints_list_failures_mirror_and_ingest_row() -> None:
    dataset_repo = InMemorySerbiaDatasetRepository()
    dataset_repo.upsert_row(
        SerbiaDatasetRow(
            id="mirror-row",
            dataset_family="serbia_national_documents",
            dataset_name="serbia_national_documents",
            source_file_name="national_strategy_policies_law.xlsx",
            source_row_number=2,
            title="Serbia National Environmental Law",
            source_url="https://example.org/law.pdf",
            url_kind="direct_document",
            ingestion_readiness="ready",
            mirror_status="not_started",
            raw_payload={},
        )
    )
    dataset_repo.upsert_row(
        SerbiaDatasetRow(
            id="failed-row",
            dataset_family="serbia_wbif_projects",
            dataset_name="serbia_wbif_projects",
            source_file_name="wbif_projects.csv",
            source_row_number=5,
            title="Failed Mirror Record",
            source_url="https://example.org/missing.pdf",
            url_kind="direct_document",
            ingestion_readiness="ready",
            mirror_status="failed",
            mirror_error="404",
            raw_payload={},
        )
    )
    dataset_repo.upsert_row(
        SerbiaDatasetRow(
            id="structured-row",
            dataset_family="serbia_wbif_tas",
            dataset_name="serbia_wbif_tas",
            source_file_name="wbif_TAs.csv",
            source_row_number=11,
            title="Serbia TA Structured",
            project_code="WBIF-TA-123",
            beneficiary_country="Serbia",
            sector="transport",
            category="Sustainable Transport",
            source_url="https://example.org/project-detail/ta-123",
            landing_page_url="https://example.org/project-detail/ta-123",
            url_kind="landing_page",
            ingestion_readiness="needs_resolver",
            mirror_status="skipped",
            raw_payload={"description": "TA structured content"},
        )
    )

    mirror_service = SerbiaDocumentMirrorService(
        repository=dataset_repo,
        fetcher=_FakeFetcher(
            {
                "https://example.org/law.pdf": FetchedDocument(
                    content=b"%PDF fake",
                    final_url="https://example.org/law.pdf",
                    mime_type="application/pdf",
                )
            }
        ),
        object_store=_FakeObjectStore(),
        gcs_prefix="ldt/sources",
        timeout_seconds=5,
        max_retries=0,
    )
    app = create_app(
        container=ServiceContainer(
            settings=Settings(auto_seed_sources=False),
            serbia_dataset_repository=dataset_repo,
            serbia_document_mirror_service=mirror_service,
            source_repository=InMemorySourceRepository(),
        )
    )
    with TestClient(app) as client:
        listed = client.get("/v1/admin/datasets/rows", params={"dataset_family": "serbia_national_documents"})
        assert listed.status_code == 200
        rows = listed.json()
        assert len(rows) == 1
        assert rows[0]["id"] == "mirror-row"

        failures = client.get("/v1/admin/datasets/failures/mirroring")
        assert failures.status_code == 200
        failure_rows = failures.json()
        assert any(row["id"] == "failed-row" for row in failure_rows)

        mirrored = client.post("/v1/admin/datasets/serbia_national_documents/mirror-row/mirror")
        assert mirrored.status_code == 200
        mirrored_payload = mirrored.json()
        assert mirrored_payload["mirror_status"] == "mirrored"
        assert mirrored_payload["gcs_uri"].startswith("gs://fake-bucket/")

        ingested = client.post("/v1/admin/datasets/serbia_wbif_tas/structured-row/ingest")
        assert ingested.status_code == 200
        ingested_payload = ingested.json()
        assert ingested_payload["status"] == "ingested_structured"
        assert ingested_payload["source_id"]

        updated_rows = client.get(
            "/v1/admin/datasets/rows",
            params={"dataset_family": "serbia_wbif_tas", "has_source_id": True},
        )
        assert updated_rows.status_code == 200
        assert any(row["id"] == "structured-row" for row in updated_rows.json())
