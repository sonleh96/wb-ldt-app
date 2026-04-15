"""Consistency validation helpers for recommendation outputs."""

from src.schemas.workflow import NarrativeExplanationOutput


def validate_consistency(
    *,
    request_context: dict[str, object],
    recommendation_candidates: list[dict[str, object]],
    selected_projects: list[dict[str, object]],
    excluded_projects: list[dict[str, object]],
    explanation_output: NarrativeExplanationOutput | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Validate consistency between explanation, ranking, and request context."""

    category = str(request_context.get("category", ""))
    municipality_id = str(request_context.get("municipality_id", ""))
    text = ""
    if explanation_output is not None:
        text = f"{explanation_output.executive_summary} {explanation_output.rationale}"

    selected_titles = [str(project.get("title", "")) for project in selected_projects]
    excluded_titles = [str(project.get("title", "")) for project in excluded_projects]
    candidate_categories_ok = all(str(candidate.get("category", "")) == category for candidate in recommendation_candidates)
    selected_categories_ok = all(str(project.get("category", "")) == category for project in selected_projects)
    selected_municipality_ok = all(
        project.get("municipality_id") in {None, municipality_id}
        for project in selected_projects
    )
    explanation_mentions_selected = bool(text) and any(title and title in text for title in selected_titles)
    explanation_promotes_excluded = any(title and title in text for title in excluded_titles)

    checks = {
        "recommendation_context_alignment": "passed" if candidate_categories_ok and selected_categories_ok else "failed",
        "selected_project_municipality_alignment": "passed" if selected_municipality_ok else "failed",
        "explanation_ranking_consistency": "passed" if explanation_mentions_selected and not explanation_promotes_excluded else "failed",
        "unsupported_claim_detection_hook": "warning" if explanation_output is not None and len(text.split()) > 20 and not explanation_output.cited_evidence_ids else "passed",
    }
    warnings: list[str] = []
    errors: list[str] = []
    if not candidate_categories_ok or not selected_categories_ok:
        errors.append("Recommendation output contradicts the requested category context.")
    if not selected_municipality_ok:
        errors.append("Selected projects contradict the requested municipality context.")
    if not explanation_mentions_selected or explanation_promotes_excluded:
        errors.append("Explanation contradicts ranking output or selected-project set.")
    if checks["unsupported_claim_detection_hook"] == "warning":
        warnings.append("Unsupported-claim detection hook flagged explanation text without citation support.")
    return checks, warnings, errors
