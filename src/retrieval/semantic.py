"""Retrieval interfaces and scoring implementations."""

from src.embeddings.client import EmbeddingClient
from src.schemas.retrieval import RetrievalResult
from src.storage.sources import SourceRepository


class SemanticRetriever:
    """Class representing SemanticRetriever."""

    def __init__(self, source_repository: SourceRepository, embedding_client: EmbeddingClient) -> None:
        """Initialize the instance and its dependencies."""

        self._source_repository = source_repository
        self._embedding_client = embedding_client

    def search(
        self,
        *,
        query: str,
        top_k: int,
        municipality_id: str | None,
        category: str | None,
        source_types: set[str] | None = None,
    ) -> list[RetrievalResult]:
        """Search and return ranked retrieval results."""

        query_embedding = self._embedding_client.embed_query(query)
        matches = self._source_repository.search_similar_chunks(
            query_embedding=query_embedding,
            top_k=top_k,
            municipality_id=municipality_id,
            category=category,
            source_types=source_types,
        )

        results: list[RetrievalResult] = []
        for match in matches:
            chunk = match.chunk
            semantic_score = match.score
            results.append(
                RetrievalResult(
                    source_id=chunk.source_id,
                    chunk_id=chunk.chunk_id,
                    source_type=chunk.source_type,
                    score=semantic_score,
                    lexical_score=0.0,
                    semantic_score=semantic_score,
                    municipality_id=chunk.municipality_id,
                    category=chunk.category,
                    snippet=chunk.text[:280],
                    citation_title=match.source.title if match.source else None,
                    citation_uri=match.source.uri if match.source else None,
                    metadata={
                        "embedding_model": chunk.embedding_model or self._embedding_client.model_name,
                        "semantic_group_id": str(chunk.semantic_group_id or 0),
                        "chunk_index": str(chunk.chunk_index),
                        "header_text": chunk.header_text or "",
                        "section_path": " > ".join(chunk.section_path),
                    },
                )
            )

        return results
