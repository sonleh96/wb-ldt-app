"""Route-facing serialization helpers for recommendation contracts."""

from src.schemas.api import RecommendationResponse
from src.schemas.run_state import RunRecord


def serialize_recommendation_result(run: RunRecord) -> RecommendationResponse:
    """Serialize a completed run into the stable frontend-facing result contract."""

    result = run.result
    node_outputs = result.get("node_outputs", {})
    explanation_node = node_outputs.get("generate_explanation", {})
    recommendation_node = node_outputs.get("generate_recommendation_candidates", {})
    build_bundle_node = node_outputs.get("build_evidence_bundle", {})

    return RecommendationResponse(
        run_id=run.run_id,
        status=run.state,
        municipality_id=str(run.request.get("municipality_id", "")),
        category=str(run.request.get("category", "")),
        run_metadata={
            "run_id": run.run_id,
            "status": run.state.value,
            "current_node": run.current_node,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
        },
        context={
            "municipality_id": str(run.request.get("municipality_id", "")),
            "category": str(run.request.get("category", "")),
            "year": run.request.get("year"),
            "language": run.request.get("language", "en"),
            "include_web_evidence": bool(run.request.get("include_web_evidence", False)),
        },
        indicator_summary=node_outputs.get("priority_signals", []),
        recommendation_candidates=result.get("recommendation_candidates", recommendation_node.get("candidates", [])),
        selected_projects=result.get("selected_projects", []),
        ranking=result.get("ranking", []),
        explanation=result.get("explanation", ""),
        explanation_narrative=result.get(
            "explanation_narrative",
            {
                "executive_summary": explanation_node.get("executive_summary", ""),
                "rationale": explanation_node.get("rationale", ""),
                "caveats": explanation_node.get("caveats", []),
                "cited_evidence_ids": explanation_node.get("cited_evidence_ids", []),
            },
        ),
        evidence_bundle_id=result.get("evidence_bundle_id"),
        evidence_bundle_summary=result.get(
            "evidence_bundle_summary",
            {
                "bundle_id": result.get("evidence_bundle_id"),
                "item_count": build_bundle_node.get("item_count", 0),
                "evidence_items": build_bundle_node.get("evidence_items", []),
            },
        ),
        citations=result.get("citations", explanation_node.get("cited_evidence_ids", [])),
        validation_summary=result.get("validation_summary", "not_validated"),
        validation_report=result.get("validation_report", {}),
        context_pack_summary=result.get("context_pack_summary", {}),
        retrieval_diagnostics=result.get("retrieval_diagnostics", {}),
        evaluation_report=result.get("evaluation_report", {}),
    )
