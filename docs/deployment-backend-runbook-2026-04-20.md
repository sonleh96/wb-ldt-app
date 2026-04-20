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
- Latest ready revision at time of validation: `wb-ldt-app-backend-00002-wor`
- Runtime SA correctly set to: `wb-ldt-app-sv@wb-ldt.iam.gserviceaccount.com`
- `/health` returned `200`
- `/v1/admin/sources` returned `403` without admin key
- `/v1/admin/sources` returned `200` with dual-header auth pattern

## Recommended Next Hardening

1. Move `LDT_ADMIN_API_KEY` from plain env var to Secret Manager binding.
2. Rotate the admin key used during this bootstrap run.
3. Add remaining production env vars (`LDT_DATABASE_URL`, `LDT_GCS_BUCKET`, `LDT_OPENAI_API_KEY`, etc.).

