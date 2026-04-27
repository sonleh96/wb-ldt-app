"""Integration tests for recommendation workflow with Postgres-backed reference data."""

from src.config.settings import Settings
from src.core.container import ServiceContainer
from src.schemas.api import RecommendationRequest
from src.schemas.run_state import RunState
from src.storage.project_reviews import InMemoryProjectReviewStore
from src.storage.run_store import InMemoryRunStore
from src.storage.run_traces import InMemoryRunTraceStore
from src.storage.serbia_datasets import InMemorySerbiaDatasetRepository
from src.storage.sources import InMemorySourceRepository
from tests.unit.fake_reference_psycopg import FakeReferencePsycopg, build_reference_database
from tests.unit.fakes import FakeExplanationGenerator, FakeRecommendationGenerator


def test_recommendation_workflow_uses_postgres_backed_reference_repositories(monkeypatch) -> None:
    """Recommendation flow should rank using staged-project rows in postgres mode."""

    fake_psycopg = FakeReferencePsycopg(build_reference_database())
    monkeypatch.setattr("src.storage.projects.psycopg", fake_psycopg)
    monkeypatch.setattr("src.storage.municipalities.psycopg", fake_psycopg)
    monkeypatch.setattr("src.storage.indicators.psycopg", fake_psycopg)

    container = ServiceContainer(
        settings=Settings(
            storage_backend="postgres",
            database_url="postgresql://fake",
            auto_seed_sources=True,
        ),
        recommendation_generator=FakeRecommendationGenerator(),
        explanation_generator=FakeExplanationGenerator(),
        source_repository=InMemorySourceRepository(),
        serbia_dataset_repository=InMemorySerbiaDatasetRepository(),
        run_store=InMemoryRunStore(),
        project_review_store=InMemoryProjectReviewStore(),
        run_trace_store=InMemoryRunTraceStore(),
    )

    run = container.run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-uzice",
            category="Environment",
            year=2024,
            include_web_evidence=False,
            top_n_projects=2,
        )
    )
    container.recommendation_graph.execute(run.run_id)
    completed = container.run_registry.get_run(run.run_id)

    assert completed.state == RunState.COMPLETED
    ranking = completed.result["ranking"]
    assert ranking
    assert any(item["project_id"].startswith(("lsg-", "wbif-")) for item in ranking)
    assert all(not item["project_id"].startswith("proj-") for item in ranking)
    assert "query_planning_handoff" in completed.result["retrieval_diagnostics"]
    assert "coverage" in completed.result["retrieval_diagnostics"]

    node_outputs = completed.result["node_outputs"]
    generation_output = node_outputs["generate_recommendation_candidates"]
    assert generation_output["project_context_count"] > 0
