"""Versioned prompt registry for narrative explanation generation."""

from src.prompts.explanations.registry import ExplanationPrompt, get_active_explanation_prompt

__all__ = ["ExplanationPrompt", "get_active_explanation_prompt"]
