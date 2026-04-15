"""Service-layer orchestration and business logic."""

from src.workflows.recommendation_graph import RecommendationGraph


class RecommendationWorkflowLauncher:
    """Launcher for RecommendationWorkflow execution."""
    def __init__(self, graph: RecommendationGraph) -> None:
        """Initialize the instance and its dependencies."""
        self._graph = graph

    def launch(self, run_id: str) -> None:
        """Launch workflow execution for a run."""
        self._graph.execute(run_id)
