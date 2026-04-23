# LDT Decision Engine v2 - Session Handoff

This file is a context bridge for a fresh Codex session.
It summarizes what is implemented, what is pending, and where to continue.

## 1. Repository Purpose

`wb-ldt-app` is the backend-first replacement of legacy `wb-ldt-de/gpbp-ldt-de.py`, following the build contract in:

- `# LDT Decision Engine v2 — Codex Build Guide`

The direction is:

- FastAPI backend (frontend-agnostic)
- schema-first internal contracts
- explicit workflow/graph orchestration
- deterministic analytics + ranking separation
- evidence provenance + validation
- optional policy-controlled web enrichment

## 2. Completed Batches

## Batch 1 (Prompts 1-5) - Completed

Implemented:

- Repository skeleton and package layout (`apps`, `src`, `tests`, `docs`, `scripts`, `infra`)
- FastAPI bootstrapping and API app factory
- System endpoints: `/health`, `/version`, `/capabilities`
- Centralized config/settings and request-id middleware
- Structured error response handling
- Canonical schema modules (API/domain/workflow/run state)
- Deterministic analytics foundation:
  - indicator gap analysis
  - priority signal computation
  - municipality profile service
- Run registry + run lifecycle transitions
- Placeholder workflow launcher and run endpoints
- Initial test suite for analytics/run lifecycle

## Batch 2 (Prompts 6-10) - Completed

Implemented:

- Source registry and ingestion scaffolding
- Ingestion pipeline with parser routing and chunk persistence
- Storage abstraction for sources/chunks
- Retrieval layer:
  - lexical retriever
  - semantic retriever
  - hybrid retriever
  - retrieval service routing + filters
- Evidence bundle service
- Validation helper for evidence item integrity
- Workflow graph shell with explicit nodes and route
- Seed source ingestion for local retrieval validation
- Expanded tests for ingestion/retrieval/evidence/workflow graph

## Batch 3 Strategy Implementation (Query + Context + Retrieval + Evaluation) - Completed

Implemented:

- Typed query planning with deterministic expansion
  - `intent_query`, `evidence_query`, `constraint_query`, `query_terms`
- Context engineering with evidence cards and context pack
  - token budget per card
  - max card cap
  - source diversity behavior
  - provenance completeness ratio
- Retrieval upgraded to hybrid RRF baseline
  - reciprocal rank fusion
  - per-retriever rank metadata
  - fusion score floor and provenance post-filter
  - retrieval diagnostics payload
- Semantic chunking baseline
  - sentence-embedding breakpoint detection
  - section-aware grouping
  - token-budget enforcement with overlap
  - deterministic contextual chunk headers from document metadata and section hierarchy
  - retrieval-time same-source context window expansion around matched chunks
  - parser-backed PDF ingestion via PyMuPDF4LLM and DOCX ingestion via Mammoth
  - schema-aware CSV row rendering with labeled field-value records for contextual tabular embeddings
- Strict evaluation gate
  - provenance completeness threshold
  - retrieval relevance threshold
  - signal coverage threshold
  - explanation consistency check
  - fail-safe run behavior (run fails if strict gate fails)
- Result payload extensions
  - `context_pack_summary`
  - `retrieval_diagnostics`
  - `evaluation_report`
- Tests added for:
  - query planner determinism
  - chunking budgets
  - context pack constraints
  - strict evaluation failure conditions
  - API e2e submit/status/result fields

## Prompt 11 (Recommendation Candidate Generation) - Completed

Implemented:

- Versioned prompt registry under `src/prompts/recommendation_candidates/`
- OpenAI-backed recommendation generator under `src/llm/recommendation_generator.py`
- Settings and container wiring for OpenAI API key/model/base URL and prompt version
- Candidate generation now uses request metadata, priority signals, evidence bundle, context pack, `top_n_projects`, and `language`
- Schema-constrained output into `RecommendationGenerationOutput`
- Candidate ID normalization to backend-owned IDs (`cand-1`, `cand-2`, ...)
- Evidence-ID validation for generated candidates
- Generation trace stored in workflow node outputs with `candidates`, `model_name`, and `prompt_version`
- Hard-fail behavior for missing config, transport failure, or invalid structured output
- Tests for prompt registry, generator validation/normalization, workflow success/failure, and unchanged API result contract

## Prompt 12 (Deterministic Ranking and Selection) - Completed

Implemented:

- Deterministic ranking modules:
  - `src/ranking/project_filters.py`
  - `src/ranking/project_scorer.py`
  - `src/ranking/project_selector.py`
- Project repository metadata expanded to support deterministic ranking signals
- Hard exclusions for municipality mismatch and inactive project status
- Missing-information flags for incomplete project metadata
- `RankingBreakdown` generation for each project candidate with explicit scoring dimensions
- Deterministic selection of top eligible projects with excluded-project diagnostics retained
- Workflow outputs now preserve ranking breakdowns for selected projects and excluded project records for later explanation/audit stages
- Tests added for filtering, scoring, exclusion handling, deterministic ordering, and workflow integration

## Prompt 13 (Explanation Generation) - Completed

Implemented:

- Versioned explanation prompt registry under `src/prompts/explanations/`
- OpenAI-backed explanation generator under `src/llm/explanation_generator.py`
- Settings and container wiring for explanation prompt version
- Explanation generation now uses recommendation candidates, selected projects, excluded projects, evidence bundle, and ranking outputs
- Schema-constrained output into `NarrativeExplanationOutput`
- Validation that explanation citations stay within known evidence IDs
- Validation that explanation text references at least one selected project title
- Workflow node output now stores structured explanation fields while preserving the existing public `explanation` string contract
- Tests for explanation prompt registry, explanation generator validation/grounding, workflow success/failure, and unchanged API result contract

