from src.config.settings import Settings
from src.core.container import ServiceContainer


def test_evidence_bundle_builds_with_deduped_items() -> None:
    container = ServiceContainer(settings=Settings(auto_seed_sources=True))
    signals = container.municipality_profile_service.compute_priority_signals(
        municipality_id="srb-belgrade",
        category="Environment",
        year=2024,
        top_n=2,
    )
    retrieval = container.retrieval_service.search(
        query="waste disposal and air quality",
        mode="hybrid",
        top_k=5,
        municipality_id="srb-belgrade",
        category="Environment",
    )

    bundle = container.evidence_bundle_service.build_bundle(
        municipality_id="srb-belgrade",
        category="Environment",
        priority_signals=signals,
        retrieval_results=retrieval.results,
    )

    assert bundle.bundle_id
    assert len(bundle.items) >= len(signals)
