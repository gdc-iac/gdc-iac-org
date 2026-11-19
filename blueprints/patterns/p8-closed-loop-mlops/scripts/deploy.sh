#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

PROJECT_ID=$(gcloud config get-value project)
REGISTRY_HOST="us-central1-docker.pkg.dev/${PROJECT_ID}/blueprint-images"
BUCKET_NAME="${PROJECT_ID}-mlops-data"
BUCKET_URI="gs://${BUCKET_NAME}"

echo "Deploying Pattern 8 with REGISTRY_HOST=${REGISTRY_HOST} and BUCKET_NAME=${BUCKET_NAME}..."

# Ensure bucket exists
if ! gcloud storage buckets describe "${BUCKET_URI}" >/dev/null 2>&1; then
    echo "Creating bucket ${BUCKET_URI}..."
    gcloud storage buckets create "${BUCKET_URI}" --project="${PROJECT_ID}" --location=us-central1
else
    echo "Bucket ${BUCKET_URI} already exists."
fi

# Deploy Pipeline Job
echo "Deploying Training Pipeline Job..."
# Delete existing job if it exists to allow re-run
kubectl delete job training-pipeline -n test-project --ignore-not-found

sed "s|\${REGISTRY_HOST}|${REGISTRY_HOST}|g; s|\${BUCKET_NAME}|${BUCKET_NAME}|g" manifests/gcp/pipeline-job.yaml | kubectl apply -f -

echo "Job deployed. Follow logs with:"
echo "kubectl logs job/training-pipeline -n test-project -f"
