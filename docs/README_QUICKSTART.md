# LDT Decision Engine v2 - Quickstart

This guide is for users who want to run the backend fast and use the current endpoints.

## What Is Implemented (Batch 1 + Batch 2 + Batch 3 + Prompts 11-20)

- FastAPI app bootstrap with request tracing and structured error handling.
- Recommendation run lifecycle (`pending -> queued -> running -> validating -> completed/failed/cancelled`).
- Deterministic analytics for indicator gaps and priority signals.
- Ingestion scaffolding for local or GCS-backed sources with parser-backed PDF/DOCX ingestion, schema-aware CSV ingestion, semantic chunking, and contextual chunk headers.
- Retrieval service with `semantic`, `lexical`, and `hybrid` modes.
- Hybrid retrieval now uses reciprocal rank fusion (RRF) diagnostics.
- Retrieved hits are expanded with a same-source context window before evidence bundling.
- Optional PostgreSQL-backed durable runtime persistence for runs, traces, project reviews, and sources.
- Evidence bundle assembly from analytics + retrieval outputs.
- Evidence-card context packing with provenance-aware selection.
- OpenAI-backed recommendation candidate generation with versioned prompt assets.
- Deterministic project filtering, scoring, exclusion handling, and top-project selection.
- Grounded narrative explanation generation with cited evidence IDs.
- Independently callable project review generation with cache-backed reuse.
- Modular run validation with explicit failure policies.
- Run inspection endpoints for trace, evidence, and validation.
- Stable frontend-facing contracts documented in `docs/contracts.md`.
- Strict evaluation gate for trustworthiness-first completion checks.
- Routed workflow graph shell that executes node-by-node and stores outputs.

## Prerequisites

- Python `3.11+`
- `pip`

## Install

```bash
pip install -e .[dev]
```

## Run API

```bash
uvicorn apps.api.main:app --reload
```

Default local URL: `http://127.0.0.1:8000`

## LLM Configuration

Prompt 11 requires OpenAI configuration for recommendation candidate generation:

```bash
set LDT_OPENAI_API_KEY=your_api_key
set LDT_OPENAI_MODEL=gpt-4.1-mini
set LDT_RECOMMENDATION_PROMPT_VERSION=recommendation_candidates.v1
```

Optional:

```bash
set LDT_OPENAI_BASE_URL=https://your-compatible-endpoint
```

If candidate generation is not configured, or the model returns invalid structured output, recommendation runs fail at
`generate_recommendation_candidates`. The HTTP result contract is unchanged; the failure is visible through run status.

## Retrieval / Chunking Configuration

Semantic chunking is now modeled after the sentence-embedding breakpoint approach used in the provided notebook:

- adjacent sentence windows are embedded
- semantic breakpoints are chosen by threshold type and amount
- final chunks are embedded for semantic retrieval
- chunk embeddings include deterministic contextual headers built from document metadata and section hierarchy
- retrieval expands matched chunks with neighboring same-source chunks before downstream evidence use

Design choices behind this setup:

- prose documents are chunked semantically first, then token-bounded
- document and section metadata are prepended before embedding so chunks remain interpretable in isolation
- CSV sources are rendered as labeled row records instead of raw comma-joined values
- retrieval expands local context after search rather than storing oversized chunks at ingest time

Default local development uses a deterministic offline embedding backend so tests and local startup do not require
network access. For real semantic quality, set:

```bash
set LDT_EMBEDDING_PROVIDER=openai
set LDT_EMBEDDING_MODEL=text-embedding-3-large
```

Production guidance:

- `local` embeddings are for deterministic tests and offline development
- `openai` embeddings are the intended production setting
- the production target is Supabase Postgres with `pgvector`, not an in-memory vector index

Optional semantic chunking controls:

```bash
set LDT_SEMANTIC_CHUNK_MAX_TOKENS=180
set LDT_SEMANTIC_CHUNK_OVERLAP_TOKENS=24
set LDT_SEMANTIC_CHUNK_MIN_TOKENS=40
set LDT_SEMANTIC_CHUNK_BREAKPOINT_TYPE=percentile
set LDT_SEMANTIC_CHUNK_BREAKPOINT_AMOUNT=90
set LDT_RETRIEVAL_CONTEXT_WINDOW_NEIGHBORS=1
```

Optional PostgreSQL + pgvector storage:

```bash
set LDT_STORAGE_BACKEND=postgres
set LDT_DATABASE_URL=postgresql://user:password@host:5432/dbname
```

When `LDT_STORAGE_BACKEND=postgres`, source metadata, chunk embeddings, run state, run traces, and project-review
cache are all stored in PostgreSQL. Semantic retrieval uses pgvector cosine search.

For Supabase, use the PostgreSQL connection string supplied by Supabase and ensure the `vector` extension is enabled.
The embedding dimension configured by `LDT_EMBEDDING_DIMENSIONS` must match the embedding model output stored in the
`source_chunks.embedding` vector column.

Optional GCS document storage:

```bash
set LDT_DOCUMENT_STORE_BACKEND=gcs
set LDT_GCP_PROJECT=your-gcp-project-id
set LDT_GCS_BUCKET=your-document-bucket
set LDT_GCS_PREFIX=ldt/sources
```