## Prompt 14 (Project Review Workflow) - Completed

Implemented:

- Independently callable `ProjectReviewService`
- In-memory project review cache store
- Versioned project review prompt registry under `src/prompts/project_reviews/`
- OpenAI-backed project review generator under `src/llm/project_review_generator.py`
- Dedicated project review endpoints:
  - `POST /v1/project-reviews`
  - `GET /v1/project-reviews/{run_id}/{project_id}`
- Tests for prompt registry, generator normalization, service caching, and API flow

## Prompt 15 (Validation Hardening) - Completed

Implemented:

- Modular validators:
  - `src/validation/schema_checks.py`
  - `src/validation/citation_checks.py`
  - `src/validation/consistency_checks.py`
  - `src/validation/run_validator.py`
- Explicit validation failure policies:
  - `fail_run`
  - `partial_result`
  - `downgrade_confidence`
  - `none`
- Top-level `validation_report` persisted in run results
- Warning-level validation can complete a run without forcing failure

## Prompt 16 (Observability and Trace Endpoints) - Completed

Implemented:

- In-memory run trace recorder under `src/observability/tracing.py`
- Node-level trace summaries, model provenance, retrieval trace, selected evidence ids, ranking snapshots, and validation trace
- Inspection service under `src/services/run_inspection_service.py`
- Inspection endpoints:
  - `GET /v1/runs/{run_id}/trace`
  - `GET /v1/runs/{run_id}/evidence`
  - `GET /v1/runs/{run_id}/validation`

## Prompt 17 (Evaluation Suite) - Completed

Implemented:

- `tests/e2e/` acceptance flow
- `tests/evals/` regression fixtures and bad-case checks
- `docs/evaluation-plan.md`

## Prompt 18 (Frontend-Facing Result Contract) - Completed

Implemented:

- Enriched `RecommendationResponse` with stable context, metadata, candidates, ranking, explanation narrative, evidence summary, citations, and validation report fields
- Polling payload progress details in `RunStatusResponse`
- Centralized result serialization in `src/api/serializers.py`
- Contract examples in `docs/contracts.md`

## Prompt 19 (Cleanup and Architecture Review) - Completed

Implemented:

- Route serialization helper introduced to keep business logic out of API routes
- Inspection logic moved into `RunInspectionService`
- Docs updated to reflect final architecture, workflows, contracts, evaluation, and prompt registries

## Prompt 20 (Migration Bridge) - Completed

Implemented:

- Migration note in `docs/migration-bridge.md`
- Old-to-new workflow mapping
- Port / do-not-port guidance
- Parity checklist and migration risk summary

## 3. Current Quality State

- Docstring policy is enforced for runtime modules via:
  - `tests/unit/test_docstring_policy.py`
- Two README styles are maintained:
  - `docs/README_QUICKSTART.md`
  - `docs/README_TECHNICAL_AUDIT.md`
- Root `README.md` is a documentation hub and policy entrypoint.
- Test status at end of this session:
  - `50 passed` (pytest)

## 4. Key Runtime Files (High-Signal)

- Workflow execution:
  - `src/workflows/recommendation_graph.py`
  - `src/workflows/nodes/recommendation_nodes.py`
- Query/context:
  - `src/services/query_planner.py`
  - `src/services/context_packer.py`
- Retrieval:
  - `src/retrieval/service.py`
  - `src/retrieval/hybrid.py`
- Evaluation:
  - `src/validation/strict_gate.py`
- API contract:
  - `src/api/routers/runs.py`
  - `src/schemas/api.py`
  - `src/schemas/workflow.py`
  - `src/schemas/retrieval.py`

## 5. Remaining Work (Build Guide Roadmap)

Build-guide prompts are now implemented through Prompt 20.

Practical v2.1 gaps remain:

- persistent reference-data backends for projects, municipalities, and indicators
- richer project metadata and ranking inputs
- live web enrichment beyond placeholders
- automated retry/remediation loops for warning/failure policies
- deeper benchmark coverage with human-reviewed datasets

## 6. Known Constraints / Decisions Locked

- Priority: trustworthiness over recall/latency.
- Context format: evidence cards (not raw top-k chunk pass-through).
- Retrieval baseline: hybrid lexical+semantic with RRF fusion.
- Chunking strategy: semantic chunking for prose, schema-aware labeled records for CSV/tabular data.
- Embedding strategy: deterministic local embeddings for offline tests, OpenAI `text-embedding-3-large` as the intended production default.
- Embedding payload: contextual header + chunk body for prose, schema/context + labeled row text for CSV.
- Retrieval context policy: expand neighboring same-source chunks after retrieval rather than storing oversized chunks.
- Optional source/chunk storage backend: PostgreSQL + pgvector via `LDT_STORAGE_BACKEND=postgres`.
- GCP/Supabase target architecture: Cloud Run + GCS documents + Supabase Postgres with `pgvector`.
- Completion policy: strict gate can fail run before completion.
- Keep current run API endpoints stable to avoid client breakage.

## 7. Environment Notes

Interpreter used in this session:

- `C:/Users/sonle/anaconda3/envs/wb-ldt-de/python.exe`

Test command:

```bash
C:/Users/sonle/anaconda3/envs/wb-ldt-de/python.exe -m pytest -q
```

## 8. Suggested First Task in New Session

Start v2.1 hardening:

1. Replace in-memory stores with durable persistence.
2. Upgrade placeholder web enrichment into policy-gated live retrieval.
3. Improve project metadata ingestion and ranking features.
4. Add richer CSV/table metadata handling and grouping strategies beyond row-wise textualization.
5. Add human-reviewed benchmark cases for acceptance evaluation.
