"""Versioned prompt registry for project review generation."""

from src.prompts.project_reviews.registry import ProjectReviewPrompt, get_active_project_review_prompt

__all__ = ["ProjectReviewPrompt", "get_active_project_review_prompt"]
