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
NAMESPACE="test-project"

echo "Cleaning up Pattern 10 resources..."

# 1. Delete Kubernetes Resources
kubectl delete -f p10-gemini-gui/manifests/apps/ --ignore-not-found=true
kubectl delete -f p10-gemini-gui/manifests/gcp/ --ignore-not-found=true


# Cleanup Persistent Volumes
kubectl delete pvc -l app=postgres -n ${NAMESPACE} --ignore-not-found=true

# 2. Delete ConfigMaps
kubectl delete configmap postgres-init -n ${NAMESPACE} --ignore-not-found=true

# 3. Delete GSA if standard name used (optional but recommended to document here)
echo "Manual step: Remember to delete your service account and bucket if completely tearing down."
echo "gcloud storage rm -r gs://\$BUCKET_NAME"
echo "gcloud iam service-accounts delete gemini-gui-sa@\$PROJECT_ID.iam.gserviceaccount.com"

echo "Cleanup complete!"
