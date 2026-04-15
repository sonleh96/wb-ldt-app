from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.core.app import create_app
from src.core.container import ServiceContainer
from tests.unit.fakes import FakeExplanationGenerator, FakeProjectReviewGenerator, FakeRecommendationGenerator


def test_recommendation_flow_acceptance_contract() -> None:
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
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        status = client.get(f"/v1/runs/{run_id}")
        assert status.status_code == 200
        assert status.json()["state"] == "completed"

        result = client.get(f"/v1/runs/{run_id}/result")
        assert result.status_code == 200
        payload = result.json()
        assert payload["run_metadata"]["run_id"] == run_id
        assert payload["context"]["municipality_id"] == "srb-belgrade"
        assert payload["indicator_summary"]
        assert payload["recommendation_candidates"]
        assert payload["selected_projects"]
        assert payload["ranking"]
        assert payload["explanation"]
        assert payload["explanation_narrative"]["executive_summary"]
        assert payload["evidence_bundle_summary"]["item_count"] > 0
        assert payload["citations"]
        assert payload["validation_report"]
        assert payload["evaluation_report"]

        trace = client.get(f"/v1/runs/{run_id}/trace")
        assert trace.status_code == 200
        assert trace.json()["model_traces"]
