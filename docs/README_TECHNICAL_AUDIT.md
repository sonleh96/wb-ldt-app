# LDT Decision Engine v2 - Technical Audit README

This document describes the implemented backend after Batch 1, Batch 2, Batch 3, and Batch 4 completion.
It is written for engineering audits, architecture reviews, and handoff.

## 1. Architecture Summary

The system is a backend-first FastAPI service with explicit workflow state handling and typed contracts.

### Implemented layers

- API layer: [main.py](d:/Work/WB/wb-ldt-app/apps/api/main.py), [app.py](d:/Work/WB/wb-ldt-app/src/core/app.py), [system.py](d:/Work/WB/wb-ldt-app/src/api/routers/system.py), [runs.py](d:/Work/WB/wb-ldt-app/src/api/routers/runs.py)
- Core runtime: [settings.py](d:/Work/WB/wb-ldt-app/src/config/settings.py), [errors.py](d:/Work/WB/wb-ldt-app/src/core/errors.py), [request_context.py](d:/Work/WB/wb-ldt-app/src/core/request_context.py), [logging.py](d:/Work/WB/wb-ldt-app/src/core/logging.py)
- Service container and dependency wiring: [container.py](d:/Work/WB/wb-ldt-app/src/core/container.py)
- LLM integration and prompt registry: [recommendation_generator.py](d:/Work/WB/wb-ldt-app/src/llm/recommendation_generator.py), [registry.py](d:/Work/WB/wb-ldt-app/src/prompts/recommendation_candidates/registry.py), [v1.py](d:/Work/WB/wb-ldt-app/src/prompts/recommendation_candidates/v1.py)
- Explanation integration and prompt registry: [explanation_generator.py](d:/Work/WB/wb-ldt-app/src/llm/explanation_generator.py), [registry.py](d:/Work/WB/wb-ldt-app/src/prompts/explanations/registry.py), [v1.py](d:/Work/WB/wb-ldt-app/src/prompts/explanations/v1.py)
- Project review integration and prompt registry: [project_review_generator.py](d:/Work/WB/wb-ldt-app/src/llm/project_review_generator.py), [registry.py](d:/Work/WB/wb-ldt-app/src/prompts/project_reviews/registry.py), [v1.py](d:/Work/WB/wb-ldt-app/src/prompts/project_reviews/v1.py)
- Ranking pipeline: [project_filters.py](d:/Work/WB/wb-ldt-app/src/ranking/project_filters.py), [project_scorer.py](d:/Work/WB/wb-ldt-app/src/ranking/project_scorer.py), [project_selector.py](d:/Work/WB/wb-ldt-app/src/ranking/project_selector.py)
- Observability and inspection: [tracing.py](d:/Work/WB/wb-ldt-app/src/observability/tracing.py), [logging.py](d:/Work/WB/wb-ldt-app/src/observability/logging.py), [run_inspection_service.py](d:/Work/WB/wb-ldt-app/src/services/run_inspection_service.py)
- Schemas: [api.py](d:/Work/WB/wb-ldt-app/src/schemas/api.py), [domain.py](d:/Work/WB/wb-ldt-app/src/schemas/domain.py), [workflow.py](d:/Work/WB/wb-ldt-app/src/schemas/workflow.py), [run_state.py](d:/Work/WB/wb-ldt-app/src/schemas/run_state.py), [source_metadata.py](d:/Work/WB/wb-ldt-app/src/schemas/source_metadata.py), [retrieval.py](d:/Work/WB/wb-ldt-app/src/schemas/retrieval.py)
- Deterministic analytics: [gap_analysis.py](d:/Work/WB/wb-ldt-app/src/analytics/gap_analysis.py), [priority_signals.py](d:/Work/WB/wb-ldt-app/src/analytics/priority_signals.py), [municipality_profile_service.py](d:/Work/WB/wb-ldt-app/src/services/municipality_profile_service.py)
- Run lifecycle: [run_registry.py](d:/Work/WB/wb-ldt-app/src/services/run_registry.py), [run_store.py](d:/Work/WB/wb-ldt-app/src/storage/run_store.py)
- Ingestion: [source_registry.py](d:/Work/WB/wb-ldt-app/src/ingestion/source_registry.py), [pipeline.py](d:/Work/WB/wb-ldt-app/src/ingestion/pipeline.py), [chunking.py](d:/Work/WB/wb-ldt-app/src/ingestion/chunking.py), [sources.py](d:/Work/WB/wb-ldt-app/src/storage/sources.py)
- Serbia staged ingestion: `src/storage/serbia_datasets.py`, `src/services/serbia_dataset_loader.py`, `src/services/serbia_document_mirror.py`, `src/services/serbia_source_ingestion.py`
- Retrieval: [semantic.py](d:/Work/WB/wb-ldt-app/src/retrieval/semantic.py), [lexical.py](d:/Work/WB/wb-ldt-app/src/retrieval/lexical.py), [hybrid.py](d:/Work/WB/wb-ldt-app/src/retrieval/hybrid.py), [service.py](d:/Work/WB/wb-ldt-app/src/retrieval/service.py)
- Evidence normalization: [evidence_bundle.py](d:/Work/WB/wb-ldt-app/src/services/evidence_bundle.py), [evidence_validation.py](d:/Work/WB/wb-ldt-app/src/validation/evidence_validation.py)
- Query planning: [query_planner.py](d:/Work/WB/wb-ldt-app/src/services/query_planner.py)
- Context engineering: [context_packer.py](d:/Work/WB/wb-ldt-app/src/services/context_packer.py)
- Strict evaluation gate: [strict_gate.py](d:/Work/WB/wb-ldt-app/src/validation/strict_gate.py)
- Workflow graph shell: [router.py](d:/Work/WB/wb-ldt-app/src/workflows/router.py), [recommendation_nodes.py](d:/Work/WB/wb-ldt-app/src/workflows/nodes/recommendation_nodes.py), [recommendation_graph.py](d:/Work/WB/wb-ldt-app/src/workflows/recommendation_graph.py), [workflow_launcher.py](d:/Work/WB/wb-ldt-app/src/services/workflow_launcher.py)

