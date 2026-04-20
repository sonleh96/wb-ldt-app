# LDT Decision Engine v2

Backend-first replacement for the legacy Streamlit prototype.

## Read This First

This repo keeps two README-style docs for every delivered batch:

- Quick setup and usage guide: [README Quickstart](d:/Work/WB/wb-ldt-app/docs/README_QUICKSTART.md)
- Detailed architecture and audit guide: [README Technical Audit](d:/Work/WB/wb-ldt-app/docs/README_TECHNICAL_AUDIT.md)
- GCP/Supabase deployment guide: [GCP Deployment](docs/deployment-gcp.md)
- Fresh-session context bridge: [Session Handoff](d:/Work/WB/wb-ldt-app/docs/SESSION_HANDOFF.md)

## Documentation Policy

For every future batch, both docs above will be updated:

1. `README_QUICKSTART.md`: setup, endpoints, common operations.
2. `README_TECHNICAL_AUDIT.md`: architecture, module map, contracts, state transitions, and validation notes.
3. Runtime code must include module/class/function docstrings. This is enforced by `tests/unit/test_docstring_policy.py`.

## Current Status

Batch 1, Batch 2, Batch 3 strategy implementation, and Prompts 11-20 are now integrated:

- typed query planning with diagnostics
- semantic chunking with sentence-embedding breakpoint detection
- contextual chunk headers embedded with document/section metadata
- parser-backed PDF and DOCX ingestion for structured source text
- schema-aware CSV row rendering for contextual tabular embeddings
- hybrid retrieval with RRF fusion and diagnostics
- retrieval-time same-source context window expansion around matched chunks
- optional PostgreSQL + pgvector chunk storage path for semantic retrieval
- GCS-backed full-document storage for source registration and ingestion
- staged Serbia context ingestion (SQL dataset tables -> GCS mirroring -> source/chunk embedding ingestion)
- Cloud Run deployment packaging
- evidence-card context packing
- OpenAI-backed recommendation candidate generation with prompt versioning
- deterministic project filtering, scoring, and selection with ranking breakdowns
- grounded narrative explanation generation with evidence references
- independently callable project review workflow with caching
- modular run validation with inspectable failure policies
- run trace, evidence, and validation inspection endpoints
- evaluation fixtures and acceptance harness
- frontend-facing stable JSON contracts and migration notes
- strict evaluation gate that can fail runs safely
