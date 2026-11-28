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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PATTERN_DIR}/.." && pwd)"
PACKAGE_DIR="${REPO_ROOT}/packages/p15-job-orchestrator"
BOM_FILE="${PACKAGE_DIR}/p15-job-orchestrator-BOM.txt"

echo "================================================================================"
echo " Packaging Pattern 15 (p15-job-orchestrator) for Air-Gapped GDC-ag Transfer"
echo "================================================================================"

# 1. Sync shared `example-app/common` modules into service contexts if present
if [[ -d "${PATTERN_DIR}/example-app/common" ]]; then
  for ctx in "job-manager" "jobs" "mock-notifier"; do
    if [[ -d "${PATTERN_DIR}/example-app/${ctx}" ]]; then
      rm -rf "${PATTERN_DIR}/example-app/${ctx}/common"
      cp -r "${PATTERN_DIR}/example-app/common" "${PATTERN_DIR}/example-app/${ctx}/common"
    fi
  done
  echo "[OK] Synchronized example-app/common into container build contexts."
fi

# 2. Fail closed if GCP Artifact Registry (`pkg.dev`) or simulated OIDC leaked into production manifests
if grep -rn "pkg\.dev" "${PATTERN_DIR}/manifests/gdc/" "${PATTERN_DIR}/manifests/apps/" >/dev/null 2>&1; then
  echo "[ERROR] Found GCP Artifact Registry (pkg.dev) reference in manifests/gdc/ or manifests/apps/." >&2
  echo "        Restore harbor.gdc.local production defaults before packaging for GDC-ag." >&2
  exit 1
fi

if grep -rn 'ALLOW_SIMULATED_OIDC: *"true"' "${PATTERN_DIR}/manifests/gdc/" "${PATTERN_DIR}/manifests/apps/" >/dev/null 2>&1; then
  echo "[ERROR] ALLOW_SIMULATED_OIDC=\"true\" detected in production manifests/gdc/ or manifests/apps/." >&2
  exit 1
fi
echo "[OK] Verified zero pkg.dev and zero ALLOW_SIMULATED_OIDC=\"true\" in manifests/gdc/ & manifests/apps/."

# 3. Delegate bundle creation to root `scripts/package-for-gdc.sh`
cd "${REPO_ROOT}"
mkdir -p "${PACKAGE_DIR}"
"${REPO_ROOT}/scripts/package-for-gdc.sh" "p15-job-orchestrator"

# 4. Generate SHA-256 Bill of Materials (`packages/p15-job-orchestrator/p15-job-orchestrator-BOM.txt`)
#    explicitly excluding `manifests/gcp/` (which is strictly for GKE Stepping-Stone emulation).
{
  echo "# Pattern 15 (p15-job-orchestrator) Air-Gap Bill of Materials (SHA-256)"
  echo "# Generated UTC: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "# Production Scope: manifests/gdc/, manifests/apps/, chart/, external_images.txt"
  echo "# Note: manifests/gcp/ is strictly for GCP/GKE Stepping-Stone emulation and MUST NOT be applied on GDC-ag."
  echo ""
  echo "## Packaged Transfer Archives"
  find "packages/p15-job-orchestrator" -maxdepth 1 -type f \( -name "*.tar" -o -name "*.tar.gz" \) | sort | xargs -r sha256sum
  echo ""
  echo "## Production Manifests, Helm Chart & 3P Image Pin List"
  find "p15-job-orchestrator/manifests/gdc" "p15-job-orchestrator/manifests/apps" \
       "p15-job-orchestrator/external_images.txt" \
       $( [[ -d "p15-job-orchestrator/chart" ]] && echo "p15-job-orchestrator/chart" ) \
       -type f 2>/dev/null | sort | xargs -r sha256sum
} > "${BOM_FILE}"

echo "================================================================================"
echo "[OK] Generated SHA-256 Bill of Materials: ${BOM_FILE}"
echo "[NOTE] On the air-gapped GDC-ag enclave, deploy ONLY manifests/gdc/, manifests/apps/,"
echo "       or chart/ (NEVER apply manifests/gcp/, which is GKE Stepping-Stone only)."
echo "================================================================================"
