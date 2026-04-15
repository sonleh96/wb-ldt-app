from src.config.settings import Settings
from src.schemas.api import RecommendationRequest
from src.schemas.run_state import RunState
from src.core.container import ServiceContainer
from src.services.run_registry import RunRegistry
from src.services.workflow_launcher import RecommendationWorkflowLauncher
from src.storage.run_store import InMemoryRunStore
from tests.unit.fakes import FakeExplanationGenerator, FakeRecommendationGenerator


def test_run_registry_lifecycle_with_workflow_launcher() -> None:
    container = ServiceContainer(
        settings=Settings(auto_seed_sources=True),
        recommendation_generator=FakeRecommendationGenerator(),
        explanation_generator=FakeExplanationGenerator(),
    )
    run_registry = container.run_registry
    launcher = container.workflow_launcher
    assert isinstance(launcher, RecommendationWorkflowLauncher)

    run = run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-belgrade",
            category="Environment",
            year=2024,
        )
    )

    launcher.launch(run.run_id)
    final_run = run_registry.get_run(run.run_id)
    assert final_run.state == RunState.COMPLETED
    assert "validation_summary" in final_run.result
    assert "node_outputs" in final_run.result


def test_cancel_before_processing() -> None:
    run_registry = RunRegistry(InMemoryRunStore())
    run = run_registry.create_recommendation_run(
        RecommendationRequest(
            municipality_id="srb-belgrade",
            category="Environment",
            year=2024,
        )
    )

    cancelled = run_registry.cancel_run(run.run_id)
    assert cancelled.state == RunState.CANCELLED
