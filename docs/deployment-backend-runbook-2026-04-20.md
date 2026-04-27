# Backend Deployment Runbook (Successful Path, 2026-04-20)

This document records the exact sequence that successfully deployed the backend in a minimally provisioned GCP project.

## Deployment Target

- Project: `wb-ldt`
- Region: `asia-southeast1`
- Cloud Run service: `wb-ldt-app-backend`
- Runtime service account: `wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com`
- Deploy mode: private service (`--no-allow-unauthenticated`)
- Admin app auth: `LDT_ADMIN_API_KEY` (application-level)

## Why This Runbook Exists

The project had only baseline setup (project + service account). Cloud Run, Artifact Registry, and Cloud Build resources/APIs were not fully ready yet. This sequence handles bootstrap and deploy in one repeatable path.

## Preconditions

1. You are at repository root: `wb-ldt-app`.
2. `gcloud` is installed and authenticated.
3. The deploying principal has enough IAM on project `wb-ldt` (owner/editor preferred for first bootstrap).

## Step-by-Step Commands

1. Set target values:

```bash
export GCP_PROJECT="wb-ldt"
export GCP_REGION="asia-southeast1"
export CLOUD_RUN_SERVICE="wb-ldt-app-backend"
export RUNTIME_SA="wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com"
```

2. Set active project:

```bash
gcloud config set project "$GCP_PROJECT"
```

3. Enable required APIs (bootstrap):

```bash
gcloud services enable \
  serviceusage.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$GCP_PROJECT"
```

4. If Cloud Build create permission fails (`cloudbuild.builds.create`), grant this to the deploying user:

```bash
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="user:YOUR_EMAIL" \
  --role="roles/cloudbuild.builds.editor"
```

5. Build and push image via Cloud Build:

```bash
export IMAGE="asia-southeast1-docker.pkg.dev/${GCP_PROJECT}/cloud-run-source-deploy/${CLOUD_RUN_SERVICE}:manual-$(date +%Y%m%d%H%M%S)"
gcloud builds submit --project="$GCP_PROJECT" --tag="$IMAGE"
```

6. Generate admin API key (do not commit this value):

```bash
export LDT_ADMIN_API_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
```

7. Deploy to Cloud Run with production mode + admin key + dedicated runtime SA:

```bash
gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --image="$IMAGE" \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account="$RUNTIME_SA" \
  --set-env-vars="LDT_ENVIRONMENT=prod,LDT_ADMIN_API_KEY=${LDT_ADMIN_API_KEY}"
```

8. Confirm runtime config:

```bash
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format='yaml(status.url,status.latestReadyRevisionName,spec.template.spec.serviceAccountName,spec.template.spec.containers[0].env)'
```

9. Smoke test (private Cloud Run + app-level admin auth):

```bash
export API_URL="$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT" --region="$GCP_REGION" --format='value(status.url)')"
export ID_TOKEN="$(gcloud auth print-identity-token)"

# Health should succeed (Cloud Run auth only)
curl -si -H "Authorization: Bearer $ID_TOKEN" "$API_URL/health"

# Admin without app key should fail (expected 401/403)
curl -si -H "Authorization: Bearer $ID_TOKEN" "$API_URL/v1/admin/sources"

# Admin with both auth layers should succeed
# NOTE: keep Cloud Run identity token in X-Serverless-Authorization
# and use Authorization for app admin key.
curl -si \
  -H "X-Serverless-Authorization: Bearer $ID_TOKEN" \
  -H "Authorization: Bearer $LDT_ADMIN_API_KEY" \
  "$API_URL/v1/admin/sources"
```

## Important Header Behavior (Cloud Run + App Auth)

For private Cloud Run services, using `Authorization` for the ID token can conflict with application-level `Authorization` handling. The reliable pattern for admin endpoints is:

- `X-Serverless-Authorization: Bearer <identity-token>` for Cloud Run auth
- `Authorization: Bearer <LDT_ADMIN_API_KEY>` for backend admin auth

## Outcomes Verified in This Run

