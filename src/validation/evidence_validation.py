"""Validation helpers for runtime artifacts and outputs."""

from src.schemas.domain import EvidenceItem


def validate_evidence_items(items: list[EvidenceItem]) -> list[str]:
    """Validate evidence items."""
    errors: list[str] = []
    for item in items:
        if not item.evidence_id:
            errors.append("Evidence item is missing evidence_id.")
        if not item.origin:
            errors.append(f"Evidence item {item.evidence_id} is missing origin.")
        if not item.statement:
            errors.append(f"Evidence item {item.evidence_id} is missing statement.")
        if item.source_id is None and item.origin in {"local_retrieval", "web_research"}:
            errors.append(f"Evidence item {item.evidence_id} is missing source_id.")
    return errors
