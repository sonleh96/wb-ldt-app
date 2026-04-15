from src.embeddings.client import DeterministicEmbeddingClient
from src.ingestion.chunking import SemanticChunkingConfig, chunk_text_semantic


def test_semantic_chunking_respects_token_budget_and_groups() -> None:
    text = (
        "Air quality sensors help city officials identify particulate hotspots. "
        "Monitoring stations support emissions enforcement and exposure mapping. "
        "Waste collection routes reduce illegal dumping in dense neighborhoods. "
        "Collection planning also improves recycling participation across districts."
    )

    chunks = chunk_text_semantic(
        text,
        embedding_client=DeterministicEmbeddingClient(),
        document_title="Environment Plan",
        source_type="policy_document",
        category="Environment",
        config=SemanticChunkingConfig(max_tokens=10, overlap_tokens=2, min_chunk_tokens=4),
    )

    assert chunks
    assert all(chunk.token_count <= 10 for chunk in chunks)
    assert all(chunk.semantic_group_id is not None for chunk in chunks)
    assert len({chunk.semantic_group_id for chunk in chunks}) >= 1
    assert all(chunk.header_text for chunk in chunks)
