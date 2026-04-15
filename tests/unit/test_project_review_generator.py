from types import SimpleNamespace

import pytest

from src.llm.project_review_generator import ProjectReviewGenerationError, ProjectReviewGenerator


class FakeResponsesApi:
    def __init__(self, parsed_output: object) -> None:
        self._parsed_output = parsed_output

    def parse(self, **kwargs) -> object:
        return SimpleNamespace(output_parsed=self._parsed_output)


class FakeOpenAIClient:
    def __init__(self, parsed_output: object) -> None:
        self.responses = FakeResponsesApi(parsed_output)


def test_project_review_generator_accepts_grounded_structured_output() -> None:
    generator = ProjectReviewGenerator(
        model_name="gpt-test",
        prompt_version="project_reviews.v1",
        client=FakeOpenAIClient(
            {
                "project_id": "wrong-id",
                "summary": "Urban Air Monitoring Expansion is a strong review candidate.",
                "municipality_relevance": "It addresses environmental monitoring needs.",
                "readiness": "Moderate readiness.",
                "financing_signals": "Financing looks plausible.",
                "implementation_considerations": ["Coordinate deployment."],
                "risks_and_caveats": ["Evidence set is still small."],
                "citation_ids": ["review:proj-001:1"],
            }
        ),
    )

    review = generator.generate(
        run_context={"run_id": "run-1"},
        project={"project_id": "proj-001", "title": "Urban Air Monitoring Expansion"},
        review_evidence=[
            {"evidence_id": "review:proj-001:1", "statement": "Monitoring expansion is supported."}
        ],
    )

    assert review.project_id == "proj-001"
    assert review.citation_ids == ["review:proj-001:1"]


def test_project_review_generator_rejects_unknown_evidence_ids() -> None:
    generator = ProjectReviewGenerator(
        model_name="gpt-test",
        prompt_version="project_reviews.v1",
        client=FakeOpenAIClient(
            {
                "project_id": "proj-001",
                "summary": "Summary",
                "municipality_relevance": "Relevant",
                "readiness": "Moderate",
                "financing_signals": "Plausible",
                "implementation_considerations": ["Coordinate deployment."],
                "risks_and_caveats": ["Evidence set is still small."],
                "citation_ids": ["missing:evidence"],
            }
        ),
    )

    with pytest.raises(ProjectReviewGenerationError, match="unknown evidence ids"):
        generator.generate(
            run_context={"run_id": "run-1"},
            project={"project_id": "proj-001", "title": "Urban Air Monitoring Expansion"},
            review_evidence=[
                {"evidence_id": "review:proj-001:1", "statement": "Monitoring expansion is supported."}
            ],
        )
