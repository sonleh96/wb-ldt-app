"""Workflow graph routing and execution engine."""

def build_recommendation_route(*, include_web_evidence: bool) -> list[str]:
    """Build recommendation route."""
    route = [
        "create_run",
        "resolve_request_context",
        "compute_indicator_analysis",
        "plan_retrieval",
        "retrieve_local_evidence",
    ]
    if include_web_evidence:
        route.append("optionally_retrieve_web_evidence")
    route.extend(
        [
            "build_evidence_bundle",
            "generate_recommendation_candidates",
            "rank_candidates",
            "select_projects",
            "generate_explanation",
            "validate_output",
            "finalize_run",
        ]
    )
    return route
