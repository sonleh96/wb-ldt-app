from src.config.settings import Settings
from src.core.container import ServiceContainer


def test_retrieval_service_hybrid_returns_filtered_results() -> None:
    container = ServiceContainer(settings=Settings(auto_seed_sources=True))
    response = container.retrieval_service.search(
        query="air quality monitoring waste collection",
        mode="hybrid",
        top_k=5,
        municipality_id="srb-belgrade",
        category="Environment",
    )

    assert response.mode == "hybrid"
    assert response.total_results > 0
    assert "rrf_k" in response.diagnostics
    assert response.diagnostics["context_window_neighbors"] == 1
    assert all(result.category in {"Environment", None} for result in response.results)
    assert all(result.fused_rank is not None for result in response.results)
    assert all("chunk_text" in result.metadata for result in response.results)
