#!/usr/bin/env sh
set -eu

: "${GCP_PROJECT:?Set GCP_PROJECT}"
: "${GCP_REGION:=asia-southeast1}"
: "${CLOUD_RUN_SERVICE:=ldt-de-v2}"

IMAGE="gcr.io/${GCP_PROJECT}/${CLOUD_RUN_SERVICE}:$(date +%Y%m%d%H%M%S)"

gcloud builds submit --project "${GCP_PROJECT}" --tag "${IMAGE}" .
gcloud run deploy "${CLOUD_RUN_SERVICE}" \
  --project "${GCP_PROJECT}" \
  --region "${GCP_REGION}" \
  --platform managed \
  --image "${IMAGE}" \
  --no-allow-unauthenticated
