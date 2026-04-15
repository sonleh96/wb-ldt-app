"""Retrieval interfaces and scoring implementations."""

from src.retrieval.context_windows import RetrievalContextWindowExpander
from src.schemas.retrieval import RetrievalResponse
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.lexical import LexicalRetriever
from src.retrieval.semantic import SemanticRetriever


class RetrievalService:
    """Service for Retrieval workflows and operations."""
    def __init__(
        self,
        *,
        semantic_retriever: SemanticRetriever,
        lexical_retriever: LexicalRetriever,
        hybrid_retriever: HybridRetriever,
        context_window_expander: RetrievalContextWindowExpander | None = None,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._semantic_retriever = semantic_retriever
        self._lexical_retriever = lexical_retriever
        self._hybrid_retriever = hybrid_retriever
        self._context_window_expander = context_window_expander

    def search(
        self,
        *,
        query: str,
        mode: str,
        top_k: int,
        municipality_id: str | None = None,
        category: str | None = None,
        source_types: set[str] | None = None,
    ) -> RetrievalResponse:
        """Search and return ranked retrieval results."""
        diagnostics: dict[str, object] = {}
        if mode == "semantic":
            results = self._semantic_retriever.search(
                query=query,
                top_k=top_k,
                municipality_id=municipality_id,
                category=category,
                source_types=source_types,
            )
            diagnostics = {"semantic_result_count": len(results), "mode": "semantic"}
        elif mode == "lexical":
            results = self._lexical_retriever.search(
                query=query,
                top_k=top_k,
                municipality_id=municipality_id,
                category=category,
                source_types=source_types,
            )
            diagnostics = {"lexical_result_count": len(results), "mode": "lexical"}
        elif mode == "hybrid":
            results, diagnostics = self._hybrid_retriever.search(
                query=query,
                top_k=top_k,
                municipality_id=municipality_id,
                category=category,
                source_types=source_types,
            )
        else:
            raise ValueError(f"Unsupported retrieval mode: {mode}")

        if self._context_window_expander is not None:
            results, expansion_diagnostics = self._context_window_expander.expand(results)
            diagnostics = {**diagnostics, **expansion_diagnostics}

        return RetrievalResponse(
            mode=mode,
            query=query,
            total_results=len(results),
            results=results,
            diagnostics=diagnostics,
        )
