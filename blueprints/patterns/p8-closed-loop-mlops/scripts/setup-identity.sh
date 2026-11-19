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
BUCKET_NAME="${PROJECT_ID}-mlops-data"
GSA_NAME="p8-mlops-sa"
GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KSA_NAME="default"
NAMESPACE="default"

echo "Setting up Workload Identity for P8..."

# 1. Create GSA if not exists
if ! gcloud iam service-accounts describe "${GSA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating GSA ${GSA_NAME}..."
    gcloud iam service-accounts create "${GSA_NAME}" --project="${PROJECT_ID}" --display-name="P8 MLOps SA"
else
    echo "GSA ${GSA_NAME} already exists."
fi

# 2. Grant Permissions on Bucket
echo "Granting Storage Object Admin to ${GSA_EMAIL} on bucket ${BUCKET_NAME}..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
    --member="serviceAccount:${GSA_EMAIL}" \
    --role="roles/storage.objectAdmin"

# 3. Bind KSA to GSA
echo "Binding KSA ${NAMESPACE}/${KSA_NAME} to GSA ${GSA_EMAIL}..."
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

# 4. Annotate KSA
echo "Annotating KSA..."
kubectl annotate serviceaccount "${KSA_NAME}" \
    --namespace "${NAMESPACE}" \
    iam.gke.io/gcp-service-account="${GSA_EMAIL}" \
    --overwrite

echo "Workload Identity setup complete!"
