"""Service-layer orchestration and business logic."""

import hashlib
import uuid

from src.schemas.domain import EvidenceBundle, EvidenceItem, PrioritySignal
from src.schemas.retrieval import RetrievalResult
from src.validation.evidence_validation import validate_evidence_items


def _evidence_key(item: EvidenceItem) -> str:
    """Internal helper to evidence key."""
    payload = f"{item.origin}|{item.source_id}|{item.chunk_id}|{item.statement}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EvidenceBundleService:
    """Service for EvidenceBundle workflows and operations."""
    def build_bundle(
        self,
        *,
        municipality_id: str,
        category: str,
        priority_signals: list[PrioritySignal],
        retrieval_results: list[RetrievalResult],
        web_evidence: list[EvidenceItem] | None = None,
    ) -> EvidenceBundle:
        """Build bundle."""
        web_rows = web_evidence or []
        items: list[EvidenceItem] = []

        for signal in priority_signals:
            items.append(
                EvidenceItem(
                    evidence_id=f"analytics:{signal.indicator_id}",
                    origin="analytics",
                    statement=signal.reason,
                    confidence=min(1.0, max(0.2, signal.severity)),
                    municipality_id=municipality_id,
                    category=category,
                    metadata={"indicator_name": signal.indicator_name},
                )
            )

        for result in retrieval_results:
            items.append(
                EvidenceItem(
                    evidence_id=f"retrieval:{result.chunk_id}",
                    origin="local_retrieval",
                    statement=str(result.metadata.get("chunk_text", result.snippet)),
                    confidence=min(1.0, max(0.1, result.score)),
                    source_id=result.source_id,
                    chunk_id=result.chunk_id,
                    municipality_id=result.municipality_id or municipality_id,
                    category=result.category or category,
                    metadata={
                        "retrieval_mode_score": f"{result.score:.4f}",
                        "citation_title": result.citation_title or "",
                        "citation_uri": result.citation_uri or "",
                        "header_text": str(result.metadata.get("header_text", "")),
                        "section_path": str(result.metadata.get("section_path", "")),
                    },
                )
            )

        items.extend(web_rows)
        deduped_map: dict[str, EvidenceItem] = {}
        for item in items:
            deduped_map[_evidence_key(item)] = item
        deduped_items = list(deduped_map.values())

        validation_errors = validate_evidence_items(deduped_items)
        if validation_errors:
            raise ValueError("; ".join(validation_errors))

        return EvidenceBundle(
            bundle_id=str(uuid.uuid4()),
            municipality_id=municipality_id,
            category=category,
            items=deduped_items,
        )
