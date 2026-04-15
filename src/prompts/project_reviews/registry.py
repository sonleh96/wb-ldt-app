"""Registry for versioned project review prompts."""

from dataclasses import dataclass
from typing import Any, Callable

from src.prompts.project_reviews import v1


@dataclass(frozen=True)
class ProjectReviewPrompt:
    """Definition for a project review prompt version."""

    version: str
    build_messages: Callable[[dict[str, Any]], list[dict[str, str]]]


PROMPT_REGISTRY: dict[str, ProjectReviewPrompt] = {
    v1.PROMPT_VERSION: ProjectReviewPrompt(version=v1.PROMPT_VERSION, build_messages=v1.build_messages)
}


def get_active_project_review_prompt(version: str) -> ProjectReviewPrompt:
    """Return the configured project review prompt version."""

    try:
        return PROMPT_REGISTRY[version]
    except KeyError as exc:
        available_versions = ", ".join(sorted(PROMPT_REGISTRY))
        raise ValueError(
            f"Unknown project review prompt version '{version}'. Available versions: {available_versions}."
        ) from exc