## 2. Workflow Execution Model

### Run state machine

Current states:

- `pending`
- `queued`
- `running`
- `validating`
- `completed`
- `failed`
- `cancelled`

Transitions are enforced by `ALLOWED_TRANSITIONS` in [run_registry.py](d:/Work/WB/wb-ldt-app/src/services/run_registry.py).

### Node route (Batch 2 graph shell)

Route is built in [router.py](d:/Work/WB/wb-ldt-app/src/workflows/router.py):

1. `create_run`
2. `resolve_request_context`
3. `compute_indicator_analysis`
4. `plan_retrieval`
5. `retrieve_local_evidence`
6. `optionally_retrieve_web_evidence` (conditional)
7. `build_evidence_bundle`
8. `generate_recommendation_candidates`
9. `rank_candidates`
10. `select_projects`
11. `generate_explanation`
12. `validate_output`
13. `finalize_run`

Node implementations are in [recommendation_nodes.py](d:/Work/WB/wb-ldt-app/src/workflows/nodes/recommendation_nodes.py). The graph executor is [recommendation_graph.py](d:/Work/WB/wb-ldt-app/src/workflows/recommendation_graph.py).

Batch 3 additions in workflow:

- typed query planning fields in `RetrievalPlan`
- context pack generation from retrieval outputs
- strict evaluation gate, including hard fail behavior before completion

Prompt 11 additions in workflow:

- `generate_recommendation_candidates` now calls a dedicated `RecommendationGenerator`
- candidate generation is prompt-versioned and schema-constrained through `RecommendationGenerationOutput`
- candidate IDs are normalized by the backend (`cand-1`, `cand-2`, ...)
- generation failures hard-fail the run at the candidate-generation node with no deterministic fallback

