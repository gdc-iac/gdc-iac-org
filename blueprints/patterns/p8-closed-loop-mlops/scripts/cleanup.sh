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
NAMESPACE="default"
BUCKET_NAME="${PROJECT_ID}-mlops-data"

echo "Cleaning up Pattern 8 resources..."

# 1. Delete Kubernetes Resources
kubectl delete job training-pipeline -n ${NAMESPACE} --ignore-not-found=true
kubectl delete -f p8-closed-loop-mlops/manifests/gcp/ --ignore-not-found=true


# Cleanup Persistent Volumes
kubectl delete pvc -l app=postgres -n ${NAMESPACE} --ignore-not-found=true

# 2. Delete Secrets
kubectl delete secret mlops-secrets -n ${NAMESPACE} --ignore-not-found=true

# 3. Bucket Cleanup (Optional)
echo "----------------------------------------------------------------"
echo "NOTE: GCS Bucket '${BUCKET_NAME}' was NOT deleted."
echo "To delete it, run:"
echo "gcloud storage rm --recursive gs://${BUCKET_NAME}"
echo "----------------------------------------------------------------"

echo "Cleanup complete!"
