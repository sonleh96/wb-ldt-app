"""Citation and evidence validation helpers."""

from src.schemas.workflow import NarrativeExplanationOutput


def validate_citations(
    *,
    evidence_ids: set[str],
    explanation_output: NarrativeExplanationOutput | None,
    selected_projects: list[dict[str, object]],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Validate evidence/citation presence and sufficiency."""

    if explanation_output is None:
        return {"explanation_citations_present": "failed", "sufficient_evidence_threshold": "failed"}, [], [
            "Explanation output is missing, so citations cannot be validated.",
            "Insufficient evidence references for a completed recommendation run.",
        ]

    cited = set(explanation_output.cited_evidence_ids)
    unknown = sorted(cited - evidence_ids)
    checks = {
        "explanation_citations_present": "passed" if cited else "warning",
        "sufficient_evidence_threshold": "passed" if len(cited) >= min(2, max(1, len(selected_projects))) else "warning",
    }
    warnings: list[str] = []
    errors: list[str] = []
    if unknown:
        checks["explanation_citations_present"] = "failed"
        errors.append(f"Explanation cites unknown evidence ids: {', '.join(unknown)}.")
    if not cited:
        warnings.append("Explanation does not cite evidence ids.")
    if checks["sufficient_evidence_threshold"] != "passed":
        warnings.append("Explanation cites too little evidence for the selected project set.")
    return checks, warnings, errors
