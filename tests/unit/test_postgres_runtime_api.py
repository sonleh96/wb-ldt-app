from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.core.app import create_app
from src.core.container import ServiceContainer
from src.storage.project_reviews import PostgresProjectReviewStore
from src.storage.run_store import PostgresRunStore
from src.storage.run_traces import PostgresRunTraceStore
from src.storage.sources import InMemorySourceRepository
from tests.unit.fake_psycopg import FakePostgresDatabase, FakePsycopg
from tests.unit.fakes import FakeExplanationGenerator, FakeProjectReviewGenerator, FakeRecommendationGenerator


def test_postgres_runtime_state_survives_container_reinstantiation(monkeypatch) -> None:
    fake_psycopg = FakePsycopg(FakePostgresDatabase())
    monkeypatch.setattr("src.storage.run_store.psycopg", fake_psycopg)
    monkeypatch.setattr("src.storage.project_reviews.psycopg", fake_psycopg)
    monkeypatch.setattr("src.storage.run_traces.psycopg", fake_psycopg)

    run_store = PostgresRunStore(database_url="postgresql://fake")
    project_review_store = PostgresProjectReviewStore(database_url="postgresql://fake")
    run_trace_store = PostgresRunTraceStore(database_url="postgresql://fake")

    seeded_source_repo = InMemorySourceRepository()
    app_a = create_app(
        container=ServiceContainer(
            settings=Settings(auto_seed_sources=True),
            recommendation_generator=FakeRecommendationGenerator(),
            explanation_generator=FakeExplanationGenerator(),
            project_review_generator=FakeProjectReviewGenerator(),
            source_repository=seeded_source_repo,
            run_store=run_store,
            project_review_store=project_review_store,
            run_trace_store=run_trace_store,
        )
    )

    with TestClient(app_a) as client_a:
        created = client_a.post(
            "/v1/runs/recommendations",
            json={
                "municipality_id": "srb-belgrade",
                "category": "Environment",
                "year": 2024,
                "top_n_projects": 2,
            },
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        result = client_a.get(f"/v1/runs/{run_id}/result")
        assert result.status_code == 200
        project_id = result.json()["selected_projects"][0]["project_id"]

        review = client_a.post(
            "/v1/project-reviews",
            json={
                "run_id": run_id,
                "project_id": project_id,
                "include_web_evidence": False,
            },
        )
        assert review.status_code == 200

    app_b = create_app(
        container=ServiceContainer(
            settings=Settings(auto_seed_sources=False),
            recommendation_generator=FakeRecommendationGenerator(),
            explanation_generator=FakeExplanationGenerator(),
            project_review_generator=FakeProjectReviewGenerator(),
            source_repository=InMemorySourceRepository(),
            run_store=PostgresRunStore(database_url="postgresql://fake"),
            project_review_store=PostgresProjectReviewStore(database_url="postgresql://fake"),
            run_trace_store=PostgresRunTraceStore(database_url="postgresql://fake"),
        )
    )

    with TestClient(app_b) as client_b:
        status_response = client_b.get(f"/v1/runs/{run_id}")
        assert status_response.status_code == 200
        assert status_response.json()["state"] == "completed"

        result_response = client_b.get(f"/v1/runs/{run_id}/result")
        assert result_response.status_code == 200
        assert result_response.json()["run_id"] == run_id

        trace_response = client_b.get(f"/v1/runs/{run_id}/trace")
        assert trace_response.status_code == 200
        assert trace_response.json()["run_id"] == run_id

        review_response = client_b.get(f"/v1/project-reviews/{run_id}/{project_id}")
        assert review_response.status_code == 200
        assert review_response.json()["project_review"]["project_id"] == project_id
