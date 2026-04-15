"""Registry for versioned explanation prompts."""

from dataclasses import dataclass
from typing import Any, Callable

from src.prompts.explanations import v1


@dataclass(frozen=True)
class ExplanationPrompt:
    """Definition for a narrative explanation prompt version."""

    version: str
    build_messages: Callable[[dict[str, Any]], list[dict[str, str]]]


PROMPT_REGISTRY: dict[str, ExplanationPrompt] = {
    v1.PROMPT_VERSION: ExplanationPrompt(
        version=v1.PROMPT_VERSION,
        build_messages=v1.build_messages,
    )
}


def get_active_explanation_prompt(version: str) -> ExplanationPrompt:
    """Return the configured explanation prompt version."""

    try:
        return PROMPT_REGISTRY[version]
    except KeyError as exc:
        available_versions = ", ".join(sorted(PROMPT_REGISTRY))
        raise ValueError(
            f"Unknown explanation prompt version '{version}'. Available versions: {available_versions}."
        ) from exc