Prompt 12 additions in workflow:

- project ranking is deterministic and isolated from the LLM layer
- a filtering pass marks excluded projects and missing-information flags before scoring
- scoring produces `RankingBreakdown` values for municipality fit, indicator alignment, development-plan alignment, readiness, financing plausibility, and evidence support strength
- selection chooses top non-excluded projects from deterministic ranking outputs and preserves excluded-project diagnostics for later explanation/audit work

Prompt 13 additions in workflow:

- `generate_explanation` now calls a dedicated `ExplanationGenerator`
- explanation generation is prompt-versioned and schema-constrained through `NarrativeExplanationOutput`
- explanations are validated against selected project titles and allowed evidence IDs
- the API still returns a single `explanation` string, but workflow trace stores structured explanation fields for downstream inspection

Prompt 14 additions:

- project review is independently callable through `ProjectReviewService`
- review outputs are cached in-memory by `(run_id, project_id, include_web_evidence)`
- project reviews use dedicated prompt assets and structured output validation

Prompt 15 additions:

- validation logic is modularized into schema, citation, and consistency checks
- `RunValidator` selects explicit failure policies (`fail_run`, `partial_result`, `downgrade_confidence`, `none`)
- validation reports are included in completed runs and inspectable via dedicated endpoints

Prompt 16 additions:

- run traces persist node summaries, model provenance, retrieval source/chunk ids, selected evidence ids, ranking snapshots, and validation reports
- inspection endpoints expose trace, evidence, and validation views after execution

## 3. Ingestion and Retrieval Contracts

### Ingestion

`SourceRegistry.register_source(...)` stores typed source metadata.
`IngestionPipeline.ingest_source(source_id)` parses and chunks content.

Parser behavior in Batch 2:

- `.csv`: parsed into schema-aware row records with labeled field-value statements
- `.txt` / `.md`: text read directly
- `.pdf`: `PyMuPDF4LLM` markdown parser
- `.docx`: `mammoth` semantic HTML-to-text parser
- other binary types: generic placeholder parser

Chunk outputs are persisted as `SourceChunk` records in `InMemorySourceRepository`.

Current chunking behavior:

- sentence-embedding breakpoint detection for semantic chunking
- deterministic contextual chunk headers using document title, source type, category, and section path
- stored chunk fields for raw body text, header text, and section hierarchy
- CSV rows are rendered with dataset-column context and row-level field labels before chunk embedding

### Retrieval

`RetrievalService.search(...)` routes by mode:

- `semantic`: embedding-based semantic retrieval over chunk embeddings
- `lexical`: token overlap scoring
- `hybrid`: reciprocal rank fusion (RRF) over lexical+semantic results with score floor and provenance checks
- retrieval-time context window expansion adds neighboring chunks from the same source around each matched chunk

Output contract: `RetrievalResponse` + `RetrievalResult` in [retrieval.py](d:/Work/WB/wb-ldt-app/src/schemas/retrieval.py).

Filters supported:

- `municipality_id`
- `category`
- `source_types`

## 4. Chunking and Embedding Design Decisions

### Chunking strategy choices

The current ingestion path intentionally uses different logic for prose-style documents and tabular data.

For prose documents (`.txt`, `.md`, `.pdf`, `.docx`):

- semantic chunking is preferred over fixed-size-only chunking because legal, policy, academic, and training documents often contain long sections where meaning changes at paragraph or sentence boundaries rather than token boundaries
- sentence-window embedding distance is used to determine semantic breakpoints because it is deterministic once the embedding model is fixed and preserves topic shifts better than simple paragraph splitting
- token-budget enforcement still runs after semantic grouping so downstream retrieval and context packing remain bounded

For CSV/tabular sources:

