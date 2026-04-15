"""Versioned prompt registry for recommendation candidate generation."""

from src.prompts.recommendation_candidates.registry import (
    RecommendationCandidatePrompt,
    get_active_recommendation_candidate_prompt,
)

__all__ = [
    "RecommendationCandidatePrompt",
    "get_active_recommendation_candidate_prompt",
]
