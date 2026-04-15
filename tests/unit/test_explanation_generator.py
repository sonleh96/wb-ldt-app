from types import SimpleNamespace

import pytest

from src.llm.explanation_generator import ExplanationGenerationError, ExplanationGenerator


class FakeResponsesApi:
    def __init__(self, parsed_output: object) -> None:
        self._parsed_output = parsed_output

    def parse(self, **kwargs) -> object:
        return SimpleNamespace(output_parsed=self._parsed_output)


class FakeOpenAIClient:
    def __init__(self, parsed_output: object) -> None:
        self.responses = FakeResponsesApi(parsed_output)


def _sample_evidence_bundle() -> dict[str, object]:
    return {
        "bundle_id": "bundle-1",
        "items": [
            {"evidence_id": "analytics:air-quality"},
            {"evidence_id": "local:policy-1"},
        ],
    }


def test_explanation_generator_accepts_grounded_structured_output() -> None:
    generator = ExplanationGenerator(
        model_name="gpt-test",
        prompt_version="explanations.v1",
        client=FakeOpenAIClient(
            {
                "executive_summary": "Urban Air Monitoring Expansion is the best-fit project.",
                "rationale": "Urban Air Monitoring Expansion aligns with air-quality evidence and ranking signals.",
                "caveats": ["Readiness assumptions should be verified."],
                "cited_evidence_ids": ["analytics:air-quality", "local:policy-1"],
            }
        ),
    )

    output = generator.generate(
        request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
        recommendation_candidates=[{"candidate_id": "cand-1", "title": "Air Monitoring"}],
        selected_projects=[{"project_id": "proj-001", "title": "Urban Air Monitoring Expansion"}],
        excluded_projects=[],
        evidence_bundle=_sample_evidence_bundle(),
        ranking=[{"project_id": "proj-001", "score": 0.9}],
    )

    assert output.executive_summary.startswith("Urban Air Monitoring Expansion")
    assert output.cited_evidence_ids == ["analytics:air-quality", "local:policy-1"]


def test_explanation_generator_rejects_unknown_evidence_ids() -> None:
    generator = ExplanationGenerator(
        model_name="gpt-test",
        prompt_version="explanations.v1",
        client=FakeOpenAIClient(
            {
                "executive_summary": "Urban Air Monitoring Expansion is the best-fit project.",
                "rationale": "Urban Air Monitoring Expansion aligns with evidence.",
                "caveats": [],
                "cited_evidence_ids": ["missing:evidence-id"],
            }
        ),
    )

    with pytest.raises(ExplanationGenerationError, match="unknown evidence ids"):
        generator.generate(
            request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
            recommendation_candidates=[{"candidate_id": "cand-1", "title": "Air Monitoring"}],
            selected_projects=[{"project_id": "proj-001", "title": "Urban Air Monitoring Expansion"}],
            excluded_projects=[],
            evidence_bundle=_sample_evidence_bundle(),
            ranking=[{"project_id": "proj-001", "score": 0.9}],
        )


def test_explanation_generator_requires_selected_project_titles_in_output() -> None:
    generator = ExplanationGenerator(
        model_name="gpt-test",
        prompt_version="explanations.v1",
        client=FakeOpenAIClient(
            {
                "executive_summary": "This recommendation is strong.",
                "rationale": "It aligns with evidence.",
                "caveats": [],
                "cited_evidence_ids": ["analytics:air-quality"],
            }
        ),
    )

    with pytest.raises(ExplanationGenerationError, match="selected project title"):
        generator.generate(
            request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
            recommendation_candidates=[{"candidate_id": "cand-1", "title": "Air Monitoring"}],
            selected_projects=[{"project_id": "proj-001", "title": "Urban Air Monitoring Expansion"}],
            excluded_projects=[],
            evidence_bundle=_sample_evidence_bundle(),
            ranking=[{"project_id": "proj-001", "score": 0.9}],
        )
