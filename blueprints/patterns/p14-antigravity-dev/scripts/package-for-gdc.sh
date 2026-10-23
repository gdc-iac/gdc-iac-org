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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "================================================================================"
echo " Pre-Packaging Sync: Ensuring Latest Antigravity SDK & GDC Skills Are Staged"
echo "================================================================================"

# 1. Sync canonical Antigravity SDK orchestrator, Jupyter magic, and SKILL.md bundles into build contexts
for target_dir in "${PATTERN_DIR}/example-app/landing-page" "${PATTERN_DIR}/example-app/operator"; do
  cp -f "${PATTERN_DIR}/example-app/orchestrator/gdc_agy_orchestrator.py" "${target_dir}/gdc_agy_orchestrator.py"
  cp -f "${PATTERN_DIR}/example-app/orchestrator/gdc_antigravity_magic.py" "${target_dir}/gdc_antigravity_magic.py"
  rm -rf "${target_dir}/skills"
  cp -r "${PATTERN_DIR}/example-app/skills" "${target_dir}/skills"
done
echo "✅ Synchronized latest gdc_agy_orchestrator.py, gdc_antigravity_magic.py, and skills/ into container contexts."

# 2. Optionally fetch latest google-antigravity wheel into binaries/ if FETCH_LATEST_AGY_WHEEL=true
if [ "${FETCH_LATEST_AGY_WHEEL:-false}" = "true" ]; then
  echo "⬇️  Downloading latest google-antigravity wheel into binaries/..."
  pip download --no-deps ${AGY_WHEEL_INDEX_ARGS:-} -d "${PATTERN_DIR}/example-app/landing-page/binaries" google-antigravity
  cp -f "${PATTERN_DIR}/example-app/landing-page/binaries/"google_antigravity-*.whl "${PATTERN_DIR}/example-app/operator/binaries/" 2>/dev/null || true
fi

if ls "${PATTERN_DIR}/example-app/landing-page/binaries/"*.whl 1>/dev/null 2>&1; then
  echo "✅ Staged offline Python wheels in binaries/ (will be installed into /opt/wheelhouse during docker build):"
  ls -1 "${PATTERN_DIR}/example-app/landing-page/binaries/"*.whl
else
  echo "ℹ️  No external .whl files found in binaries/; using built-in Antigravity SDK adapter (gdc_agy_orchestrator.py)."
fi

# 3. Verify manifests/gdc/ have clean GDC-ag production defaults (no GCP emulation residue)
if grep -rn "pkg\.dev" "${PATTERN_DIR}/manifests/gdc/" >/dev/null 2>&1; then
  echo "❌ ERROR: Found GCP Artifact Registry (pkg.dev) reference in manifests/gdc/. Restore harbor.gdc.local defaults before packaging."
  exit 1
fi

echo "Delegating to root package-for-gdc.sh script..."
"${PATTERN_DIR}/../scripts/package-for-gdc.sh" "p14-antigravity-dev"
