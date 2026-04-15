"""Run-level validation orchestration and failure-policy selection."""

from src.schemas.domain import ValidationReport
from src.schemas.workflow import NarrativeExplanationOutput
from src.validation.citation_checks import validate_citations
from src.validation.consistency_checks import validate_consistency
from src.validation.schema_checks import validate_schema_state


class RunValidator:
    """Compose modular validators for completed recommendation runs."""

    def validate(
        self,
        *,
        run_id: str,
        request_context: dict[str, object],
        recommendation_candidates: list[dict[str, object]],
        selected_projects: list[dict[str, object]],
        excluded_projects: list[dict[str, object]],
        evidence_ids: set[str],
        explanation_output: NarrativeExplanationOutput | None,
    ) -> ValidationReport:
        """Validate a completed run and choose a failure policy."""

        checks: dict[str, str] = {}
        warnings: list[str] = []
        errors: list[str] = []

        schema_checks, schema_errors = validate_schema_state(
            selected_projects=selected_projects,
            recommendation_candidates=recommendation_candidates,
            explanation_output=explanation_output,
        )
        checks.update(schema_checks)
        errors.extend(schema_errors)

        citation_checks, citation_warnings, citation_errors = validate_citations(
            evidence_ids=evidence_ids,
            explanation_output=explanation_output,
            selected_projects=selected_projects,
        )
        checks.update(citation_checks)
        warnings.extend(citation_warnings)
        errors.extend(citation_errors)

        consistency_checks, consistency_warnings, consistency_errors = validate_consistency(
            request_context=request_context,
            recommendation_candidates=recommendation_candidates,
            selected_projects=selected_projects,
            excluded_projects=excluded_projects,
            explanation_output=explanation_output,
        )
        checks.update(consistency_checks)
        warnings.extend(consistency_warnings)
        errors.extend(consistency_errors)

        failed_checks = [name for name, status in checks.items() if status == "failed"]
        warning_checks = [name for name, status in checks.items() if status == "warning"]

        if failed_checks:
            status = "failed"
            failure_policy = "fail_run"
        elif warning_checks:
            status = "warning"
            if "unsupported_claim_detection_hook" in warning_checks:
                failure_policy = "downgrade_confidence"
            else:
                failure_policy = "partial_result"
        else:
            status = "passed"
            failure_policy = "none"

        return ValidationReport(
            run_id=run_id,
            status=status,
            checks=checks,
            warnings=warnings,
            errors=errors,
            failure_policy=failure_policy,
            metadata={
                "failed_checks": failed_checks,
                "warning_checks": warning_checks,
                "retry_supported": "narrative_explanation_present" in failed_checks,
            },
        )
