"""Workflow node implementations for recommendation execution."""

from dataclasses import dataclass, field
from typing import Any

from src.llm.explanation_generator import ExplanationGenerator
from src.llm.recommendation_generator import RecommendationGenerator
from src.ranking.project_filters import ProjectFilter
from src.ranking.project_scorer import ProjectScorer, ScoredProject
from src.ranking.project_selector import ProjectSelector
from src.schemas.domain import (
    EvidenceBundle,
    EvidenceItem,
    PrioritySignal,
    RankingBreakdown,
    RecommendationCandidate,
    ValidationReport,
)
from src.schemas.retrieval import RetrievalResponse
from src.schemas.workflow import ContextPack, NarrativeExplanationOutput, RetrievalPlan
from src.services.context_packer import ContextPacker
from src.services.evidence_bundle import EvidenceBundleService
from src.services.municipality_profile_service import MunicipalityProfileService
from src.services.query_planner import QueryPlanner
from src.storage.projects import InMemoryProjectRepository
from src.retrieval.service import RetrievalService
from src.validation.run_validator import RunValidator
from src.validation.strict_gate import StrictEvaluationGate


@dataclass
class WorkflowContext:
    """Class representing WorkflowContext."""
    run_id: str
    request: dict[str, Any]
    retrieval_plan: RetrievalPlan | None = None
    retrieval_response: RetrievalResponse | None = None
    retrieval_diagnostics: dict[str, object] = field(default_factory=dict)
    context_pack: ContextPack | None = None
    web_evidence: list[EvidenceItem] = field(default_factory=list)
    evidence_bundle: EvidenceBundle | None = None
    recommendation_candidates: list[RecommendationCandidate] = field(default_factory=list)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    ranking_breakdowns: list[RankingBreakdown] = field(default_factory=list)
    scored_projects: list[ScoredProject] = field(default_factory=list)
    excluded_projects: list[dict[str, Any]] = field(default_factory=list)
    selected_projects: list[dict[str, Any]] = field(default_factory=list)
    narrative_explanation: NarrativeExplanationOutput | None = None
    explanation: str = ""
    validation_summary: str = "not_validated"
    node_outputs: dict[str, Any] = field(default_factory=dict)


