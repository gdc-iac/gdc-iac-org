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

PROJECT_ID=$(gcloud config get-value project)
GSA_NAME="p8-mlops-sa"
GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KSA_NAME="default"
NAMESPACE="default"

echo "=== Debugging Workload Identity ==="
echo "Project: ${PROJECT_ID}"
echo "GSA: ${GSA_EMAIL}"
echo "KSA: ${NAMESPACE}/${KSA_NAME}"

echo -e "\n1. Checking KSA Annotation..."
kubectl get serviceaccount ${KSA_NAME} -n ${NAMESPACE} -o jsonpath='{.metadata.annotations}'

echo -e "\n\n2. Checking GSA IAM Policy (looking for workloadIdentityUser)..."
gcloud iam service-accounts get-iam-policy ${GSA_EMAIL} \
    --flatten="bindings[].members" \
    --format="table(bindings.role, bindings.members)" \
    --filter="bindings.role:roles/iam.workloadIdentityUser"

echo -e "\n\n3. Checking GSA Storage Permissions..."
gcloud storage buckets get-iam-policy gs://${PROJECT_ID}-mlops-data \
    --flatten="bindings[].members" \
    --format="table(bindings.role, bindings.members)" \
    --filter="bindings.members:${GSA_EMAIL}"

echo -e "\n=== End Debug ==="
