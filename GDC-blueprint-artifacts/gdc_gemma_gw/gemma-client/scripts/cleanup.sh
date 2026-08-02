#!/bin/bash
# Cleanup Script for Gemma Client testing resources.

set -e

PROJECT_ID=$(gcloud config get-value project)
NAMESPACE=${NAMESPACE:-"gemma-inference"}
BUCKET_NAME="gs://gemma-client-files-${PROJECT_ID}"

echo "🧹 Tearing down Gemma Client resources..."

# 1. Delete Kubernetes Resources
kubectl delete -f gemma-client/manifests/apps/frontend.yaml -n $NAMESPACE --ignore-not-found=true || true
kubectl delete -f gemma-client/manifests/apps/backend.yaml -n $NAMESPACE --ignore-not-found=true || true
kubectl delete -f gemma-client/manifests/gcp/statefulset-postgres.yaml -n $NAMESPACE --ignore-not-found=true || true
kubectl delete -f gemma-client/manifests/gcp/postgres-configmap.yaml -n $NAMESPACE --ignore-not-found=true || true

# 2. Delete GCS Bucket
echo "🧹 Deleting GCS Bucket: $BUCKET_NAME..."
gcloud storage rm -r "$BUCKET_NAME" || true

# 3. Delete GSA/KSA
echo "🧹 Deleting Service Accounts..."
kubectl delete serviceaccount gemma-client-sa -n $NAMESPACE --ignore-not-found=true || true
gcloud iam service-accounts delete gemma-client-sa@$PROJECT_ID.iam.gserviceaccount.com --quiet || true

echo "✅ Cleanup complete!"