class RecommendationNodes:
    """Class representing RecommendationNodes."""
    def __init__(
        self,
        *,
        municipality_profile_service: MunicipalityProfileService,
        retrieval_service: RetrievalService,
        evidence_bundle_service: EvidenceBundleService,
        project_repository: InMemoryProjectRepository,
        query_planner: QueryPlanner,
        context_packer: ContextPacker,
        strict_evaluation_gate: StrictEvaluationGate,
        run_validator: RunValidator,
        recommendation_generator: RecommendationGenerator,
        explanation_generator: ExplanationGenerator,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._municipality_profile_service = municipality_profile_service
        self._retrieval_service = retrieval_service
        self._evidence_bundle_service = evidence_bundle_service
        self._project_repository = project_repository
        self._query_planner = query_planner
        self._context_packer = context_packer
        self._strict_evaluation_gate = strict_evaluation_gate
        self._run_validator = run_validator
        self._recommendation_generator = recommendation_generator
        self._explanation_generator = explanation_generator
        self._project_filter = ProjectFilter()
        self._project_scorer = ProjectScorer()
        self._project_selector = ProjectSelector()

    def create_run(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Create run."""
        return {"message": "Run context initialized."}

    def resolve_request_context(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Handle resolve request context."""
        return {
            "municipality_id": str(ctx.request["municipality_id"]),
            "category": str(ctx.request["category"]),
            "year": int(ctx.request["year"]),
            "include_web_evidence": bool(ctx.request.get("include_web_evidence", False)),
        }

    def compute_indicator_analysis(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Compute indicator analysis."""
        municipality_id = str(ctx.request["municipality_id"])
        category = str(ctx.request["category"])
        year = int(ctx.request["year"])
        signals = self._municipality_profile_service.compute_priority_signals(
            municipality_id=municipality_id,
            category=category,
            year=year,
            top_n=max(3, int(ctx.request.get("top_n_projects", 3))),
        )
        ctx.node_outputs["priority_signals"] = [signal.model_dump(mode="json") for signal in signals]
        return {"signal_count": len(signals)}

    def plan_retrieval(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Handle plan retrieval."""
        priority_signals = list(ctx.node_outputs.get("priority_signals", []))
        plan = self._query_planner.build_retrieval_plan(
            municipality_id=str(ctx.request["municipality_id"]),
            category=str(ctx.request["category"]),
            year=int(ctx.request["year"]),
            priority_signals=priority_signals,
            top_k=8,
        )
        ctx.retrieval_plan = plan
        return {
            "intent_query": plan.intent_query,
            "evidence_query": plan.evidence_query,
            "constraint_query": plan.constraint_query,
            "query_terms": plan.query_terms,
            "filters": plan.filters,
        }

    def retrieve_local_evidence(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Handle retrieve local evidence."""
        if ctx.retrieval_plan is None:
            raise ValueError("retrieval plan not available")

        response = self._retrieval_service.search(
            query=ctx.retrieval_plan.query,
            mode=ctx.retrieval_plan.retrieval_mode,
            top_k=ctx.retrieval_plan.top_k,
            municipality_id=ctx.retrieval_plan.municipality_id,
            category=ctx.retrieval_plan.category,
        )
        ctx.retrieval_response = response
        ctx.retrieval_diagnostics = response.diagnostics
        return {
            "retrieval_mode": response.mode,
            "result_count": response.total_results,
            "diagnostics": response.diagnostics,
        }

    def optionally_retrieve_web_evidence(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Handle optionally retrieve web evidence."""
        if not bool(ctx.request.get("include_web_evidence", False)):
            return {"web_evidence_enabled": False, "result_count": 0}

        placeholder = EvidenceItem(
            evidence_id=f"web:{ctx.run_id}",
            origin="web_research",
            statement=(
                "Web research placeholder entry. Policy-controlled live web enrichment "
                "will be integrated in a later batch."
            ),
            confidence=0.2,
            source_id="web-placeholder",
            municipality_id=str(ctx.request["municipality_id"]),
            category=str(ctx.request["category"]),
        )
        ctx.web_evidence = [placeholder]
        return {"web_evidence_enabled": True, "result_count": 1}

    def build_evidence_bundle(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Build evidence bundle."""
        signals_data = ctx.node_outputs.get("priority_signals", [])
        if ctx.retrieval_response is None:
            raise ValueError("local retrieval must run before building evidence bundle")

        from src.schemas.domain import PrioritySignal

        signals = [PrioritySignal.model_validate(item) for item in signals_data]
        bundle = self._evidence_bundle_service.build_bundle(
            municipality_id=str(ctx.request["municipality_id"]),
            category=str(ctx.request["category"]),
            priority_signals=signals,
            retrieval_results=ctx.retrieval_response.results,
            web_evidence=ctx.web_evidence,
        )
        context_pack = self._context_packer.build_context_pack(
            run_id=ctx.run_id,
            municipality_id=str(ctx.request["municipality_id"]),
            category=str(ctx.request["category"]),
            retrieval_results=ctx.retrieval_response.results,
            token_budget_per_card=120,
            max_cards=8,
        )
        ctx.evidence_bundle = bundle
        ctx.context_pack = context_pack
        return {
            "bundle_id": bundle.bundle_id,
            "item_count": len(bundle.items),
            "evidence_items": [item.model_dump(mode="json") for item in bundle.items],
            "context_pack_summary": {
                "card_count": len(context_pack.cards),
                "provenance_completeness_ratio": context_pack.provenance_completeness_ratio,
            },
        }

    def generate_recommendation_candidates(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Generate recommendation candidates."""
        if ctx.evidence_bundle is None:
            raise ValueError("evidence bundle must exist before candidate generation")
        if ctx.context_pack is None:
            raise ValueError("context pack must exist before candidate generation")

        generation_output = self._recommendation_generator.generate(
            request=dict(ctx.request),
            priority_signals=list(ctx.node_outputs.get("priority_signals", [])),
            evidence_bundle=ctx.evidence_bundle.model_dump(mode="json"),
            context_pack=ctx.context_pack.model_dump(mode="json"),
            top_n_projects=int(ctx.request.get("top_n_projects", 3)),
            language=str(ctx.request.get("language", "en")),
        )

        ctx.recommendation_candidates = generation_output.candidates
        return {
            "candidate_count": len(generation_output.candidates),
            "candidates": [candidate.model_dump(mode="json") for candidate in generation_output.candidates],
            "model_name": generation_output.model_name,
            "prompt_version": generation_output.prompt_version,
        }

    def rank_candidates(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Handle rank candidates."""
        if ctx.evidence_bundle is None:
            raise ValueError("evidence bundle must exist before ranking")

        category = str(ctx.request["category"])
        municipality_id = str(ctx.request["municipality_id"])
        projects = self._project_repository.list_by_category(category)
        filtered_projects = self._project_filter.filter_projects(
            projects=projects,
            municipality_id=municipality_id,
            category=category,
        )
        priority_signals = [
            PrioritySignal.model_validate(item) for item in ctx.node_outputs.get("priority_signals", [])
        ]
        scored_projects = self._project_scorer.score_projects(
            filtered_projects=filtered_projects,
            recommendation_candidates=ctx.recommendation_candidates,
            priority_signals=priority_signals,
            evidence_bundle=ctx.evidence_bundle,
            municipality_id=municipality_id,
        )
        ordered_projects = sorted(
            scored_projects,
            key=lambda item: (
                bool(item.exclusion_reasons),
                -item.total_score,
                item.project_id,
                item.title,
            ),
        )
        ctx.ranking = [
            {
                "project_id": item.project_id,
                "title": item.title,
                "category": item.category,
                "candidate_id": item.matched_candidate_id,
                "score": item.total_score,
                "exclusion_reasons": item.exclusion_reasons,
                "missing_information_flags": item.missing_information_flags,
                "ranking_breakdown": item.ranking_breakdown.model_dump(mode="json"),
            }
            for item in ordered_projects
        ]
        ctx.scored_projects = ordered_projects
        ctx.ranking_breakdowns = [item.ranking_breakdown for item in ordered_projects]
        ctx.excluded_projects = [
            {
                "project_id": item.project_id,
                "title": item.title,
                "category": item.category,
                "candidate_id": item.matched_candidate_id,
                "exclusion_reasons": item.exclusion_reasons,
                "missing_information_flags": item.missing_information_flags,
                "ranking_breakdown": item.ranking_breakdown.model_dump(mode="json"),
            }
            for item in ordered_projects
            if item.exclusion_reasons
        ]
        top_score = max((item.total_score for item in ordered_projects if not item.exclusion_reasons), default=0.0)
        return {
            "ranked_count": len(ctx.ranking),
            "eligible_count": len([item for item in ordered_projects if not item.exclusion_reasons]),
            "excluded_count": len(ctx.excluded_projects),
            "top_score": top_score,
        }

    def select_projects(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Select projects."""
        if not ctx.scored_projects:
            raise ValueError("ranking outputs must exist before project selection")

        top_n = int(ctx.request.get("top_n_projects", 3))
        selected_scored, excluded_scored = self._project_selector.select_projects(
            scored_projects=ctx.scored_projects,
            top_n=top_n,
        )

        ctx.selected_projects = [
            {
                "project_id": item.project_id,
                "title": item.title,
                "category": item.category,
                "municipality_id": item.municipality_id,
                "ranking_score": item.total_score,
                "candidate_id": item.matched_candidate_id,
                "ranking_breakdown": item.ranking_breakdown.model_dump(mode="json"),
                "missing_information_flags": item.missing_information_flags,
                "exclusion_reasons": item.exclusion_reasons,
            }
            for item in selected_scored
        ]
        ctx.excluded_projects = [
            {
                "project_id": item.project_id,
                "title": item.title,
                "category": item.category,
                "municipality_id": item.municipality_id,
                "candidate_id": item.matched_candidate_id,
                "ranking_breakdown": item.ranking_breakdown.model_dump(mode="json"),
                "missing_information_flags": item.missing_information_flags,
                "exclusion_reasons": item.exclusion_reasons,
            }
            for item in excluded_scored
        ]
        return {"selected_count": len(ctx.selected_projects), "excluded_count": len(ctx.excluded_projects)}

    def generate_explanation(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Generate explanation."""
        if ctx.evidence_bundle is None:
            raise ValueError("evidence bundle must exist before explanation generation")

        explanation_output = self._explanation_generator.generate(
            request=dict(ctx.request),
            recommendation_candidates=[candidate.model_dump(mode="json") for candidate in ctx.recommendation_candidates],
            selected_projects=ctx.selected_projects,
            excluded_projects=ctx.excluded_projects,
            evidence_bundle=ctx.evidence_bundle.model_dump(mode="json"),
            ranking=ctx.ranking,
        )
        ctx.narrative_explanation = explanation_output
        caveat_text = (
            "\nCaveats: " + "; ".join(explanation_output.caveats)
            if explanation_output.caveats
            else ""
        )
        evidence_text = (
            "\nEvidence: " + ", ".join(explanation_output.cited_evidence_ids)
            if explanation_output.cited_evidence_ids
            else ""
        )
        ctx.explanation = (
            f"{explanation_output.executive_summary}\n\n"
            f"Rationale: {explanation_output.rationale}"
            f"{caveat_text}"
            f"{evidence_text}"
        )
        return {
            "summary_length": len(ctx.explanation),
            "executive_summary": explanation_output.executive_summary,
            "rationale": explanation_output.rationale,
            "caveats": explanation_output.caveats,
            "cited_evidence_ids": explanation_output.cited_evidence_ids,
        }

    def validate_output(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Validate output."""
        strict_report = self._strict_evaluation_gate.evaluate(
            context_pack=ctx.context_pack,
            selected_projects=ctx.selected_projects,
            explanation=ctx.explanation,
            retrieval_diagnostics=ctx.retrieval_diagnostics,
        )
        checks = {
            "has_selected_projects": "passed" if ctx.selected_projects else "failed",
            "has_evidence_bundle": "passed" if ctx.evidence_bundle else "failed",
            "has_explanation": "passed" if ctx.explanation else "failed",
        }
        base_status = "passed" if all(value == "passed" for value in checks.values()) else "failed"
        structural_report = ValidationReport(
            run_id=ctx.run_id,
            status="passed" if (base_status == "passed" and strict_report.status == "passed") else "failed",
            checks=checks,
            warnings=[] if strict_report.status == "passed" else strict_report.remediation_hints,
            errors=strict_report.failed_checks,
            failure_policy="fail_run" if strict_report.status == "failed" else "none",
        )
        run_report = self._run_validator.validate(
            run_id=ctx.run_id,
            request_context=dict(ctx.request),
            recommendation_candidates=[candidate.model_dump(mode="json") for candidate in ctx.recommendation_candidates],
            selected_projects=ctx.selected_projects,
            excluded_projects=ctx.excluded_projects,
            evidence_ids={item.evidence_id for item in (ctx.evidence_bundle.items if ctx.evidence_bundle else [])},
            explanation_output=ctx.narrative_explanation,
        )
        merged_checks = {**checks, **run_report.checks}
        merged_warnings = [*structural_report.warnings, *run_report.warnings]
        merged_errors = [*structural_report.errors, *run_report.errors]
        merged_status = "failed"
        if structural_report.status != "failed" and run_report.status == "warning":
            merged_status = "warning"
        elif structural_report.status == "passed" and run_report.status == "passed":
            merged_status = "passed"
        report = ValidationReport(
            run_id=ctx.run_id,
            status=merged_status,
            checks=merged_checks,
            warnings=merged_warnings,
            errors=merged_errors,
            failure_policy=(
                "fail_run"
                if structural_report.failure_policy == "fail_run" or run_report.failure_policy == "fail_run"
                else run_report.failure_policy
            ),
            metadata={
                "evaluation_report_status": strict_report.status,
                "recommended_failure_policy": run_report.failure_policy,
                **run_report.metadata,
            },
        )
        ctx.validation_summary = report.status
        return {
            "validation_report": report.model_dump(mode="json"),
            "evaluation_report": strict_report.model_dump(mode="json"),
        }

    def finalize_run(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Handle finalize run."""
        validate_node_output = ctx.node_outputs.get("validate_output", {})
        evaluation_report = validate_node_output.get("evaluation_report", {})
        return {
            "municipality_id": str(ctx.request["municipality_id"]),
            "category": str(ctx.request["category"]),
            "indicator_summary": ctx.node_outputs.get("priority_signals", []),
            "recommendation_candidates": [
                candidate.model_dump(mode="json") for candidate in ctx.recommendation_candidates
            ],
            "ranking": ctx.ranking,
            "selected_projects": ctx.selected_projects,
            "explanation": ctx.explanation,
            "explanation_narrative": (
                ctx.narrative_explanation.model_dump(mode="json") if ctx.narrative_explanation else {}
            ),
            "evidence_bundle_id": ctx.evidence_bundle.bundle_id if ctx.evidence_bundle else None,
            "evidence_bundle_summary": {
                "bundle_id": ctx.evidence_bundle.bundle_id if ctx.evidence_bundle else None,
                "item_count": len(ctx.evidence_bundle.items) if ctx.evidence_bundle else 0,
                "evidence_items": [
                    item.model_dump(mode="json") for item in (ctx.evidence_bundle.items if ctx.evidence_bundle else [])
                ],
            },
            "citations": ctx.narrative_explanation.cited_evidence_ids if ctx.narrative_explanation else [],
            "validation_summary": ctx.validation_summary,
            "validation_report": validate_node_output.get("validation_report", {}),
            "context_pack_summary": {
                "card_count": len(ctx.context_pack.cards) if ctx.context_pack else 0,
                "provenance_completeness_ratio": (
                    ctx.context_pack.provenance_completeness_ratio if ctx.context_pack else 0.0
                ),
            },
            "retrieval_diagnostics": ctx.retrieval_diagnostics,
            "evaluation_report": evaluation_report,
            "excluded_projects": ctx.excluded_projects,
            "node_outputs": dict(ctx.node_outputs),
        }
