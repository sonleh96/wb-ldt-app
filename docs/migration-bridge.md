# Migration Bridge From `wb-ldt-de`

This note maps the legacy Streamlit prototype in `D:\Work\WB\wb-ldt-de` to the backend-first rebuild in `wb-ldt-app`.

## What To Port

- Deterministic analytics logic from legacy files such as `src/analysis.py`, especially municipality-versus-national comparison patterns and indicator relevance handling.
- Prompt content worth preserving from `src/llm.py`, especially domain phrasing, project-review structure, and background-research framing.
- Useful project metadata conventions from `data/project_info.json` and `data/wbif_project_examples_v2.csv`.
- Caching semantics from `src/caching.py` where repeatable output reuse is still valuable, but only after adapting them to backend-safe storage abstractions.

## What Not To Port

- Streamlit-specific flow and session-state orchestration from `gpbp-ldt-de.py`, `app.py`, and `src/ui.py`.
- Brittle prompt chaining where downstream steps consume prose instead of typed outputs.
- UI-coupled state transitions, view logic, or widget-driven control flow.
- UI-era deployment assumptions; GCS may still be used, but only through backend-owned document storage abstractions.

## Old-To-New Workflow Mapping

- Legacy regional indicator analysis:
  maps to deterministic analytics and `compute_indicator_analysis`
- Legacy background research and recommendation prompt chain:
  maps to retrieval, evidence bundling, `generate_recommendation_candidates`, `rank_candidates`, and `generate_explanation`
- Legacy project-review document generation:
  maps to `ProjectReviewService` and the `project_reviews` prompt registry
- Legacy cached response layer:
  maps conceptually to explicit stores such as run storage, trace storage, and project-review cache

## Reference Files From Old Repo

- `D:\Work\WB\wb-ldt-de\src\analysis.py`
- `D:\Work\WB\wb-ldt-de\src\llm.py`
- `D:\Work\WB\wb-ldt-de\src\caching.py`
- `D:\Work\WB\wb-ldt-de\gpbp-ldt-de.py`

These should now be treated as reference material only, not direct implementation templates.

## Parity Checklist

- Municipality/category input still drives deterministic indicator analysis.
- Recommendation generation still produces policy-style project options, but now through typed candidate objects.
- Ranking is deterministic and separate from LLM generation.
- Explanation is generated only after ranking and cites evidence IDs.
- Project review is independently callable and evidence-backed.
- Failures, validation outcomes, and traces are inspectable after a run.
- Frontend can poll stable JSON contracts instead of relying on Streamlit session state.

## Highest-Risk Migration Areas

- Prompt-content drift:
  the old repo contains useful phrasing and project-review structure that may still outperform current prompt wording in some cases.
- Project metadata richness:
  the old repo may encode more nuanced project context than the current seed repository metadata.
- Cached output semantics:
  the old cache manager mixes UI/runtime assumptions with persistence; only the reuse intent should be ported, not the implementation.
- Web-search behavior:
  the old project-review flow relies on live web research patterns that are still placeholder or policy-limited in the rebuilt backend.