- Service URL: `https://wb-ldt-app-backend-bhqks3bqvq-as.a.run.app`
- Latest ready revision at time of validation: `wb-ldt-app-backend-00008-leq`
- Runtime SA correctly set to: `wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com`
- `/health` returned `200`
- `/v1/admin/sources` returned `403` without admin key
- `/v1/admin/sources` returned `200` with dual-header auth pattern

## Environment Variable Mutation Log

All commands below were executed against:

- Project: `wb-ldt`
- Region: `asia-southeast1`
- Service: `wb-ldt-app-backend`

1. Initial bootstrap deploy (plaintext admin key; later migrated to secret):

```bash
gcloud run deploy wb-ldt-app-backend \
  --project=wb-ldt \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/wb-ldt/cloud-run-source-deploy/wb-ldt-app-backend:manual-test \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com \
  --set-env-vars=LDT_ENVIRONMENT=prod,LDT_ADMIN_API_KEY=<generated-key>
```

2. Admin key migration to Secret Manager (remove plaintext env var):

```bash
gcloud run services update wb-ldt-app-backend \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-secrets=LDT_ADMIN_API_KEY=ldt-admin-api-key:latest \
  --remove-env-vars=LDT_ADMIN_API_KEY
```

3. Runtime environment update for current backend mode:

```bash
gcloud run services update wb-ldt-app-backend \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-env-vars=LDT_STORAGE_BACKEND=memory,LDT_DOCUMENT_STORE_BACKEND=gcs,LDT_GCP_PROJECT=wb-ldt,LDT_GCS_BUCKET=wb-ldt,LDT_GCS_PREFIX=ldt/sources,LDT_SERBIA_DATASET_LOADING_ENABLED=true,LDT_SERBIA_DOCUMENT_MIRRORING_ENABLED=true,LDT_SERBIA_INGESTION_BATCH_SIZE=200,LDT_SERBIA_FETCH_TIMEOUT_SECONDS=30,LDT_SERBIA_FETCH_MAX_RETRIES=2,LDT_SERBIA_REFRESH_MODE=pending_only,LDT_EMBEDDING_PROVIDER=local,LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=256,LDT_OPENAI_MODEL=gpt-4.1-mini,LDT_AUTO_SEED_SOURCES=false
```

4. Secret env bindings prepared for future production switch:

```bash
gcloud run services update wb-ldt-app-backend \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-secrets=LDT_DATABASE_URL=ldt-database-url:latest,LDT_OPENAI_API_KEY=ldt-openai-api-key:latest
```

5. Embedding model uplift to multilingual-stronger OpenAI model (`text-embedding-3-large`) while keeping
   pgvector-compatible dimensions (`1536`):

```bash
gcloud run services update wb-ldt-app-backend \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-env-vars=LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536

gcloud alpha run jobs update wb-ldt-serbia-stage3-ingest \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-env-vars=LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536

gcloud alpha run jobs update wb-ldt-serbia-first-batch \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-env-vars=LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536

gcloud alpha run jobs update wb-ldt-serbia-stage2-mirror \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-env-vars=LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536
```

6. Runtime cost optimization + longer Stage 3 timeout (applied 2026-04-24):

```bash
gcloud run services update wb-ldt-app-backend \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --update-env-vars=LDT_EMBEDDING_MODEL=text-embedding-3-small,LDT_EMBEDDING_DIMENSIONS=1536

gcloud alpha run jobs update wb-ldt-serbia-stage3-ingest \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --task-timeout=28800s \
  --update-env-vars=LDT_EMBEDDING_MODEL=text-embedding-3-small,LDT_EMBEDDING_DIMENSIONS=1536
```

Current note:
- `LDT_DATABASE_URL` and `LDT_OPENAI_API_KEY` are currently bound to placeholder secret values and must be replaced with real values before switching to `LDT_STORAGE_BACKEND=postgres` and OpenAI embeddings.
- Latest live settings (2026-04-24): `LDT_EMBEDDING_MODEL=text-embedding-3-small`, `LDT_EMBEDDING_DIMENSIONS=1536`, and Stage 3 Cloud Run Job `timeoutSeconds=28800`.

## Replacing Supabase and OpenAI Placeholders (No Secret Sharing)

