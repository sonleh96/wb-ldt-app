# GCP / Supabase Deployment

This guide describes the target deployment shape:

- Google Cloud Run for the FastAPI backend
- Google Cloud Storage for full source documents
- Supabase Postgres with `pgvector` for metadata, chunks, embeddings, runs, traces, and reviews

For an end-to-end bootstrap sequence that was executed successfully in a minimally provisioned project, see
`docs/deployment-backend-runbook-2026-04-20.md`.

## Required Services

1. Create a GCS bucket for source documents.
2. Create a Supabase project.
3. Enable the `vector` extension in Supabase.
4. Deploy this backend to Cloud Run.
5. Configure Cloud Run environment variables or secret bindings.

## Environment Variables

Minimum production configuration:

```bash
LDT_ENVIRONMENT=prod
LDT_STORAGE_BACKEND=postgres
LDT_DATABASE_URL=postgresql://...
LDT_DOCUMENT_STORE_BACKEND=gcs
LDT_GCP_PROJECT=your-gcp-project
LDT_GCS_BUCKET=your-document-bucket
LDT_GCS_PREFIX=ldt/sources
LDT_ADMIN_API_KEY=strong-secret-value
LDT_SERBIA_DATASET_LOADING_ENABLED=true
LDT_SERBIA_DOCUMENT_MIRRORING_ENABLED=true
LDT_SERBIA_INGESTION_BATCH_SIZE=200
LDT_SERBIA_FETCH_TIMEOUT_SECONDS=30
LDT_SERBIA_FETCH_MAX_RETRIES=2
LDT_SERBIA_REFRESH_MODE=pending_only
LDT_EMBEDDING_PROVIDER=openai
LDT_EMBEDDING_MODEL=text-embedding-3-small
LDT_EMBEDDING_DIMENSIONS=1536
LDT_OPENAI_API_KEY=...
LDT_OPENAI_MODEL=gpt-4.1-mini
LDT_AUTO_SEED_SOURCES=false
```

`LDT_EMBEDDING_DIMENSIONS` must match the actual embedding size stored in Supabase. If you change embedding model or
requested dimensions, recreate or migrate the `source_chunks.embedding` vector column accordingly.

## Serbia Ingestion Stages

The production Serbia path is explicitly staged:

1. Load raw files into Supabase dataset tables:
   - `serbia_national_documents`
   - `serbia_municipal_development_plans`
   - `serbia_lsg_projects`
   - `serbia_wbif_projects`
   - `serbia_wbif_tas`
2. Mirror resolvable document URLs from those tables into GCS.
3. Register mirrored/structured rows into `sources` and ingest into `source_chunks` embeddings.

Commands:

```bash
python scripts/load_serbia_datasets.py --data-dir data
python scripts/mirror_serbia_documents.py --batch-size 200 --refresh-mode pending_only
python scripts/ingest_serbia_sources.py --batch-size 200 --refresh-mode pending_only
```

## GCS Naming Conventions

National policy:

```text
gs://{bucket}/ldt/sources/national/{country_code}/{category_slug}/{year}/{doc-slug}__{lang}__{year}__v{version}.{ext}
```

Municipal policy:

```text
gs://{bucket}/ldt/sources/municipal/{municipality_id}/{category_slug}/{year}/{doc-slug}__{lang}__{year}__v{version}.{ext}
```

Project document:

```text
gs://{bucket}/ldt/sources/projects/{municipality_id}/{category_slug}/{project_id}/{year}/{doc-slug}__{lang}__{year}__v{version}.{ext}
```

Examples:

```text
gs://ldt-documents/ldt/sources/national/srb/environment/2024/national-air-quality-program__en__2024__v1.pdf
gs://ldt-documents/ldt/sources/municipal/srb-belgrade/environment/2024/belgrade-green-city-action-plan__en__2024__v1.pdf
gs://ldt-documents/ldt/sources/projects/srb-belgrade/environment/proj-001/2024/urban-air-monitoring-expansion-concept-note__en__2024__v1.pdf
```

## Source Registration

After uploading a document to GCS, register it:

```json
{
  "source_id": "mun-srb-belgrade-environment-2024-belgrade-green-city-action-plan-en-v1",
  "source_type": "municipal_development_plan",
  "title": "Belgrade Green City Action Plan",
  "uri": "gs://ldt-documents/ldt/sources/municipal/srb-belgrade/environment/2024/belgrade-green-city-action-plan__en__2024__v1.pdf",
  "municipality_id": "srb-belgrade",
  "category": "Environment",
  "mime_type": "application/pdf"
}
```

Then ingest it:

```bash
curl -X POST \
  -H "Authorization: Bearer $LDT_ADMIN_API_KEY" \
  "$API_URL/v1/admin/sources/{source_id}/ingest"
```

The backend validates that the GCS object exists, downloads it to a temporary local path for parsing, chunks it, embeds
it, and stores chunk metadata plus embeddings in the configured source repository.

## Cloud Run Deployment

Using the deploy script:

```bash
export GCP_PROJECT=your-gcp-project
export GCP_REGION=asia-southeast1
export CLOUD_RUN_SERVICE=ldt-de-v2
./scripts/deploy_cloud_run.sh
```

Using Cloud Build:

```bash
gcloud builds submit --config cloudbuild.yaml --project your-gcp-project
```

After deployment, configure environment variables/secrets on the Cloud Run service. The image alone is not enough for
production because Supabase, OpenAI, and GCS settings are environment-specific.

Admin routes are protected by `LDT_ADMIN_API_KEY` at the application layer. Use:

```text
Authorization: Bearer <LDT_ADMIN_API_KEY>
```

## IAM

The Cloud Run runtime service account needs permission to read GCS source documents.

For register-and-ingest only:

```text
roles/storage.objectViewer
```

If a future upload endpoint writes documents to GCS, use a narrower bucket-level writer/admin role for that service
account.

## Smoke Tests

```bash
TOKEN="$(gcloud auth print-identity-token)"
curl -H "Authorization: Bearer $TOKEN" "$API_URL/health"
curl -H "Authorization: Bearer $TOKEN" "$API_URL/version"
curl -H "Authorization: Bearer $TOKEN" "$API_URL/capabilities"
```

Then register and ingest one small `.txt` source from GCS before testing PDFs/DOCX files.

## Production Risks

- Admin routes require API-key authentication and secret rotation policy.
- Long-running ingestion currently runs inside the API service, not a durable worker queue.
- Supabase connection limits must be considered when Cloud Run concurrency or max instances increase.
- Large PDFs/DOCX files can hit Cloud Run memory or timeout limits.
