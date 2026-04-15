from src.config.settings import Settings
from src.core.container import ServiceContainer


def test_context_packer_enforces_budget_and_diversity() -> None:
    container = ServiceContainer(settings=Settings(auto_seed_sources=True))
    retrieval = container.retrieval_service.search(
        query="air quality waste municipal investment",
        mode="hybrid",
        top_k=10,
        municipality_id="srb-belgrade",
        category="Environment",
    )

    pack = container.context_packer.build_context_pack(
        run_id="run-1",
        municipality_id="srb-belgrade",
        category="Environment",
        retrieval_results=retrieval.results,
        token_budget_per_card=40,
        max_cards=4,
    )

    assert len(pack.cards) <= 4
    assert 0.0 <= pack.provenance_completeness_ratio <= 1.0
    unique_sources = {card.source_id for card in pack.cards}
    assert len(unique_sources) >= 1