Use this flow when real credentials are ready:

```bash
export GCP_PROJECT="wb-ldt"
export GCP_REGION="asia-southeast1"
export CLOUD_RUN_SERVICE="wb-ldt-app-backend"
export RUNTIME_SA="wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com"
gcloud config set project "$GCP_PROJECT"

# Hidden terminal input for secret payloads
read -s "?Paste Supabase/Postgres URL: " DB_URL; echo
printf '%s' "$DB_URL" | gcloud secrets versions add ldt-database-url --data-file=- --project="$GCP_PROJECT"
unset DB_URL

read -s "?Paste OpenAI API key: " OPENAI_KEY; echo
printf '%s' "$OPENAI_KEY" | gcloud secrets versions add ldt-openai-api-key --data-file=- --project="$GCP_PROJECT"
unset OPENAI_KEY

# Ensure runtime SA can read secrets
gcloud secrets add-iam-policy-binding ldt-database-url \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="$GCP_PROJECT"

gcloud secrets add-iam-policy-binding ldt-openai-api-key \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="$GCP_PROJECT"

# Switch runtime mode to Postgres + OpenAI embeddings
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --update-secrets="LDT_DATABASE_URL=ldt-database-url:latest,LDT_OPENAI_API_KEY=ldt-openai-api-key:latest" \
  --update-env-vars="LDT_STORAGE_BACKEND=postgres,LDT_EMBEDDING_PROVIDER=openai,LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536"

# Force new revision to refresh mounted secret versions
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --update-env-vars="LDT_SECRETS_REFRESH_TS=$(date +%s)"
```

Verification:

```bash
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format='yaml(status.latestReadyRevisionName,spec.template.spec.containers[0].env)'
```

If startup fails after switching to Postgres/OpenAI:
- check revision logs for the exact exception
- ensure `LDT_DATABASE_URL` is a valid Postgres URI (not Supabase HTTP URL)
- confirm `LDT_EMBEDDING_DIMENSIONS` matches chosen embedding configuration (`1536` for `text-embedding-3-large` in this deployment)

## IAM and Guardrail Commands Executed

```bash
# Allow runtime service account to read GCS source objects
gcloud storage buckets add-iam-policy-binding gs://wb-ldt \
  --member='serviceAccount:wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com' \
  --role='roles/storage.objectViewer'

# Cloud Run service guardrails
gcloud run services update wb-ldt-app-backend \
  --region=asia-southeast1 \
  --project=wb-ldt \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=20 \
  --timeout=300
```

## Monitoring Baseline Executed

```bash
# Enable Monitoring API
gcloud services enable monitoring.googleapis.com --project=wb-ldt

# Create log-based metric for backend HTTP 5xx
gcloud logging metrics create wb_ldt_backend_http_5xx \
  --project=wb-ldt \
  --description='Count Cloud Run 5xx responses for wb-ldt-app-backend' \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="wb-ldt-app-backend" AND httpRequest.status>=500'

# Create alert policy from checked-in file
gcloud alpha monitoring policies create \
  --project=wb-ldt \
  --policy-from-file=infra/monitoring/wb-ldt-backend-5xx-alert-policy.json
```

Created policy:
- `projects/wb-ldt/alertPolicies/13632477850689605212` (`wb-ldt-app-backend 5xx alerts`)

## First Real Postgres Serbia Batch + Verification (Live Service)

This section records the exact successful path used on April 20, 2026 to run the first production-like Serbia batch
using:

- `LDT_STORAGE_BACKEND=postgres`
- `LDT_DOCUMENT_STORE_BACKEND=gcs`
- `LDT_EMBEDDING_PROVIDER=openai`
- secret-backed `LDT_DATABASE_URL` and `LDT_OPENAI_API_KEY`

### Why Cloud Run Jobs Were Used

Two operational constraints were encountered:

1. Local runner could not resolve Supabase hostnames from this workstation runtime (`psycopg ... failed to resolve host`).
2. The deployed service image did not include local `scripts/` and `data/` paths inside the container filesystem.

The working solution was to run ingestion inside Cloud Run Jobs and stage raw Serbia files in GCS for the job to pull.

