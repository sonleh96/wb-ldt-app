import pytest

from src.prompts.explanations import get_active_explanation_prompt


def test_explanation_prompt_registry_resolves_active_version() -> None:
    prompt = get_active_explanation_prompt("explanations.v1")

    assert prompt.version == "explanations.v1"
    messages = prompt.build_messages({"request": {"category": "Environment"}})
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_explanation_prompt_registry_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="Unknown explanation prompt version"):
        get_active_explanation_prompt("explanations.v999")
