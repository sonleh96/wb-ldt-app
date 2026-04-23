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
LDT_EMBEDDING_MODEL=text-embedding-3-large
LDT_EMBEDDING_DIMENSIONS=1536
LDT_OPENAI_API_KEY=...
LDT_OPENAI_MODEL=gpt-4.1-mini
LDT_AUTO_SEED_SOURCES=false
```

`LDT_EMBEDDING_DIMENSIONS` must match the actual embedding size stored in Supabase. If you change embedding model or
requested dimensions, recreate or migrate the `source_chunks.embedding` vector column accordingly.

### Cloud Run Env Mutation Commands

Use these command patterns to set/update env vars and secret-backed vars on Cloud Run:

```bash
# Plain env vars
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --update-env-vars="KEY1=value1,KEY2=value2"

# Secret-backed env vars
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --update-secrets="KEY1=secret-name-1:latest,KEY2=secret-name-2:latest"

# Remove plaintext env var after migrating to secret-backed env var
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --remove-env-vars="KEY1"
```

Executed reference commands for `wb-ldt-app-backend` are recorded in
`docs/deployment-backend-runbook-2026-04-20.md` under "Environment Variable Mutation Log".

### Add Supabase and OpenAI Secrets (Safe Workflow)

Use this flow to populate `LDT_DATABASE_URL` and `LDT_OPENAI_API_KEY` without pasting secrets into docs, chat, or shell history.

1. Set deployment targets:

```bash
export GCP_PROJECT=your-gcp-project
export GCP_REGION=asia-southeast1
export CLOUD_RUN_SERVICE=wb-ldt-app-backend
export RUNTIME_SA=wb-ldt-app-sv@${GCP_PROJECT}.iam.gserviceaccount.com
gcloud config set project "$GCP_PROJECT"
```

2. Create secrets if they do not already exist:

```bash
gcloud secrets describe ldt-database-url --project="$GCP_PROJECT" >/dev/null 2>&1 || \
  gcloud secrets create ldt-database-url --replication-policy=automatic --project="$GCP_PROJECT"

gcloud secrets describe ldt-openai-api-key --project="$GCP_PROJECT" >/dev/null 2>&1 || \
  gcloud secrets create ldt-openai-api-key --replication-policy=automatic --project="$GCP_PROJECT"
```

3. Add new secret versions using hidden terminal input:

```bash
read -s "?Paste Supabase/Postgres URL: " DB_URL; echo
printf '%s' "$DB_URL" | gcloud secrets versions add ldt-database-url --data-file=- --project="$GCP_PROJECT"
unset DB_URL

read -s "?Paste OpenAI API key: " OPENAI_KEY; echo
printf '%s' "$OPENAI_KEY" | gcloud secrets versions add ldt-openai-api-key --data-file=- --project="$GCP_PROJECT"
unset OPENAI_KEY
```

4. Ensure Cloud Run runtime SA can read those secrets:

```bash
gcloud secrets add-iam-policy-binding ldt-database-url \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="$GCP_PROJECT"

gcloud secrets add-iam-policy-binding ldt-openai-api-key \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="$GCP_PROJECT"
```

5. Bind secret-backed env vars and switch runtime mode:

```bash
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --update-secrets="LDT_DATABASE_URL=ldt-database-url:latest,LDT_OPENAI_API_KEY=ldt-openai-api-key:latest" \
  --update-env-vars="LDT_STORAGE_BACKEND=postgres,LDT_EMBEDDING_PROVIDER=openai,LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536"
```

6. Force a fresh revision to ensure latest secret versions are mounted:

```bash
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --update-env-vars="LDT_SECRETS_REFRESH_TS=$(date +%s)"
```

7. Verify configuration and health:

```bash
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format='yaml(status.latestReadyRevisionName,spec.template.spec.containers[0].env)'

ID_TOKEN="$(gcloud auth print-identity-token)"
API_URL="$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT" --region="$GCP_REGION" --format='value(status.url)')"
curl -si -H "Authorization: Bearer $ID_TOKEN" "$API_URL/health"
```

Supabase URL guidance:
- Use the Postgres connection URI from Supabase "Connect to your project".
- Prefer the connection-pooler URI (typically port `6543`) for Cloud Run.
- Do not use project HTTP URLs (`https://...supabase.co`) as `LDT_DATABASE_URL`.

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

For the exact command log of the first successful live Postgres/OpenAI batch and DB/API verification, see
`docs/deployment-backend-runbook-2026-04-20.md` under "First Real Postgres Serbia Batch + Verification (Live Service)".
For the concise CLI command taxonomy used to complete Stage 2 mirroring and verification, see
`docs/deployment-backend-runbook-2026-04-20.md` under "CLI Command Categories Used (Stage 2 Mirroring + Verification)".

Commands:

```bash
python scripts/load_serbia_datasets.py --data-dir data
python scripts/mirror_serbia_documents.py --batch-size 200 --refresh-mode pending_only
python scripts/ingest_serbia_sources.py --batch-size 200 --refresh-mode pending_only
```

Cloud Run jobs should prefer module entrypoints (the container includes `src/` but not `scripts/`):

```bash
python -m src.jobs.load_serbia_datasets --data-dir data
python -m src.jobs.mirror_serbia_documents --batch-size 200 --refresh-mode pending_only
python -m src.jobs.ingest_serbia_sources --batch-size 200 --refresh-mode pending_only
```

Local pre-deploy validation:

```bash
python scripts/local_serbia_rag_smoke.py --data-dir data --output-dir .local/serbia-smoke
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