### Operator Shell Setup (Recorded)

```bash
export GCP_PROJECT="wb-ldt"
export GCP_REGION="asia-southeast1"
export CLOUD_RUN_SERVICE="wb-ldt-app-backend"
export RUNTIME_SA="wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com"
export GCS_BUCKET="wb-ldt"
export GCS_DATA_PREFIX="bootstrap/serbia-data"

# Workaround for local gcloud resolving to an incompatible Python runtime.
export CLOUDSDK_PYTHON=/opt/homebrew/bin/python3.11
```

### 1) Confirm Live Service Config

```bash
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format='yaml(status.url,spec.template.spec.containers[0].env)'
```

Expected key values in this successful run:

- `LDT_STORAGE_BACKEND=postgres`
- `LDT_EMBEDDING_PROVIDER=openai`
- `LDT_EMBEDDING_MODEL=text-embedding-3-large`
- `LDT_EMBEDDING_DIMENSIONS=1536`
- `LDT_DATABASE_URL` from `ldt-database-url:latest`
- `LDT_OPENAI_API_KEY` from `ldt-openai-api-key:latest`

### 2) Stage the Five Raw Serbia Files in GCS

```bash
gcloud storage cp \
  data/national_strategy_policies_law.xlsx \
  data/serbia_local_dev_plans_final.csv \
  data/serbia_lsg_projects.xlsx \
  data/wbif_projects.csv \
  data/wbif_TAs.csv \
  "gs://${GCS_BUCKET}/${GCS_DATA_PREFIX}/"
```

### 3) Deploy and Run the First Batch Cloud Run Job

1. Fetch the exact image digest currently deployed by the live service:

```bash
IMAGE="$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --format='value(spec.template.spec.containers[0].image)')"
```

2. Build inline runner code (base64-encoded to avoid shell escaping issues):

```bash
BATCH_SCRIPT_B64="$(python3 - <<'PY'
import base64

script = r'''
from pathlib import Path
import json
from google.cloud import storage
from src.core.container import ServiceContainer

bucket = "wb-ldt"
prefix = "bootstrap/serbia-data"
files = [
    "national_strategy_policies_law.xlsx",
    "serbia_local_dev_plans_final.csv",
    "serbia_lsg_projects.xlsx",
    "wbif_projects.csv",
    "wbif_TAs.csv",
]

data_dir = Path("/tmp/data")
data_dir.mkdir(parents=True, exist_ok=True)
client = storage.Client(project="wb-ldt")
b = client.bucket(bucket)
for name in files:
    b.blob(f"{prefix}/{name}").download_to_filename(str(data_dir / name))

container = ServiceContainer()
load = container.serbia_dataset_loader_service.load_from_data_dir(data_dir)
ingest = container.serbia_source_ingestion_service.ingest_pending_rows(
    batch_size=20,
    refresh_mode="pending_only",
)

print(json.dumps({
    "load_total_rows": load.total_rows,
    "load_family_counts": load.family_counts,
    "ingest": {
        "scanned_rows": ingest.scanned_rows,
        "ingested_document_rows": ingest.ingested_document_rows,
        "ingested_structured_rows": ingest.ingested_structured_rows,
        "skipped_rows": ingest.skipped_rows,
        "failed_rows": ingest.failed_rows,
    },
}, ensure_ascii=True))
'''
print(base64.b64encode(script.encode("utf-8")).decode("ascii"))
PY
)"
```

3. Deploy job:

```bash
gcloud alpha run jobs deploy wb-ldt-serbia-first-batch \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --image="$IMAGE" \
  --service-account="$RUNTIME_SA" \
  --set-secrets="LDT_DATABASE_URL=ldt-database-url:latest,LDT_OPENAI_API_KEY=ldt-openai-api-key:latest" \
  --set-env-vars="LDT_ENVIRONMENT=prod,LDT_STORAGE_BACKEND=postgres,LDT_DOCUMENT_STORE_BACKEND=gcs,LDT_GCP_PROJECT=wb-ldt,LDT_GCS_BUCKET=wb-ldt,LDT_GCS_PREFIX=ldt/sources,LDT_SERBIA_DATASET_LOADING_ENABLED=true,LDT_SERBIA_DOCUMENT_MIRRORING_ENABLED=true,LDT_SERBIA_INGESTION_BATCH_SIZE=200,LDT_SERBIA_FETCH_TIMEOUT_SECONDS=5,LDT_SERBIA_FETCH_MAX_RETRIES=0,LDT_SERBIA_REFRESH_MODE=pending_only,LDT_EMBEDDING_PROVIDER=openai,LDT_EMBEDDING_MODEL=text-embedding-3-large,LDT_EMBEDDING_DIMENSIONS=1536,LDT_OPENAI_MODEL=gpt-4.1-mini,LDT_AUTO_SEED_SOURCES=false" \
  --command=python \
  --args=-c,"import base64;exec(base64.b64decode('${BATCH_SCRIPT_B64}').decode())"
```

4. Execute job and wait:

```bash
gcloud alpha run jobs execute wb-ldt-serbia-first-batch \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --wait
```

Successful execution recorded:

- Execution name: `wb-ldt-serbia-first-batch-pqqkd`
- Status: `Completed=True`
- Runtime message: `Execution completed successfully in 10m26.68s`

5. Inspect summary payload from logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="wb-ldt-serbia-first-batch-pqqkd"' \
  --project="$GCP_PROJECT" \
  --limit=200 \
  --format=json
```

Observed summary payload:

- `load_total_rows=408`
- `load_family_counts={24,161,107,77,39}` by family:
  - national: `24`
  - municipal: `161`
  - LSG projects: `107`
  - WBIF projects: `77`
  - WBIF TAs: `39`
- `ingest.scanned_rows=20`
- `ingest.ingested_structured_rows=20`
- `ingest.ingested_document_rows=0`
- `ingest.failed_rows=0`

### 4) API-Level Verification (Admin Endpoints)

Use dual-header auth for private Cloud Run:

```bash
API_URL="$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT" --region="$GCP_REGION" --format='value(status.url)')"
ID_TOKEN="$(gcloud auth print-identity-token)"
ADMIN_KEY="$(gcloud secrets versions access latest --secret=ldt-admin-api-key --project="$GCP_PROJECT")"

curl -sf \
  -H "X-Serverless-Authorization: Bearer $ID_TOKEN" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  "$API_URL/v1/admin/datasets/rows?limit=1000" > /tmp/serbia_rows.json

curl -sf \
  -H "X-Serverless-Authorization: Bearer $ID_TOKEN" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  "$API_URL/v1/admin/sources" > /tmp/all_sources.json
```

Observed API-level counts after run:

- Dataset rows total: `408`
- Ingestion readiness:
  - `metadata_only=223`
  - `missing_url=10`
  - `ready=130`
  - `needs_resolver=45`
- Mirror status:
  - `not_started=408`
- Dataset rows with `source_id`: `20`
- Dataset rows with `gcs_uri`: `0`
- Sources total: `20`
- Serbia sources total: `20`
- Serbia sources URI profile:
  - `structured://...` => `20`
  - `gs://...` => `0`

### 5) DB-Level Verification (Chunks + Embeddings)

Deploy a one-off verification job that reads Postgres directly:

```bash
gcloud alpha run jobs deploy wb-ldt-serbia-verify-counts \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --image="$IMAGE" \
  --service-account="$RUNTIME_SA" \
  --set-secrets="LDT_DATABASE_URL=ldt-database-url:latest" \
  --set-env-vars="PYTHONUNBUFFERED=1" \
  --command=python \
  --args=-c,"import os;import psycopg;conn=psycopg.connect(os.environ['LDT_DATABASE_URL']);cur=conn.cursor();cur.execute('select count(*) from sources');print('sources_total='+str(cur.fetchone()[0]));cur.execute(\"select count(*) from sources where source_id like 'serbia-%'\");print('serbia_sources_total='+str(cur.fetchone()[0]));cur.execute('select count(*) from source_chunks');print('source_chunks_total='+str(cur.fetchone()[0]));cur.execute(\"select count(*) from source_chunks where source_id like 'serbia-%'\");print('serbia_source_chunks_total='+str(cur.fetchone()[0]));cur.execute(\"select count(*) from source_chunks where source_id like 'serbia-%' and embedding is not null\");print('serbia_chunks_with_embedding='+str(cur.fetchone()[0]));cur.close();conn.close()"
```

