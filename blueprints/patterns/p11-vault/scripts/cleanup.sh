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

set -euo pipefail

NAMESPACE=${NAMESPACE:-"vault"}
PROJECT_ID=${PROJECT_ID:-"my-gdc-project"}
RELEASE_NAME=${RELEASE_NAME:-"vault"}

echo "Cleaning up Pattern 11 (p11-vault) resources in namespace '${NAMESPACE}'..."

# 1. Remove User Cluster Helm release & PVCs
GODEBUG=tlsmlkem=0 helm uninstall "${RELEASE_NAME}" -n "${NAMESPACE}" || true
kubectl delete networkpolicy vault-internal-policy -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete pvc -l app.kubernetes.io/name=vault -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete secret gdc-kms-sa -n "${NAMESPACE}" --ignore-not-found=true

# 2. Optional GDCag Zonal & Global KMS/IAM cleanup (only when explicitly requested via DELETE_KMS=true)
if [ "${DELETE_KMS:-false}" = "true" ]; then
  if [ -n "${ZONE_KUBECONFIG:-}" ]; then
    echo "Deleting Zonal AEADKey in namespace '${PROJECT_ID}'..."
    kubectl --kubeconfig="${ZONE_KUBECONFIG}" delete aeadkey vault-unseal-key -n "${PROJECT_ID}" --ignore-not-found=true
  fi
  if [ -n "${GLOBAL_API_KUBECONFIG:-}" ]; then
    echo "Deleting Global ProjectServiceAccount & IAMRoleBindings in namespace '${PROJECT_ID}'..."
    kubectl --kubeconfig="${GLOBAL_API_KUBECONFIG}" delete iamrolebinding \
      vault-kms-sa--kms-developer vault-kms-sa--kms-viewer -n "${PROJECT_ID}" --ignore-not-found=true
    kubectl --kubeconfig="${GLOBAL_API_KUBECONFIG}" delete projectserviceaccount \
      vault-kms-sa -n "${PROJECT_ID}" --ignore-not-found=true
  fi
fi

# 3. Optional GCP Stepping-Stone identity cleanup
if command -v gcloud >/dev/null 2>&1 && [ "${CLEANUP_GCP_GSA:-false}" = "true" ]; then
  GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
  if [ -n "${GCP_PROJECT}" ]; then
    GSA_EMAIL="vault-kms-sa@${GCP_PROJECT}.iam.gserviceaccount.com"
    gcloud iam service-accounts delete "${GSA_EMAIL}" --quiet >/dev/null 2>&1 || true
  fi
fi

echo "Cleanup complete!"