- rows are rendered into labeled field-value records rather than raw comma-joined lines
- the goal is to preserve schema meaning so values remain interpretable during retrieval
- a value such as `18.4` should not be embedded without field labels like `Indicator`, `Year`, `Unit`, or `Municipality`

### Contextual chunk headers

Chunk headers are intentionally embedded together with chunk bodies.

The rationale:

- many chunks in policies, legal text, journal articles, and training material rely on higher-level context that is not restated locally
- document title, source type, category, and section path materially improve retrieval for chunks that contain pronouns, implicit references, abbreviations, or topic-local language
- headers are deterministic and cheap compared with LLM-generated summaries

Current rule:

- embed `header_text + body_text`
- preserve `body_text` separately for traceability

### Retrieval-time context windows

The system expands retrieved hits with neighboring same-source chunks after retrieval rather than storing oversized chunks at ingest time.

This was chosen because:

- larger stored chunks reduce retrieval precision
- retrieval-time expansion preserves sharper indexing while still restoring surrounding context when a relevant chunk is found
- context windows are especially useful for legal/policy sections, textbooks, and journal articles where adjacent paragraphs often contain the needed qualifiers or definitions

### Why hybrid retrieval remains necessary

The intended retrieval model is not pure vector search.

Hybrid retrieval is retained because:

- exact lexical matching is important for indicators, acronyms, named programs, laws, dates, and numeric/table lookups
- semantic retrieval improves recall for paraphrased or conceptually related passages
- CSV and table-style content in particular benefits from lexical matching on keys such as municipality, year, indicator, and unit

## 5. Embedding Strategy

### Current embedding modes

Two embedding modes exist by design:

- `local`: deterministic hashed embeddings for offline-safe tests and local startup
- `openai`: production-oriented embeddings using `LDT_EMBEDDING_MODEL`, currently defaulting to `text-embedding-3-small`

The local mode exists so:

- test runs do not require network access
- ingestion/retrieval logic can be exercised deterministically in constrained environments

The OpenAI mode exists so:

- semantic chunking breakpoints are based on real embeddings
- semantic retrieval has real production quality

### What gets embedded

The embedding payload is intentionally contextualized:

- prose chunks: `document/section header + chunk body`
- CSV chunks: `dataset schema context + row label + labeled field-value statements`
- retrieval-time context windows are not separately embedded; they are assembled after retrieval for downstream evidence use

### Production recommendation

For production use, the intended path is:

- `LDT_EMBEDDING_PROVIDER=openai`
- `LDT_EMBEDDING_MODEL=text-embedding-3-small` as the baseline default

This model choice is currently favored because it is a practical quality/cost choice for large-scale ingestion and retrieval. The deterministic embedder is a development fallback, not the intended production setting.

## 6. Evidence Bundle Model

`EvidenceBundleService.build_bundle(...)` merges:

- deterministic analytics priority signals
- local retrieval results
- optional web evidence placeholders

Current behavior:

- item-level normalization into `EvidenceItem`
- deduplication by stable hash key
- structural checks through `validate_evidence_items(...)`

Outputs are `EvidenceBundle` typed objects in [domain.py](d:/Work/WB/wb-ldt-app/src/schemas/domain.py).

Context pack outputs are represented as `ContextPack` and `EvidenceCard` in [workflow.py](d:/Work/WB/wb-ldt-app/src/schemas/workflow.py).

## 7. Recommendation Candidate Generation

Prompt assets live under `src/prompts/recommendation_candidates/` and are selected through an explicit registry version.

Current implementation details:

- active prompt version comes from `LDT_RECOMMENDATION_PROMPT_VERSION`
- OpenAI model config comes from `LDT_OPENAI_API_KEY`, `LDT_OPENAI_MODEL`, and optional `LDT_OPENAI_BASE_URL`
- generation input includes request metadata, priority signals, evidence bundle items, context-pack cards, `top_n_projects`, and `language`
- output is parsed into `RecommendationGenerationOutput`, then validated so every `supporting_evidence_id` exists in the current evidence bundle
- candidate-generation trace is stored in workflow `node_outputs` with `candidates`, `model_name`, and `prompt_version`