Execute:

```bash
gcloud alpha run jobs execute wb-ldt-serbia-verify-counts \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --wait
```

Successful execution recorded:

- Execution name: `wb-ldt-serbia-verify-counts-jm2xr`
- Status: `Completed=True`

Read logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="wb-ldt-serbia-verify-counts-jm2xr"' \
  --project="$GCP_PROJECT" \
  --limit=50 \
  --format='value(textPayload)'
```

Observed DB-level verification:

- `sources_total=20`
- `serbia_sources_total=20`
- `source_chunks_total=20`
- `serbia_source_chunks_total=20`
- `serbia_chunks_with_embedding=20`

### Current Interpretation

The first live Postgres/OpenAI batch completed successfully for:

- full Serbia dataset row loading (`408` rows),
- structured-row source registration for the first ingestion window (`20` rows),
- chunk creation + embeddings (`20` Serbia chunks with non-null embedding vectors).

Document mirroring and document-backed ingestion were intentionally not part of this first successful run and remain to
be executed in the next stage.

## CLI Command Categories Used (Stage 2 Mirroring + Verification)

This is a concise map of the command types used to complete Stage 2 safely while skipping already mirrored rows.

1. Build and publish patched backend image

```bash
gcloud builds submit --project="$GCP_PROJECT" --tag="$IMAGE_TAG"
```

2. Deploy/update Cloud Run Job configuration

```bash
gcloud alpha run jobs deploy wb-ldt-serbia-stage2-mirror \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --image="$IMAGE_TAG" \
  --set-secrets=... \
  --set-env-vars=... \
  --command=python \
  --args=-c,"..."
```

3. Execute mirroring job runs and wait for completion

```bash
gcloud alpha run jobs execute wb-ldt-serbia-stage2-mirror \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --wait
```

4. Inspect execution status / troubleshoot failures

```bash
gcloud alpha run jobs executions list --project="$GCP_PROJECT" --region="$GCP_REGION" --job=wb-ldt-serbia-stage2-mirror
gcloud alpha run jobs executions describe <execution-name> --project="$GCP_PROJECT" --region="$GCP_REGION"
gcloud alpha run jobs executions cancel <execution-name> --project="$GCP_PROJECT" --region="$GCP_REGION" --quiet
```

5. Pull runtime logs and parse structured job output

```bash
gcloud logging read 'resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="<execution-name>"' \
  --project="$GCP_PROJECT" \
  --limit=200 \
  --format=json > /tmp/<execution>.json

python3 - <<'PY'
import json
entries = json.load(open('/tmp/<execution>.json'))
# extract jsonPayload summary blocks
PY
```

6. Query live admin API state for before/after verification

```bash
ID_TOKEN="$(gcloud auth print-identity-token)"
ADMIN_KEY="$(gcloud secrets versions access latest --secret=ldt-admin-api-key --project="$GCP_PROJECT")"
curl -sf \
  -H "X-Serverless-Authorization: Bearer $ID_TOKEN" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  "$API_URL/v1/admin/datasets/rows?limit=1000" > /tmp/rows.json
```

7. Compute summaries from API snapshots

```bash
python3 - <<'PY'
import json
from collections import Counter
rows = json.load(open('/tmp/rows.json'))
print(Counter(r.get('mirror_status') for r in rows))
PY
```

### Notes From This Run Pattern

- `pending_only` mode was intentionally used to skip already mirrored rows.
- Fairness fix was deployed via new image build before rerunning Stage 2.
- For local environments where `gcloud` resolves to an incompatible Python, `CLOUDSDK_PYTHON` was set explicitly.

## Recommended Next Hardening

1. Keep periodic rotation for `ldt-admin-api-key`.
2. Keep periodic rotation for `ldt-database-url` and `ldt-openai-api-key`.
3. Maintain alert policy notification channels (email/PagerDuty/etc.) as ops processes mature.
