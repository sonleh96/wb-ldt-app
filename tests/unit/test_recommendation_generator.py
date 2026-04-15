from types import SimpleNamespace

import pytest

from src.llm.recommendation_generator import RecommendationGenerationError, RecommendationGenerator


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


def _sample_context_pack() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "cards": [{"card_id": "card-1", "claim_text": "Claim"}],
        "max_cards": 8,
        "token_budget_per_card": 120,
        "provenance_completeness_ratio": 1.0,
        "diagnostics": {},
    }


def test_recommendation_generator_normalizes_candidates_and_metadata() -> None:
    generator = RecommendationGenerator(
        model_name="gpt-test",
        prompt_version="recommendation_candidates.v1",
        client=FakeOpenAIClient(
            {
                "candidates": [
                    {
                        "candidate_id": "model-supplied-id",
                        "title": "Air Quality Upgrade",
                        "summary": "Improve environmental outcomes.",
                        "problem_statement": "Air quality remains below target.",
                        "intended_outcome": "Reduce exposure to pollution.",
                        "category": "Environment",
                        "public_investment_type": "capital_program",
                        "supporting_evidence_ids": ["analytics:air-quality", "local:policy-1"],
                        "confidence": 0.91,
                        "caveats": ["Requires procurement planning."],
                    }
                ]
            }
        ),
    )

    output = generator.generate(
        request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
        priority_signals=[{"indicator_id": "air-quality", "indicator_name": "Air Quality"}],
        evidence_bundle=_sample_evidence_bundle(),
        context_pack=_sample_context_pack(),
        top_n_projects=1,
        language="en",
    )

    assert output.model_name == "gpt-test"
    assert output.prompt_version == "recommendation_candidates.v1"
    assert output.candidates[0].candidate_id == "cand-1"
    assert output.candidates[0].supporting_evidence_ids == ["analytics:air-quality", "local:policy-1"]


def test_recommendation_generator_rejects_empty_candidates() -> None:
    generator = RecommendationGenerator(
        model_name="gpt-test",
        prompt_version="recommendation_candidates.v1",
        client=FakeOpenAIClient({"candidates": []}),
    )

    with pytest.raises(RecommendationGenerationError, match="returned no candidates"):
        generator.generate(
            request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
            priority_signals=[],
            evidence_bundle=_sample_evidence_bundle(),
            context_pack=_sample_context_pack(),
            top_n_projects=1,
            language="en",
        )


def test_recommendation_generator_rejects_unknown_evidence_ids() -> None:
    generator = RecommendationGenerator(
        model_name="gpt-test",
        prompt_version="recommendation_candidates.v1",
        client=FakeOpenAIClient(
            {
                "candidates": [
                    {
                        "candidate_id": "model-supplied-id",
                        "title": "Air Quality Upgrade",
                        "summary": "Improve environmental outcomes.",
                        "problem_statement": "Air quality remains below target.",
                        "intended_outcome": "Reduce exposure to pollution.",
                        "category": "Environment",
                        "public_investment_type": "capital_program",
                        "supporting_evidence_ids": ["missing:evidence-id"],
                        "confidence": 0.91,
                        "caveats": ["Requires procurement planning."],
                    }
                ]
            }
        ),
    )

    with pytest.raises(RecommendationGenerationError, match="unknown evidence ids"):
        generator.generate(
            request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
            priority_signals=[],
            evidence_bundle=_sample_evidence_bundle(),
            context_pack=_sample_context_pack(),
            top_n_projects=1,
            language="en",
        )


def test_recommendation_generator_rejects_malformed_structured_output() -> None:
    generator = RecommendationGenerator(
        model_name="gpt-test",
        prompt_version="recommendation_candidates.v1",
        client=FakeOpenAIClient(
            {
                "candidates": [
                    {
                        "candidate_id": "bad-row",
                        "title": "Incomplete Candidate",
                    }
                ]
            }
        ),
    )

    with pytest.raises(RecommendationGenerationError, match="failed schema validation"):
        generator.generate(
            request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
            priority_signals=[],
            evidence_bundle=_sample_evidence_bundle(),
            context_pack=_sample_context_pack(),
            top_n_projects=1,
            language="en",
        )
