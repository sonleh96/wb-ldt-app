from src.schemas.workflow import NarrativeExplanationOutput
from src.validation.run_validator import RunValidator


def test_run_validator_fails_on_context_contradiction() -> None:
    validator = RunValidator()

    report = validator.validate(
        run_id="run-1",
        request_context={"municipality_id": "srb-belgrade", "category": "Environment"},
        recommendation_candidates=[{"candidate_id": "cand-1", "category": "Transport"}],
        selected_projects=[{"title": "Urban Air Monitoring Expansion", "category": "Environment"}],
        excluded_projects=[],
        evidence_ids={"e1", "e2"},
        explanation_output=NarrativeExplanationOutput(
            executive_summary="Urban Air Monitoring Expansion is selected.",
            rationale="Urban Air Monitoring Expansion fits the evidence.",
            caveats=[],
            cited_evidence_ids=["e1", "e2"],
        ),
    )

    assert report.status == "failed"
    assert report.failure_policy == "fail_run"
    assert "recommendation_context_alignment" in report.checks


def test_run_validator_warns_on_unsupported_claim_hook() -> None:
    validator = RunValidator()

    report = validator.validate(
        run_id="run-2",
        request_context={"municipality_id": "srb-belgrade", "category": "Environment"},
        recommendation_candidates=[{"candidate_id": "cand-1", "category": "Environment"}],
        selected_projects=[{"title": "Urban Air Monitoring Expansion", "category": "Environment"}],
        excluded_projects=[],
        evidence_ids={"e1"},
        explanation_output=NarrativeExplanationOutput(
            executive_summary="Urban Air Monitoring Expansion is selected based on a long explanation text without explicit support.",
            rationale="Urban Air Monitoring Expansion continues to be discussed in a long rationale that intentionally omits evidence references to trigger the unsupported claim hook.",
            caveats=[],
            cited_evidence_ids=[],
        ),
    )

    assert report.status == "warning"
    assert report.failure_policy in {"downgrade_confidence", "partial_result"}
    assert "unsupported_claim_detection_hook" in report.checks
