import pytest

from src.prompts.recommendation_candidates import get_active_recommendation_candidate_prompt


def test_recommendation_prompt_registry_resolves_active_version() -> None:
    prompt = get_active_recommendation_candidate_prompt("recommendation_candidates.v1")

    assert prompt.version == "recommendation_candidates.v1"
    messages = prompt.build_messages({"request": {"category": "Environment"}})
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_recommendation_prompt_registry_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="Unknown recommendation candidate prompt version"):
        get_active_recommendation_candidate_prompt("recommendation_candidates.v999")
