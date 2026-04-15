from src.config.settings import Settings
from src.core.container import ServiceContainer
from src.schemas.api import RecommendationRequest
from src.schemas.run_state import RunState
from tests.unit.fakes import (
    FakeExplanationGenerator,
    FakeRecommendationGenerator,
    FailingExplanationGenerator,
    FailingRecommendationGenerator,
)


def test_recommendation_graph_executes_full_route() -> None:
    container = ServiceContainer(
        settings=Settings(auto_seed_sources=True),
        recommendation_generator=FakeRecommendationGenerator(),
        explanation_generator=FakeExplanationGenerator(),
    )
    run = container.run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-belgrade",
            category="Environment",
            year=2024,
            include_web_evidence=True,
            top_n_projects=2,
        )
    )

    container.recommendation_graph.execute(run.run_id)
    completed = container.run_registry.get_run(run.run_id)

    assert completed.state == RunState.COMPLETED
    node_outputs = completed.result.get("node_outputs", {})
    assert "build_evidence_bundle" in node_outputs
    assert "optionally_retrieve_web_evidence" in node_outputs
    assert "generate_recommendation_candidates" in node_outputs
    assert node_outputs["generate_recommendation_candidates"]["model_name"] == "fake-model"
    assert "generate_explanation" in node_outputs
    assert "executive_summary" in node_outputs["generate_explanation"]
    assert completed.result["selected_projects"][0]["ranking_breakdown"]["total_score"] > 0
    assert completed.result["excluded_projects"]
    assert "evaluation_report" in completed.result


def test_recommendation_graph_fails_at_generation_node() -> None:
    container = ServiceContainer(
        settings=Settings(auto_seed_sources=True),
        recommendation_generator=FailingRecommendationGenerator(),
        explanation_generator=FakeExplanationGenerator(),
    )
    run = container.run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-belgrade",
            category="Environment",
            year=2024,
        )
    )

    container.recommendation_graph.execute(run.run_id)
    failed = container.run_registry.get_run(run.run_id)

    assert failed.state == RunState.FAILED
    assert failed.current_node == "generate_recommendation_candidates"
    assert failed.error_message == "synthetic generation failure"


def test_recommendation_graph_fails_at_explanation_node() -> None:
    container = ServiceContainer(
        settings=Settings(auto_seed_sources=True),
        recommendation_generator=FakeRecommendationGenerator(),
        explanation_generator=FailingExplanationGenerator(),
    )
    run = container.run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-belgrade",
            category="Environment",
            year=2024,
        )
    )

    container.recommendation_graph.execute(run.run_id)
    failed = container.run_registry.get_run(run.run_id)

    assert failed.state == RunState.FAILED
    assert failed.current_node == "generate_explanation"
    assert failed.error_message == "synthetic explanation failure"
