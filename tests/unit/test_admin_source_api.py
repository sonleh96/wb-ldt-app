from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.core.app import create_app
from src.core.container import ServiceContainer


def test_admin_source_endpoints_register_list_and_ingest_sources_idempotently() -> None:
    base_dir = Path(__file__).resolve().parents[2] / ".test-artifacts"
    base_dir.mkdir(exist_ok=True)
    source_path = base_dir / "admin-source.txt"
    source_path.write_text("Belgrade air quality policy text.", encoding="utf-8")

    app = create_app(container=ServiceContainer(settings=Settings(auto_seed_sources=False)))
    with TestClient(app) as client:
        empty = client.get("/v1/admin/sources")
        assert empty.status_code == 200
        assert empty.json() == []

        payload = {
            "source_type": "policy_document",
            "title": "Admin Policy Source",
            "uri": str(source_path),
            "municipality_id": "srb-belgrade",
            "category": "Environment",
            "mime_type": "text/plain",
        }
        registered = client.post("/v1/admin/sources", json=payload)
        assert registered.status_code == 200
        registered_payload = registered.json()
        assert registered_payload["title"] == "Admin Policy Source"

        duplicate = client.post("/v1/admin/sources", json=payload)
        assert duplicate.status_code == 200
        assert duplicate.json()["source_id"] == registered_payload["source_id"]

        listed = client.get("/v1/admin/sources")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        ingested = client.post(f"/v1/admin/sources/{registered_payload['source_id']}/ingest")
        assert ingested.status_code == 200
        assert ingested.json()["chunk_count"] > 0
        assert ingested.json()["parser_used"] == "text_parser"


def test_capabilities_endpoint_reports_current_runtime_features() -> None:
    app = create_app(container=ServiceContainer(settings=Settings(auto_seed_sources=False)))

    with TestClient(app) as client:
        response = client.get("/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_runs"] is True
    assert payload["project_review"] is True
    assert payload["web_research_policy_control"] is False
    assert "admin source ingestion" in payload["notes"].lower()
