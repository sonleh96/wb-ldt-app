"""Service-layer orchestration and business logic."""

import uuid

from src.ingestion.chunking import chunk_text
from src.schemas.retrieval import RetrievalResult
from src.schemas.workflow import ContextPack, EvidenceCard


class ContextPacker:
    """Service for ContextPacker workflows and operations."""

    def build_context_pack(
        self,
        *,
        run_id: str,
        municipality_id: str,
        category: str,
        retrieval_results: list[RetrievalResult],
        token_budget_per_card: int = 120,
        max_cards: int = 8,
    ) -> ContextPack:
        """Build context pack."""
        selected: list[EvidenceCard] = []
        source_seen: set[str] = set()

        for result in sorted(
            retrieval_results,
            key=lambda row: (
                row.citation_uri is not None,
                row.fusion_score,
                row.score,
            ),
            reverse=True,
        ):
            if len(selected) >= max_cards:
                break

            # Diversity rule: avoid over-concentrating all cards in a single source.
            if result.source_id in source_seen and len(source_seen) >= max(2, max_cards // 3):
                continue

            excerpt_chunks = chunk_text(result.snippet, max_tokens=token_budget_per_card, overlap_tokens=20)
            excerpt = excerpt_chunks[0] if excerpt_chunks else result.snippet
            provenance_complete = bool(result.source_id and result.chunk_id and result.citation_uri)

            card = EvidenceCard(
                card_id=f"card-{uuid.uuid4()}",
                source_id=result.source_id,
                chunk_id=result.chunk_id,
                source_type=result.source_type,
                relevance_score=result.fusion_score or result.score,
                selection_reason="Selected via fused lexical+semantic retrieval with provenance filter.",
                claim_text=result.snippet[:220],
                supporting_excerpt=excerpt,
                municipality_id=result.municipality_id or municipality_id,
                category=result.category or category,
                provenance_complete=provenance_complete,
                metadata={
                    "lexical_score": f"{result.lexical_score:.4f}",
                    "semantic_score": f"{result.semantic_score:.4f}",
                    "fusion_score": f"{(result.fusion_score or result.score):.4f}",
                    "fused_rank": str(result.fused_rank or ""),
                },
            )
            selected.append(card)
            source_seen.add(result.source_id)

        provenance_ratio = (
            sum(1 for card in selected if card.provenance_complete) / len(selected)
            if selected
            else 0.0
        )

        return ContextPack(
            run_id=run_id,
            cards=selected,
            max_cards=max_cards,
            token_budget_per_card=token_budget_per_card,
            provenance_completeness_ratio=provenance_ratio,
            diagnostics={
                "input_result_count": str(len(retrieval_results)),
                "selected_card_count": str(len(selected)),
                "unique_sources": str(len(source_seen)),
            },
        )
