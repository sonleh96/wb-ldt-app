from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.core.container import ServiceContainer
from src.core.app import create_app
from tests.unit.fakes import (
    FakeExplanationGenerator,
    FakeProjectReviewGenerator,
    FakeRecommendationGenerator,
)


def test_api_submit_poll_result_includes_batch3_fields() -> None:
    app = create_app(
        container=ServiceContainer(
            settings=Settings(auto_seed_sources=True),
            recommendation_generator=FakeRecommendationGenerator(),
            explanation_generator=FakeExplanationGenerator(),
            project_review_generator=FakeProjectReviewGenerator(),
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/runs/recommendations",
            json={
                "municipality_id": "srb-belgrade",
                "category": "Environment",
                "year": 2024,
                "include_web_evidence": True,
                "top_n_projects": 3,
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        status = client.get(f"/v1/runs/{run_id}")
        assert status.status_code == 200
        assert status.json()["state"] in {"completed", "running", "validating", "queued"}

        # BackgroundTasks execute in request lifecycle in TestClient, result is expected immediately.
        result = client.get(f"/v1/runs/{run_id}/result")
        assert result.status_code == 200
        payload = result.json()
        assert "context_pack_summary" in payload
        assert "retrieval_diagnostics" in payload
        assert "evaluation_report" in payload


def test_api_project_review_endpoint_returns_typed_review() -> None:
    app = create_app(
        container=ServiceContainer(
            settings=Settings(auto_seed_sources=True),
            recommendation_generator=FakeRecommendationGenerator(),
            explanation_generator=FakeExplanationGenerator(),
            project_review_generator=FakeProjectReviewGenerator(),
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/runs/recommendations",
            json={
                "municipality_id": "srb-belgrade",
                "category": "Environment",
                "year": 2024,
                "include_web_evidence": False,
                "top_n_projects": 2,
            },
        )
        run_id = response.json()["run_id"]
        result = client.get(f"/v1/runs/{run_id}/result")
        project_id = result.json()["selected_projects"][0]["project_id"]

        review = client.post(
            "/v1/project-reviews",
            json={
                "run_id": run_id,
                "project_id": project_id,
                "include_web_evidence": False,
            },
        )
        assert review.status_code == 200
        payload = review.json()
        assert payload["run_id"] == run_id
        assert payload["project_review"]["project_id"] == project_id
        assert payload["validation_summary"] in {"passed", "warning"}


def test_api_run_inspection_endpoints_return_trace_evidence_and_validation() -> None:
    app = create_app(
        container=ServiceContainer(
            settings=Settings(auto_seed_sources=True),
            recommendation_generator=FakeRecommendationGenerator(),
            explanation_generator=FakeExplanationGenerator(),
            project_review_generator=FakeProjectReviewGenerator(),
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/runs/recommendations",
            json={
                "municipality_id": "srb-belgrade",
                "category": "Environment",
                "year": 2024,
                "include_web_evidence": True,
                "top_n_projects": 2,
            },
        )
        run_id = response.json()["run_id"]

        trace = client.get(f"/v1/runs/{run_id}/trace")
        assert trace.status_code == 200
        trace_payload = trace.json()
        assert trace_payload["run_id"] == run_id
        assert trace_payload["nodes"]
        assert trace_payload["retrieval_traces"]

        evidence = client.get(f"/v1/runs/{run_id}/evidence")
        assert evidence.status_code == 200
        evidence_payload = evidence.json()
        assert evidence_payload["run_id"] == run_id
        assert evidence_payload["evidence_items"]

        validation = client.get(f"/v1/runs/{run_id}/validation")
        assert validation.status_code == 200
        validation_payload = validation.json()
        assert validation_payload["run_id"] == run_id
        assert validation_payload["validation_report"]
        assert validation_payload["evaluation_report"]