## 8. Deterministic Project Ranking

Prompt 12 introduces a three-step deterministic ranking pipeline:

- `ProjectFilter` applies hard exclusions such as municipality mismatch and inactive status, and emits missing-information flags
- `ProjectScorer` matches projects against recommendation candidates and evidence to compute `RankingBreakdown`
- `ProjectSelector` sorts reproducibly and returns top eligible projects plus excluded-project diagnostics

Current ranking signals:

- municipality/category fit
- indicator-gap alignment from project/candidate keyword overlap
- development-plan alignment from project metadata
- implementation readiness from metadata plus status adjustment
- financing plausibility with investment-type compatibility check
- evidence support strength from candidate evidence overlap and confidence

## 9. Narrative Explanation Generation

Prompt 13 introduces a bounded explanation layer:

- prompt assets live under `src/prompts/explanations/`
- active prompt version comes from `LDT_EXPLANATION_PROMPT_VERSION`
- explanation input includes recommendation candidates, selected projects, excluded projects, evidence bundle, and ranking outputs
- output is parsed into `NarrativeExplanationOutput`
- cited evidence IDs are validated against the current evidence bundle
- explanations must reference at least one selected project title to pass normalization

This keeps explanation generation downstream of ranking and evidence assembly, so the narrative cannot alter project choice or ranking math.

## 10. Project Review Workflow

Project review is now an independent service path:

- request schema: `ProjectReviewRequest`
- response schema: `ProjectReviewResponse`
- endpoints:
  - `POST /v1/project-reviews`
  - `GET /v1/project-reviews/{run_id}/{project_id}`

The review path reuses completed run context, performs project-specific retrieval, optionally appends a web placeholder, and generates a structured review with citations normalized to review evidence ids.

## 11. Validation and Observability

Validation modules:

- `schema_checks.py`
- `citation_checks.py`
- `consistency_checks.py`
- `run_validator.py`

Observability artifacts:

- node-level traces
- model/prompt provenance
- retrieval chunk/source traces
- selected evidence ids
- ranking snapshots
- validation reports

Inspection endpoints:

- `GET /v1/runs/{run_id}/trace`
- `GET /v1/runs/{run_id}/evidence`
- `GET /v1/runs/{run_id}/validation`

## 12. GCP / Supabase Deployment Target

The intended hosted production architecture is now GCP/Supabase-based.

Target stack:

- Google Cloud Run for the FastAPI runtime
- Google Cloud Storage for raw uploaded documents and large source artifacts
- Supabase Postgres as the primary system of record
- `pgvector` inside Supabase Postgres for semantic chunk retrieval
- secrets supplied through environment variables or Cloud Run secret bindings

Implemented GCP/Supabase-ready pieces:

- source/chunk storage can already switch to PostgreSQL through `LDT_STORAGE_BACKEND=postgres`
- run state, trace, and project-review persistence can also switch to PostgreSQL through `LDT_STORAGE_BACKEND=postgres`
- semantic retrieval is designed to use PostgreSQL + `pgvector`
- ingestion already produces embeddings suitable for vector search
- source documents can be registered as `gs://bucket/object` URIs through `LDT_DOCUMENT_STORE_BACKEND=gcs`
- GCS objects are downloaded to temporary local files for parser-backed ingestion
- Cloud Run packaging files are present (`Dockerfile`, `.dockerignore`, `cloudbuild.yaml`, and deploy script)

Still pending:

- direct browser/client upload orchestration for GCS
- durable worker/queue handling for long-running ingestion and recommendation jobs

This means the current codebase is aligned to Cloud Run + GCS + Supabase, but still needs environment provisioning
and production hardening before public exposure.

## 13. API Surface and Runtime

### System endpoints

