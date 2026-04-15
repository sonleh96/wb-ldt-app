"""Retrieval interfaces and scoring implementations."""

from src.retrieval.lexical import LexicalRetriever
from src.retrieval.semantic import SemanticRetriever
from src.schemas.retrieval import RetrievalResult


class HybridRetriever:
    """Class representing HybridRetriever."""
    def __init__(
        self,
        *,
        lexical_retriever: LexicalRetriever,
        semantic_retriever: SemanticRetriever,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._lexical_retriever = lexical_retriever
        self._semantic_retriever = semantic_retriever

    def search(
        self,
        *,
        query: str,
        top_k: int,
        municipality_id: str | None,
        category: str | None,
        source_types: set[str] | None = None,
        rrf_k: int = 60,
        min_fusion_score: float = 0.01,
    ) -> tuple[list[RetrievalResult], dict[str, object]]:
        """Search and return ranked retrieval results."""
        lexical_results = self._lexical_retriever.search(
            query=query,
            top_k=top_k * 2,
            municipality_id=municipality_id,
            category=category,
            source_types=source_types,
        )
        semantic_results = self._semantic_retriever.search(
            query=query,
            top_k=top_k * 2,
            municipality_id=municipality_id,
            category=category,
            source_types=source_types,
        )

        combined: dict[str, RetrievalResult] = {}
        lexical_rank_map = {row.chunk_id: idx + 1 for idx, row in enumerate(lexical_results)}
        semantic_rank_map = {row.chunk_id: idx + 1 for idx, row in enumerate(semantic_results)}
        dropped_reasons: dict[str, str] = {}

        for result in lexical_results:
            combined[result.chunk_id] = result.model_copy(
                update={"lexical_rank": lexical_rank_map[result.chunk_id]}
            )
        for result in semantic_results:
            existing = combined.get(result.chunk_id)
            if existing is None:
                combined[result.chunk_id] = result.model_copy(
                    update={"semantic_rank": semantic_rank_map[result.chunk_id]}
                )
            else:
                merged = existing.model_copy(
                    update={
                        "lexical_score": max(existing.lexical_score, result.lexical_score),
                        "semantic_score": max(existing.semantic_score, result.semantic_score),
                        "semantic_rank": semantic_rank_map[result.chunk_id],
                    }
                )
                combined[result.chunk_id] = merged

        ranked: list[RetrievalResult] = []
        for item in combined.values():
            lr = item.lexical_rank
            sr = item.semantic_rank
            rrf_score = (1.0 / (rrf_k + lr) if lr else 0.0) + (1.0 / (rrf_k + sr) if sr else 0.0)
            fused = item.model_copy(update={"score": rrf_score, "fusion_score": rrf_score})

            if not (fused.source_id and fused.chunk_id and fused.citation_uri):
                dropped_reasons[fused.chunk_id] = "missing_provenance"
                continue
            if fused.fusion_score < min_fusion_score:
                dropped_reasons[fused.chunk_id] = "below_fusion_score_floor"
                continue
            ranked.append(fused)

        ranked = sorted(ranked, key=lambda item: item.score, reverse=True)
        for idx, item in enumerate(ranked, start=1):
            ranked[idx - 1] = item.model_copy(update={"fused_rank": idx})

        final_rows = ranked[:top_k]
        diagnostics = {
            "lexical_result_count": len(lexical_results),
            "semantic_result_count": len(semantic_results),
            "fused_candidate_count": len(combined),
            "returned_result_count": len(final_rows),
            "dropped_results": dropped_reasons,
            "rrf_k": rrf_k,
            "min_fusion_score": min_fusion_score,
        }
        return final_rows, diagnostics
