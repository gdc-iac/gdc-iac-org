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

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo "test-project")}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "============================================================"
echo " Rolling back Pattern 13 from Phase 3 to Phase 2 (Passive) "
echo " Project ID: ${PROJECT_ID}"
echo "============================================================"

# 1. Re-apply Phase 2 AI ConfigMap (disabling Agentic mode)
echo "[1/4] Applying Phase 2 AI ConfigMap..."
kubectl apply -f "${PATTERN_DIR}/manifests/gdc/ai-gateway-configmap.yaml"

# 2. Re-apply Phase 2 Deployment Manifest
echo "[2/4] Applying Phase 2 Deployment Manifest..."
kubectl apply -f "${PATTERN_DIR}/manifests/gdc/gdc-dev-phase2-deployment.yaml"

# 3. Ensure images target active registry
REGISTRY_HOST=${REGISTRY_HOST:-"harbor.shared-services.gdc.local/my-org"}
echo "[3/4] Updating image references to registry ${REGISTRY_HOST}..."
kubectl set image deployment/gdc-dev-landing-page landing-page="${REGISTRY_HOST}/gdc-dev-landing-page:latest" -n gdc-dev
kubectl set image deployment/gdc-dev-operator operator="${REGISTRY_HOST}/gdc-dev-operator:latest" -n gdc-dev

# 4. Rollout restart and verify
echo "[4/4] Restarting deployments and verifying rollout status..."
kubectl rollout restart deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
kubectl rollout status deployment/gdc-dev-landing-page -n gdc-dev
kubectl rollout status deployment/gdc-dev-operator -n gdc-dev

echo "============================================================"
echo "✅ Rollback to Phase 2 (Passive Co-Pilot) completed successfully!"
echo "============================================================"
