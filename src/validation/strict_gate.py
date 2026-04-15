"""Validation helpers for runtime artifacts and outputs."""

from src.schemas.workflow import ContextPack, EvaluationReport


class StrictEvaluationGate:
    """Class representing StrictEvaluationGate."""

    def evaluate(
        self,
        *,
        context_pack: ContextPack | None,
        selected_projects: list[dict],
        explanation: str,
        retrieval_diagnostics: dict[str, object],
    ) -> EvaluationReport:
        """Evaluate output."""
        thresholds = {
            "min_provenance_completeness_ratio": 0.7,
            "min_retrieval_relevance": 0.02,
            "min_signal_coverage": 0.6,
        }

        provenance_ratio = context_pack.provenance_completeness_ratio if context_pack else 0.0
        scores = [
            card.relevance_score
            for card in (context_pack.cards if context_pack else [])
        ]
        avg_relevance = sum(scores) / len(scores) if scores else 0.0

        signal_coverage = min(1.0, len(selected_projects) / 3.0)
        explanation_mentions_project = (
            bool(selected_projects)
            and bool(explanation)
            and any(project.get("title", "") in explanation for project in selected_projects)
        )
        checks = {
            "schema_validity": "passed",
            "provenance_completeness": "passed"
            if provenance_ratio >= thresholds["min_provenance_completeness_ratio"]
            else "failed",
            "retrieval_relevance": "passed"
            if avg_relevance >= thresholds["min_retrieval_relevance"]
            else "failed",
            "signal_coverage": "passed"
            if signal_coverage >= thresholds["min_signal_coverage"]
            else "failed",
            "explanation_project_consistency": "passed" if explanation_mentions_project else "failed",
        }
        failed_checks = [name for name, status in checks.items() if status == "failed"]
        remediation: list[str] = []
        if "provenance_completeness" in failed_checks:
            remediation.append("Increase trusted-source retrieval and enforce citation URI presence.")
        if "retrieval_relevance" in failed_checks:
            remediation.append("Adjust query terms and raise lexical/semantic overlap quality.")
        if "signal_coverage" in failed_checks:
            remediation.append("Ensure selection covers at least 60% of required signal slots.")
        if "explanation_project_consistency" in failed_checks:
            remediation.append("Regenerate explanation from selected project titles only.")

        return EvaluationReport(
            status="failed" if failed_checks else "passed",
            checks=checks,
            thresholds=thresholds,
            metrics={
                "provenance_completeness_ratio": provenance_ratio,
                "avg_relevance_score": avg_relevance,
                "signal_coverage_ratio": signal_coverage,
                "retrieval_returned_count": float(retrieval_diagnostics.get("returned_result_count", 0)),
            },
            failed_checks=failed_checks,
            remediation_hints=remediation,
        )
