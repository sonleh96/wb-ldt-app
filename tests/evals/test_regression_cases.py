import json
from pathlib import Path

from src.config.settings import Settings
from src.core.container import ServiceContainer
from src.schemas.api import RecommendationRequest
from src.schemas.run_state import RunState
from tests.unit.fakes import FakeExplanationGenerator, FakeProjectReviewGenerator, FakeRecommendationGenerator


def _container() -> ServiceContainer:
    return ServiceContainer(
        settings=Settings(auto_seed_sources=True),
        recommendation_generator=FakeRecommendationGenerator(),
        explanation_generator=FakeExplanationGenerator(),
        project_review_generator=FakeProjectReviewGenerator(),
    )


def _fixtures() -> list[dict[str, object]]:
    path = Path(__file__).resolve().parent / "fixtures" / "bad_recommendations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_bad_recommendation_regressions() -> None:
    fixtures = _fixtures()
    for fixture in fixtures:
        container = _container()
        run = container.run_registry.create_recommendation_run(
            RecommendationRequest(
                municipality_id=str(fixture["municipality_id"]),
                category=str(fixture["category"]),
                year=int(fixture["year"]),
                include_web_evidence=True,
                top_n_projects=2,
            )
        )
        container.recommendation_graph.execute(run.run_id)
        completed = container.run_registry.get_run(run.run_id)

        assert completed.state == RunState.COMPLETED, fixture["name"]

        if "expected_excluded_project_id" in fixture:
            excluded_ids = [item["project_id"] for item in completed.result.get("excluded_projects", [])]
            assert str(fixture["expected_excluded_project_id"]) in excluded_ids, fixture["name"]

        if "minimum_cited_evidence_count" in fixture:
            explanation_node = completed.result.get("node_outputs", {}).get("generate_explanation", {})
            cited = explanation_node.get("cited_evidence_ids", [])
            assert len(cited) >= int(fixture["minimum_cited_evidence_count"]), fixture["name"]
