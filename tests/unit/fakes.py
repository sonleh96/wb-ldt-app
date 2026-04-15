from src.schemas.domain import ProjectReview
from src.schemas.workflow import NarrativeExplanationOutput, RecommendationGenerationOutput


class FakeRecommendationGenerator:
    def generate(
        self,
        *,
        request: dict[str, object],
        priority_signals: list[dict[str, object]],
        evidence_bundle: dict[str, object],
        context_pack: dict[str, object],
        top_n_projects: int,
        language: str,
    ) -> RecommendationGenerationOutput:
        evidence_items = evidence_bundle.get("items", [])
        supporting_evidence_ids = [
            str(item["evidence_id"]) for item in evidence_items[:2] if "evidence_id" in item
        ] or ["analytics:default"]
        category = str(request["category"])
        candidates = []
        for index in range(top_n_projects):
            candidates.append(
                {
                    "candidate_id": f"llm-{index + 1}",
                    "title": f"{category} Candidate {index + 1}",
                    "summary": f"Generated candidate {index + 1} for {category}.",
                    "problem_statement": f"{category} service gaps remain unresolved.",
                    "intended_outcome": f"Improve {category} service delivery.",
                    "category": category,
                    "public_investment_type": "capital_program",
                    "supporting_evidence_ids": supporting_evidence_ids,
                    "confidence": 0.82,
                    "caveats": [f"Generated in language={language}."],
                }
            )

        return RecommendationGenerationOutput(
            candidates=candidates,
            model_name="fake-model",
            prompt_version="recommendation_candidates.v1",
        )


class FailingRecommendationGenerator:
    def generate(
        self,
        *,
        request: dict[str, object],
        priority_signals: list[dict[str, object]],
        evidence_bundle: dict[str, object],
        context_pack: dict[str, object],
        top_n_projects: int,
        language: str,
    ) -> RecommendationGenerationOutput:
        raise RuntimeError("synthetic generation failure")


class FakeExplanationGenerator:
    def generate(
        self,
        *,
        request: dict[str, object],
        recommendation_candidates: list[dict[str, object]],
        selected_projects: list[dict[str, object]],
        excluded_projects: list[dict[str, object]],
        evidence_bundle: dict[str, object],
        ranking: list[dict[str, object]],
    ) -> NarrativeExplanationOutput:
        selected_title = str(selected_projects[0]["title"])
        evidence_ids = [str(item["evidence_id"]) for item in evidence_bundle.get("items", [])[:2]]
        return NarrativeExplanationOutput(
            executive_summary=(
                f"{selected_title} is the leading recommendation for {request['municipality_id']} "
                f"in {request['category']}."
            ),
            rationale=(
                f"{selected_title} ranks highest because it aligns with the strongest evidence "
                f"and deterministic scoring signals."
            ),
            caveats=["Readiness and financing assumptions should be verified before commitment."],
            cited_evidence_ids=evidence_ids,
        )


class FailingExplanationGenerator:
    def generate(
        self,
        *,
        request: dict[str, object],
        recommendation_candidates: list[dict[str, object]],
        selected_projects: list[dict[str, object]],
        excluded_projects: list[dict[str, object]],
        evidence_bundle: dict[str, object],
        ranking: list[dict[str, object]],
    ) -> NarrativeExplanationOutput:
        raise RuntimeError("synthetic explanation failure")


class FakeProjectReviewGenerator:
    def generate(
        self,
        *,
        run_context: dict[str, object],
        project: dict[str, object],
        review_evidence: list[dict[str, object]],
    ) -> ProjectReview:
        return ProjectReview(
            project_id=str(project["project_id"]),
            summary=f"{project['title']} is suitable for detailed follow-up.",
            municipality_relevance=(
                f"{project['title']} aligns with {run_context['municipality_id']} in {run_context['category']}."
            ),
            readiness="Moderate readiness based on current project metadata.",
            financing_signals="Capital-program financing path appears plausible.",
            implementation_considerations=["Confirm delivery sequencing.", "Validate execution dependencies."],
            risks_and_caveats=["Review evidence is limited and should be expanded before approval."],
            citation_ids=[str(item["evidence_id"]) for item in review_evidence[:2]],
        )


class FailingProjectReviewGenerator:
    def generate(
        self,
        *,
        run_context: dict[str, object],
        project: dict[str, object],
        review_evidence: list[dict[str, object]],
    ) -> ProjectReview:
        raise RuntimeError("synthetic project review failure")
