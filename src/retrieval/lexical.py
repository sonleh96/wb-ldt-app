"""Retrieval interfaces and scoring implementations."""

from src.schemas.retrieval import RetrievalResult
from src.schemas.source_metadata import SourceMetadata
from src.storage.sources import SourceRepository


def _tokenize(text: str) -> set[str]:
    """Internal helper to tokenize."""
    return {part.strip(".,;:!?()[]{}\"'").lower() for part in text.split() if part.strip()}


class LexicalRetriever:
    """Class representing LexicalRetriever."""
    def __init__(self, source_repository: SourceRepository) -> None:
        """Initialize the instance and its dependencies."""
        self._source_repository = source_repository

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
        query_tokens = _tokenize(query)
        chunks = self._source_repository.list_chunks(
            municipality_id=municipality_id,
            category=category,
            source_types=source_types,
        )

        results: list[RetrievalResult] = []
        for chunk in chunks:
            chunk_tokens = _tokenize(chunk.text)
            overlap = len(query_tokens & chunk_tokens)
            if overlap == 0:
                continue
            lexical_score = overlap / max(len(query_tokens), 1)
            source: SourceMetadata | None = self._source_repository.get_source(chunk.source_id)
            results.append(
                RetrievalResult(
                    source_id=chunk.source_id,
                    chunk_id=chunk.chunk_id,
                    source_type=chunk.source_type,
                    score=lexical_score,
                    lexical_score=lexical_score,
                    semantic_score=0.0,
                    municipality_id=chunk.municipality_id,
                    category=chunk.category,
                    snippet=chunk.text[:280],
                    citation_title=source.title if source else None,
                    citation_uri=source.uri if source else None,
                    metadata={
                        "chunk_index": str(chunk.chunk_index),
                        "header_text": chunk.header_text or "",
                        "section_path": " > ".join(chunk.section_path),
                    },
                )
            )

        return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]
