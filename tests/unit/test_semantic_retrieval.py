from src.embeddings.client import DeterministicEmbeddingClient
from src.retrieval.semantic import SemanticRetriever
from src.schemas.source_metadata import SourceChunk, SourceMetadata
from src.storage.sources import InMemorySourceRepository


def test_semantic_retriever_uses_chunk_embeddings() -> None:
    source_repo = InMemorySourceRepository()
    source = SourceMetadata(
        source_id="src-1",
        source_type="policy_document",
        title="Air Policy",
        uri="memory://air-policy",
        municipality_id="srb-belgrade",
        category="Environment",
    )
    source_repo.upsert_source(source)

    embedding_client = DeterministicEmbeddingClient()
    air_embedding = embedding_client.embed_query("air quality monitoring emissions sensors")
    waste_embedding = embedding_client.embed_query("waste collection recycling routes")
    source_repo.replace_chunks(
        source.source_id,
        [
            SourceChunk(
                chunk_id="src-1:0",
                source_id=source.source_id,
                chunk_index=0,
                text="Air quality monitoring and emissions sensor deployment.",
                token_count=8,
                embedding=air_embedding,
                embedding_model=embedding_client.model_name,
                semantic_group_id=0,
                municipality_id="srb-belgrade",
                category="Environment",
                source_type="policy_document",
            ),
            SourceChunk(
                chunk_id="src-1:1",
                source_id=source.source_id,
                chunk_index=1,
                text="Waste collection vehicle planning and route coverage.",
                token_count=8,
                embedding=waste_embedding,
                embedding_model=embedding_client.model_name,
                semantic_group_id=1,
                municipality_id="srb-belgrade",
                category="Environment",
                source_type="policy_document",
            ),
        ],
    )

    retriever = SemanticRetriever(source_repo, embedding_client)
    results = retriever.search(
        query="Which source talks about emissions monitoring?",
        top_k=1,
        municipality_id="srb-belgrade",
        category="Environment",
    )

    assert len(results) == 1
    assert results[0].chunk_id == "src-1:0"
    assert results[0].metadata["embedding_model"] == embedding_client.model_name
