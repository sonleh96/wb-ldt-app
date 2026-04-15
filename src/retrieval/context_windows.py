"""Context-window enrichment for retrieval results."""

from __future__ import annotations

from src.schemas.retrieval import RetrievalResult
from src.storage.sources import SourceRepository


class RetrievalContextWindowExpander:
    """Expand retrieved chunks with nearby same-source chunk context."""

    def __init__(self, source_repository: SourceRepository, *, neighbor_window: int = 1) -> None:
        """Initialize the expander."""

        self._source_repository = source_repository
        self._neighbor_window = max(0, neighbor_window)

    @staticmethod
    def _merge_bodies(chunks: list[str]) -> str:
        """Merge chunk bodies into one context window."""

        return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()

    def expand(self, results: list[RetrievalResult]) -> tuple[list[RetrievalResult], dict[str, object]]:
        """Expand retrieval results with neighboring chunks from the same source."""

        if self._neighbor_window == 0 or not results:
            return results, {"context_window_neighbors": 0, "expanded_results": 0}

        expanded: list[RetrievalResult] = []
        for result in results:
            chunk_index = result.metadata.get("chunk_index")
            if chunk_index is None:
                expanded.append(result)
                continue
            center_index = int(chunk_index)
            neighbor_chunks = self._source_repository.list_chunks_for_source(
                source_id=result.source_id,
                start_index=max(0, center_index - self._neighbor_window),
                end_index=center_index + self._neighbor_window,
            )
            if not neighbor_chunks:
                expanded.append(result)
                continue

            merged_body = self._merge_bodies(
                [chunk.body_text or chunk.text for chunk in neighbor_chunks]
            )
            center_chunk = next(
                (chunk for chunk in neighbor_chunks if chunk.chunk_index == center_index),
                neighbor_chunks[min(self._neighbor_window, len(neighbor_chunks) - 1)],
            )
            header_text = center_chunk.header_text or ""
            contextual_text = f"{header_text}\n\n{merged_body}".strip() if header_text else merged_body
            expanded.append(
                result.model_copy(
                    update={
                        "snippet": contextual_text[:280],
                        "metadata": {
                            **result.metadata,
                            "context_window_neighbors": str(self._neighbor_window),
                            "context_window_start": str(neighbor_chunks[0].chunk_index),
                            "context_window_end": str(neighbor_chunks[-1].chunk_index),
                            "chunk_text": contextual_text,
                        },
                    }
                )
            )
        return expanded, {
            "context_window_neighbors": self._neighbor_window,
            "expanded_results": len(expanded),
        }
