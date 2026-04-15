"""Registry for versioned recommendation candidate prompts."""

from dataclasses import dataclass
from typing import Any, Callable

from src.prompts.recommendation_candidates import v1


@dataclass(frozen=True)
class RecommendationCandidatePrompt:
    """Definition for a recommendation candidate prompt version."""

    version: str
    build_messages: Callable[[dict[str, Any]], list[dict[str, str]]]


PROMPT_REGISTRY: dict[str, RecommendationCandidatePrompt] = {
    v1.PROMPT_VERSION: RecommendationCandidatePrompt(
        version=v1.PROMPT_VERSION,
        build_messages=v1.build_messages,
    )
}


def get_active_recommendation_candidate_prompt(version: str) -> RecommendationCandidatePrompt:
    """Return the configured recommendation candidate prompt version."""

    try:
        return PROMPT_REGISTRY[version]
    except KeyError as exc:
        available_versions = ", ".join(sorted(PROMPT_REGISTRY))
        raise ValueError(
            f"Unknown recommendation candidate prompt version '{version}'. "
            f"Available versions: {available_versions}."
        ) from exc
