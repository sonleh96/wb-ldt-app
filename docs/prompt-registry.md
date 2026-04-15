# Prompt Registry

This repo uses explicit prompt registries instead of hidden inline prompt strings.

## Active Registries

- `src/prompts/recommendation_candidates/`
- `src/prompts/explanations/`
- `src/prompts/project_reviews/`

Each registry exposes:

- an explicit prompt version string
- a resolver function for the active prompt
- a versioned prompt asset module

## Environment Configuration

- `LDT_RECOMMENDATION_PROMPT_VERSION`
- `LDT_EXPLANATION_PROMPT_VERSION`
- `LDT_PROJECT_REVIEW_PROMPT_VERSION`

## Why This Exists

- prompt locations are explicit and auditable
- version changes can be tested independently
- model-facing logic stays separated from workflow orchestration
- trace endpoints can record prompt provenance without scraping free-form code