When `LDT_DOCUMENT_STORE_BACKEND=gcs`, admin source registration accepts `gs://bucket/object` URIs. The backend
validates that the object exists, downloads it to a temporary local path for parsing, and stores source metadata plus
chunk embeddings in the configured source repository.

Optional seed-source bootstrap:

```bash
set LDT_AUTO_SEED_SOURCES=true
```

## GCP Deployment Notes

The intended hosted architecture is:

- Google Cloud Run for the FastAPI runtime
- Google Cloud Storage for full source documents
- Supabase Postgres as the primary database
- `pgvector` in Supabase Postgres for semantic retrieval

Current implementation status:

- source/chunk persistence is Supabase/PostgreSQL-ready
- semantic retrieval is PostgreSQL/pgvector-ready
- runs, traces, and project-review cache now support PostgreSQL-backed durability
- GCS-backed document access is available for source registration and ingestion

Cloud Run files are included:

- `Dockerfile`
- `.dockerignore`
- `cloudbuild.yaml`
- `scripts/deploy_cloud_run.sh`

## Core Endpoints

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
- `POST /v1/runs/recommendations`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/result`
- `POST /v1/runs/{run_id}/cancel`

Result payload now includes:

- `context_pack_summary`
- `retrieval_diagnostics`
- `evaluation_report`

Candidate-generation metadata (`model_name`, `prompt_version`, typed candidates) is stored in internal workflow
`node_outputs`, not in the public result payload.

Ranking breakdowns and excluded-project diagnostics are also generated internally for downstream explanation and audit
work.

Explanation generation is now structured internally and grounded on selected projects, ranking outputs, and evidence IDs.

Inspection endpoints are available at:

- `GET /v1/runs/{run_id}/trace`
- `GET /v1/runs/{run_id}/evidence`
- `GET /v1/runs/{run_id}/validation`
- `POST /v1/project-reviews`

Admin endpoints require authentication when `LDT_ADMIN_API_KEY` is configured:

```bash
curl -H "Authorization: Bearer $LDT_ADMIN_API_KEY" "$API_URL/v1/admin/sources"
```

## Minimal Usage Flow

1. Submit a run:

```json
{
  "municipality_id": "srb-belgrade",
  "category": "Environment",
  "year": 2024,
  "include_web_evidence": false,
  "language": "en",
  "top_n_projects": 3
}
```

2. Poll `GET /v1/runs/{run_id}` until `state` is `completed`.
3. Fetch final payload from `GET /v1/runs/{run_id}/result`.

## Run Tests

```bash
python -m pytest -q
```

## Serbia Context Pipeline

Serbia ingestion now uses a staged storage architecture:

- raw Serbia dataset rows are normalized into dedicated Supabase/Postgres tables
- mirrorable documents are fetched and uploaded into GCS
- retrieval-serving sources/chunks/embeddings remain in `sources` and `source_chunks` (`pgvector`)

Supported SQL dataset tables:

- `serbia_national_documents`
- `serbia_municipal_development_plans`
- `serbia_lsg_projects`
- `serbia_wbif_projects`
- `serbia_wbif_tas`

Stage 1, load normalized dataset rows into SQL:

```bash
python scripts/load_serbia_datasets.py --data-dir data
# or (Cloud Run-safe module entrypoint):
python -m src.jobs.load_serbia_datasets --data-dir data
```

Stage 2, resolve and mirror documents to GCS:

```bash
python scripts/mirror_serbia_documents.py --batch-size 200 --refresh-mode pending_only
# or (Cloud Run-safe module entrypoint):
python -m src.jobs.mirror_serbia_documents --batch-size 200 --refresh-mode pending_only
```

Stage 3, register and ingest mirrored plus metadata-only rows:

```bash
python scripts/ingest_serbia_sources.py --batch-size 200 --refresh-mode pending_only
# or (Cloud Run-safe module entrypoint):
python -m src.jobs.ingest_serbia_sources --batch-size 200 --refresh-mode pending_only
```

Local pre-deploy smoke (creates local chunk artifacts and runs semantic retrieval checks):

```bash
python scripts/local_serbia_rag_smoke.py --data-dir data --output-dir .local/serbia-smoke
```

Artifacts:

- `.local/serbia-smoke/chunks.json`
- `.local/serbia-smoke/smoke_report.json`
- `.local/serbia-smoke/smoke_report_full.json`

Legacy canonical export tooling is still available:

```bash
python scripts/export_serbia_context_bundle.py --data-dir data --output-dir data/normalized
```

## Current Scope Notes

- CSV parsing renders schema-aware row records for embedding instead of raw comma-joined lines.
- PDF parsing uses `PyMuPDF4LLM` markdown extraction when the dependency is installed.
- DOCX parsing uses `mammoth` semantic HTML conversion when the dependency is installed.
- Seed sources are opt-in through `LDT_AUTO_SEED_SOURCES=true`.
- Explicit admin ingestion is available through `/v1/admin/sources` and `/v1/admin/sources/{source_id}/ingest`.
- In `prod`, admin routes require `LDT_ADMIN_API_KEY`; if it is missing, admin routes return a configuration error.
- Live web research remains policy-controlled and placeholder-backed in the main recommendation workflow.
