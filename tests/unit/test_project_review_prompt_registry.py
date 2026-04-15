import pytest

from src.prompts.project_reviews import get_active_project_review_prompt


def test_project_review_prompt_registry_resolves_active_version() -> None:
    prompt = get_active_project_review_prompt("project_reviews.v1")

    assert prompt.version == "project_reviews.v1"
    messages = prompt.build_messages({"project": {"project_id": "proj-001"}})
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_project_review_prompt_registry_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="Unknown project review prompt version"):
        get_active_project_review_prompt("project_reviews.v999")
