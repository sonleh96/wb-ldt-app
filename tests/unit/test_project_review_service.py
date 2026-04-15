from src.config.settings import Settings
from src.core.container import ServiceContainer
from src.schemas.api import ProjectReviewRequest, RecommendationRequest
from tests.unit.fakes import (
    FakeExplanationGenerator,
    FakeProjectReviewGenerator,
    FakeRecommendationGenerator,
)


def test_project_review_service_caches_reviews() -> None:
    container = ServiceContainer(
        settings=Settings(auto_seed_sources=True),
        recommendation_generator=FakeRecommendationGenerator(),
        explanation_generator=FakeExplanationGenerator(),
        project_review_generator=FakeProjectReviewGenerator(),
    )
    run = container.run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-belgrade",
            category="Environment",
            year=2024,
        )
    )
    container.recommendation_graph.execute(run.run_id)
    completed = container.run_registry.get_run(run.run_id)
    project_id = completed.result["selected_projects"][0]["project_id"]

    response_a = container.project_review_service.get_or_create_review(
        run_id=run.run_id,
        project_id=project_id,
        include_web_evidence=False,
    )
    response_b = container.project_review_service.get_or_create_review(
        run_id=run.run_id,
        project_id=project_id,
        include_web_evidence=False,
    )

    assert response_a.project_review.project_id == project_id
    assert response_b.project_review.project_id == project_id
    cached = container.project_review_store.get(
        run_id=run.run_id,
        project_id=project_id,
        include_web_evidence=False,
    )
    assert cached is not None
    assert cached.review.project_id == project_id
