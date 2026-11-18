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

# scripts/cleanup.sh
# Cleans up resources created for the P6 Resilient RAG Agent.

PROJECT_ID=$(gcloud config get-value project)
NAMESPACE="test-project"
BUCKET_NAME="raw-docs-${PROJECT_ID}"

echo "Cleaning up P6 Resilient RAG Agent resources..."

# 1. Delete Kubernetes Resources
echo "Deleting Kubernetes resources..."
kubectl delete -f p6-resilient-rag-agent/manifests/apps/ --ignore-not-found=true
kubectl delete -f p6-resilient-rag-agent/manifests/gcp/ --ignore-not-found=true


# Cleanup Persistent Volumes
kubectl delete pvc -l app=postgres -n ${NAMESPACE} --ignore-not-found=true

# 2. Delete Secrets & Identities
echo "Deleting Secrets and Service Accounts..."
kubectl delete secret rag-db-credentials -n ${NAMESPACE} --ignore-not-found=true
kubectl delete secret gemini-secrets -n ${NAMESPACE} --ignore-not-found=true
kubectl delete serviceaccount rag-sa -n ${NAMESPACE} --ignore-not-found=true

# 3. Empty and Delete Bucket
if gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "Emptying and deleting bucket gs://${BUCKET_NAME}..."
    gcloud storage rm --recursive "gs://${BUCKET_NAME}/**" || true
    gcloud storage buckets delete "gs://${BUCKET_NAME}" || true
else
    echo "Bucket gs://${BUCKET_NAME} not found, skipping."
fi

# 4. Clean up Workload Identity (Optional - commented out to avoid breaking other things if shared)
# echo "Cleaning up Workload Identity..."
# ...

echo "Cleanup complete!"
