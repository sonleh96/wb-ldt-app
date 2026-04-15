from src.embeddings.client import DeterministicEmbeddingClient
from src.ingestion.chunking import chunk_text, chunk_text_semantic, estimate_token_count


def test_chunking_structure_and_token_budget() -> None:
    text = (
        "# Section A\n"
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu\n\n"
        "# Section B\n"
        "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
    )
    chunks = chunk_text(text, max_tokens=8, overlap_tokens=2)

    assert chunks
    assert all(estimate_token_count(chunk) <= 8 for chunk in chunks)
    assert len(chunks) >= 3


def test_semantic_chunking_adds_contextual_headers() -> None:
    text = (
        "# Air Quality Policy\n"
        "Cities should expand air quality monitoring and emissions tracking.\n\n"
        "## Implementation\n"
        "Monitoring stations should be placed near schools and dense roads."
    )

    chunks = chunk_text_semantic(
        text,
        embedding_client=DeterministicEmbeddingClient(),
        document_title="Belgrade Clean Air Plan",
        source_type="policy_document",
        category="Environment",
    )

    assert chunks
    assert chunks[0].header_text.startswith("Document Title: Belgrade Clean Air Plan")
    assert "Section Path: Air Quality Policy" in chunks[0].header_text
    assert chunks[0].body_text in chunks[0].text
