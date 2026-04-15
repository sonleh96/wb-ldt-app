"""Schema-shape checks for completed workflow outputs."""

from src.schemas.workflow import NarrativeExplanationOutput


def validate_schema_state(
    *,
    selected_projects: list[dict[str, object]],
    recommendation_candidates: list[dict[str, object]],
    explanation_output: NarrativeExplanationOutput | None,
) -> tuple[dict[str, str], list[str]]:
    """Validate the minimum structured output shape for a completed run."""

    checks = {
        "selected_projects_present": "passed" if selected_projects else "failed",
        "recommendation_candidates_present": "passed" if recommendation_candidates else "failed",
        "narrative_explanation_present": "passed" if explanation_output is not None else "failed",
    }
    errors = [name for name, status in checks.items() if status == "failed"]
    return checks, errors