- `GET /health`
- `GET /version`
- `GET /capabilities`
- `GET /v1/admin/sources`
- `POST /v1/admin/sources`
- `POST /v1/admin/sources/{source_id}/ingest`
- `GET /v1/admin/datasets/rows`
- `GET /v1/admin/datasets/failures/mirroring`
- `POST /v1/admin/datasets/{dataset_family}/{row_id}/mirror`
- `POST /v1/admin/datasets/{dataset_family}/{row_id}/ingest`

### Run endpoints

- `POST /v1/runs/recommendations`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/result`
- `POST /v1/runs/{run_id}/cancel`
- `POST /v1/project-reviews`
- `GET /v1/project-reviews/{run_id}/{project_id}`
- `GET /v1/runs/{run_id}/trace`
- `GET /v1/runs/{run_id}/evidence`
- `GET /v1/runs/{run_id}/validation`

Request IDs are assigned/propagated via `X-Request-Id` middleware in [request_context.py](d:/Work/WB/wb-ldt-app/src/core/request_context.py).
Errors are returned as structured `ErrorResponse` payloads via [errors.py](d:/Work/WB/wb-ldt-app/src/core/errors.py).

## 14. Seed Data and Bootstrapping Notes

`ServiceContainer._seed_sources()` is now opt-in through `LDT_AUTO_SEED_SOURCES=true` and remains a dev/test helper:

- [seed_environment_policy.txt](d:/Work/WB/wb-ldt-app/docs/seed_environment_policy.txt)
- [seed_environment_dataset.csv](d:/Work/WB/wb-ldt-app/docs/seed_environment_dataset.csv)

Admin endpoints are protected by `LDT_ADMIN_API_KEY` when configured, and are required in `prod`.

## 15. Test Coverage

Unit tests currently cover:

- deterministic analytics gap computation
- priority signal ordering
- municipality profile service
- ingestion pipeline CSV flow
- parser routing for PDF/DOCX ingestion
- retrieval service filtering/shape
- evidence bundle assembly
- run lifecycle
- workflow graph execution
- docstring policy enforcement across `src/` and `apps/`
- query planner deterministic expansion
- chunking token budget behavior
- context pack constraints
- recommendation prompt registry resolution
- recommendation generator normalization and failure handling
- project filtering, scoring breakdowns, exclusions, and deterministic selection
- explanation prompt registry resolution
- explanation generator grounding and validation behavior
- project review prompt registry, generator, service, and API flow
- run validator policies
- run inspection endpoints
- admin source registration, ingestion, and idempotent duplicate handling
- PostgreSQL-backed runtime persistence for runs, traces, and project-review cache
- e2e acceptance flow
- eval regression fixtures
- strict evaluation failure conditions
- API submit/status/result contract fields

See `tests/unit/`.

Docstring policy checker:

- [test_docstring_policy.py](d:/Work/WB/wb-ldt-app/tests/unit/test_docstring_policy.py)

## 16. Known Gaps (Expected at this Stage)

- Source metadata and chunk embeddings now have an optional PostgreSQL + pgvector backend via `LDT_STORAGE_BACKEND=postgres`.
- Run state, traces, and review cache now share the same optional PostgreSQL backend via `LDT_STORAGE_BACKEND=postgres`.
- Full source documents can be stored in GCS and registered through `gs://` URIs via `LDT_DOCUMENT_STORE_BACKEND=gcs`.
- PDF/DOCX parsing depends on optional parser libraries being installed in the runtime environment.
- OpenAI embeddings are the intended production path, but local deterministic embeddings remain the default development/test fallback.
- Ranking uses seed-project metadata and heuristic keyword overlap; richer project metadata sources are still pending.
- Live web enrichment remains placeholder-backed in the main workflow.
- Retry-style remediation is policy-modeled but not yet auto-executed.

## 17. Run and Verify

Install:

```bash
pip install -e .[dev]
```

Run:

```bash
uvicorn apps.api.main:app --reload
```

Test:

```bash
python -m pytest -q
```
