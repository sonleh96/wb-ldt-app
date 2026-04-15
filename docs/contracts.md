# API Contracts

This document captures the stable JSON shapes for the main frontend-facing endpoints.

## `POST /v1/runs/recommendations`

Returns `202 Accepted` with a polling payload:

```json
{
  "run_id": "uuid",
  "state": "queued",
  "created_at": "2026-04-03T00:00:00+00:00",
  "updated_at": "2026-04-03T00:00:00+00:00",
  "current_node": "create_run",
  "progress": {
    "completed_steps": 0,
    "total_steps": 13,
    "percent": 0.0,
    "current_node": "create_run"
  },
  "message": null
}
```

## `GET /v1/runs/{run_id}`

Uses the same status shape as the submit response, with `progress` updated for polling.

## `GET /v1/runs/{run_id}/result`

Completed recommendation result shape:

```json
{
  "run_id": "uuid",
  "status": "completed",
  "municipality_id": "srb-belgrade",
  "category": "Environment",
  "run_metadata": {},
  "context": {},
  "indicator_summary": [],
  "recommendation_candidates": [],
  "selected_projects": [],
  "ranking": [],
  "explanation": "string",
  "explanation_narrative": {
    "executive_summary": "string",
    "rationale": "string",
    "caveats": [],
    "cited_evidence_ids": []
  },
  "evidence_bundle_id": "bundle-id",
  "evidence_bundle_summary": {
    "bundle_id": "bundle-id",
    "item_count": 0,
    "evidence_items": []
  },
  "citations": [],
  "validation_summary": "passed",
  "validation_report": {},
  "context_pack_summary": {},
  "retrieval_diagnostics": {},
  "evaluation_report": {}
}
```

## Inspection Endpoints

- `GET /v1/runs/{run_id}/trace`
- `GET /v1/runs/{run_id}/evidence`
- `GET /v1/runs/{run_id}/validation`

These return debug/inspection payloads for engineering and admin use.

## `POST /v1/project-reviews`

```json
{
  "run_id": "uuid",
  "project_id": "proj-001",
  "include_web_evidence": false
}
```

Response:

```json
{
  "run_id": "uuid",
  "project_review": {
    "project_id": "proj-001",
    "summary": "string",
    "municipality_relevance": "string",
    "readiness": "string",
    "financing_signals": "string",
    "implementation_considerations": [],
    "risks_and_caveats": [],
    "citation_ids": []
  },
  "validation_summary": "passed"
}
```

## Error Payloads

All error responses use the shared structured error contract:

```json
{
  "request_id": "request-id",
  "error": {
    "code": "error_code",
    "message": "Human-readable message",
    "target": "optional-field",
    "metadata": {}
  }
}
```
