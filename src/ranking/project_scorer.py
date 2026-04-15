"""Deterministic project scoring and ranking breakdown generation."""

from __future__ import annotations

from dataclasses import dataclass

from src.ranking.project_filters import FilteredProject
from src.schemas.domain import EvidenceBundle, PrioritySignal, RankingBreakdown, RecommendationCandidate


WEIGHTS = {
    "municipality_fit": 0.2,
    "indicator_alignment": 0.25,
    "development_plan_alignment": 0.15,
    "readiness": 0.15,
    "financing_plausibility": 0.1,
    "evidence_support_strength": 0.15,
}


@dataclass(frozen=True)
class ScoredProject:
    """Project ranking output with matched candidate and diagnostics."""

    project_id: str
    title: str
    category: str
    municipality_id: str | None
    matched_candidate_id: str | None
    total_score: float
    ranking_breakdown: RankingBreakdown
    exclusion_reasons: list[str]
    missing_information_flags: list[str]


class ProjectScorer:
    """Score projects deterministically against recommendation candidates and evidence."""

    def score_projects(
        self,
        *,
        filtered_projects: list[FilteredProject],
        recommendation_candidates: list[RecommendationCandidate],
        priority_signals: list[PrioritySignal],
        evidence_bundle: EvidenceBundle,
        municipality_id: str,
    ) -> list[ScoredProject]:
        """Return deterministic ranking outputs for each filtered project."""

        evidence_ids = {item.evidence_id for item in evidence_bundle.items}
        total_evidence_count = max(1, len(evidence_ids))
        scored_projects: list[ScoredProject] = []

        for filtered_project in filtered_projects:
            project = filtered_project.project
            project_keywords = self._keyword_set(project)
            best_candidate: RecommendationCandidate | None = None
            best_indicator_alignment = 0.0
            best_evidence_support = 0.0

            for candidate in recommendation_candidates:
                candidate_keywords = self._candidate_keyword_set(candidate, priority_signals)
                overlap = len(project_keywords & candidate_keywords)
                denominator = max(1, len(project_keywords | candidate_keywords))
                indicator_alignment = overlap / denominator

                evidence_overlap = len(set(candidate.supporting_evidence_ids) & evidence_ids)
                evidence_support = min(
                    1.0,
                    (evidence_overlap / total_evidence_count) * 2.0 * max(candidate.confidence, 0.1),
                )

                if (
                    indicator_alignment > best_indicator_alignment
                    or (
                        indicator_alignment == best_indicator_alignment
                        and evidence_support > best_evidence_support
                    )
                ):
                    best_candidate = candidate
                    best_indicator_alignment = indicator_alignment
                    best_evidence_support = evidence_support

            municipality_fit = 1.0 if project.municipality_id in {None, municipality_id} else 0.0
            development_plan_alignment = self._bounded_float(
                project.metadata.get("development_plan_alignment"), fallback=0.5
            )
            readiness = self._status_adjusted_readiness(project.status, project.metadata.get("readiness"))
            financing_plausibility = self._financing_score(
                project.metadata.get("financing_plausibility"),
                best_candidate.public_investment_type if best_candidate else None,
                project.metadata.get("public_investment_types"),
            )

            total_score = 0.0 if filtered_project.is_excluded else round(
                (
                    municipality_fit * WEIGHTS["municipality_fit"]
                    + best_indicator_alignment * WEIGHTS["indicator_alignment"]
                    + development_plan_alignment * WEIGHTS["development_plan_alignment"]
                    + readiness * WEIGHTS["readiness"]
                    + financing_plausibility * WEIGHTS["financing_plausibility"]
                    + best_evidence_support * WEIGHTS["evidence_support_strength"]
                ),
                4,
            )

            breakdown = RankingBreakdown(
                project_id=project.project_id,
                total_score=total_score,
                municipality_fit=round(municipality_fit, 4),
                indicator_alignment=round(best_indicator_alignment, 4),
                development_plan_alignment=round(development_plan_alignment, 4),
                readiness=round(readiness, 4),
                financing_plausibility=round(financing_plausibility, 4),
                evidence_support_strength=round(best_evidence_support, 4),
                exclusion_reasons=filtered_project.exclusion_reasons,
            )
            scored_projects.append(
                ScoredProject(
                    project_id=project.project_id,
                    title=project.title,
                    category=project.category,
                    municipality_id=project.municipality_id,
                    matched_candidate_id=best_candidate.candidate_id if best_candidate else None,
                    total_score=total_score,
                    ranking_breakdown=breakdown,
                    exclusion_reasons=filtered_project.exclusion_reasons,
                    missing_information_flags=filtered_project.missing_information_flags,
                )
            )

        return scored_projects

    def _keyword_set(self, project) -> set[str]:
        """Return normalized keywords for a project."""

        keywords = set(str(value).lower() for value in project.metadata.get("indicator_keywords", []))
        keywords.update(project.title.lower().replace("-", " ").split())
        keywords.update(project.description.lower().replace("-", " ").split())
        return keywords

    def _candidate_keyword_set(
        self,
        candidate: RecommendationCandidate,
        priority_signals: list[PrioritySignal],
    ) -> set[str]:
        """Return normalized keywords for a recommendation candidate."""

        keywords = set(candidate.title.lower().replace("-", " ").split())
        keywords.update(candidate.summary.lower().replace("-", " ").split())
        keywords.update(candidate.problem_statement.lower().replace("-", " ").split())
        keywords.update(candidate.intended_outcome.lower().replace("-", " ").split())
        signal_lookup = {signal.indicator_id: signal for signal in priority_signals}
        for evidence_id in candidate.supporting_evidence_ids:
            indicator_id = evidence_id.split("analytics:", 1)[-1] if evidence_id.startswith("analytics:") else None
            if indicator_id and indicator_id in signal_lookup:
                keywords.add(signal_lookup[indicator_id].indicator_id.lower())
                keywords.update(signal_lookup[indicator_id].indicator_name.lower().replace("-", " ").split())
        return keywords

    def _bounded_float(self, value: object, *, fallback: float) -> float:
        """Return a numeric value constrained to the 0..1 range."""

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, numeric))

    def _status_adjusted_readiness(self, status: str, raw_readiness: object) -> float:
        """Return readiness adjusted by project status."""

        base = self._bounded_float(raw_readiness, fallback=0.4)
        status_multiplier = {
            "pipeline": 0.9,
            "concept": 0.65,
            "ready": 1.0,
            "cancelled": 0.0,
        }.get(status.lower(), 0.75)
        return max(0.0, min(1.0, base * status_multiplier))

    def _financing_score(
        self,
        raw_financing: object,
        candidate_investment_type: str | None,
        supported_investment_types: object,
    ) -> float:
        """Return financing plausibility, penalizing incompatible investment types."""

        base = self._bounded_float(raw_financing, fallback=0.5)
        allowed_types = {str(item) for item in (supported_investment_types or [])}
        if candidate_investment_type and allowed_types and candidate_investment_type not in allowed_types:
            return max(0.0, base - 0.35)
        return base
