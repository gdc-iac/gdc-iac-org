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

BUNDLE_DIR="."
TARGET_REGISTRY="${REGISTRY_HOST:-}"
OUTPUT_DIR="./p15-job-orchestrator"
NO_PUSH=false

usage() {
  cat <<EOF
Usage: ./unpack-for-gdc.sh [OPTIONS]

Extract Pattern 15 (p15-job-orchestrator) manifests/Helm chart and load/push
air-gapped container image archives into GDC Managed Harbor.

Options:
  --bundle-dir <dir>    Directory containing p15-job-orchestrator-gdc-*.tar* (default: .)
  --output-dir <dir>    Target directory to extract manifests and Helm chart (default: ./p15-job-orchestrator)
  --registry <url>      Target GDC Harbor registry prefix (e.g. harbor.gdc.local/blueprint-images)
  --no-push             Load images into local Docker daemon without pushing to Harbor
  -h, --help            Show this help message
EOF
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --bundle-dir)
      BUNDLE_DIR="$2"
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift
      ;;
    --registry)
      TARGET_REGISTRY="${2%/}"
      shift
      ;;
    --no-push)
      NO_PUSH=true
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1 (run with --help for usage)" >&2
      exit 1
      ;;
  esac
  shift
done

MANIFESTS_TAR="${BUNDLE_DIR}/p15-job-orchestrator-gdc-manifests.tar.gz"
IMAGES_TAR="${BUNDLE_DIR}/p15-job-orchestrator-gdc-images.tar"
BOM_FILE="${BUNDLE_DIR}/p15-job-orchestrator-BOM.txt"

if [[ ! -f "${MANIFESTS_TAR}" ]]; then
  echo "ERROR: Manifests archive not found at ${MANIFESTS_TAR}" >&2
  exit 1
fi

echo "=================================================================="
echo " Unpacking Pattern 15 (p15-job-orchestrator) Air-Gap Bundle"
echo " Bundle Dir : ${BUNDLE_DIR}"
echo " Output Dir : ${OUTPUT_DIR}"
echo " Registry   : ${TARGET_REGISTRY:-<not set - local docker load only>}"
echo "=================================================================="

if [[ -f "${BOM_FILE}" ]]; then
  echo "Found SHA-256 Bill of Materials (${BOM_FILE})."
fi

mkdir -p "${OUTPUT_DIR}"
tar -xzf "${MANIFESTS_TAR}" -C "${OUTPUT_DIR}"
# Remove GKE Stepping-Stone emulation manifests on high-side unpack so operators apply only GDC-ag assets
rm -rf "${OUTPUT_DIR}/manifests/gcp"
echo "[OK] Extracted production manifests/gdc/, manifests/apps/, and chart/ to ${OUTPUT_DIR}/ (excluded manifests/gcp/)."

push_loaded_output() {
  local load_out="$1"
  if [[ -z "${TARGET_REGISTRY}" || "${NO_PUSH}" == "true" ]]; then
    return 0
  fi
  while IFS= read -r line; do
    if [[ "${line}" =~ Loaded\ image:\ ([^[:space:]]+) ]]; then
      src_img="${BASH_REMATCH[1]}"
      base_tag="${src_img##*/}"
      dst_img="${TARGET_REGISTRY}/${base_tag}"
      echo " -> Tagging ${src_img} -> ${dst_img}"
      docker tag "${src_img}" "${dst_img}"
      echo " -> Pushing ${dst_img}..."
      docker push "${dst_img}"
    fi
  done <<< "${load_out}"
}

if [[ -f "${IMAGES_TAR}" ]]; then
  echo "Loading bundled image archive ${IMAGES_TAR}..."
  LOAD_OUT="$(docker load -i "${IMAGES_TAR}")"
  echo "${LOAD_OUT}"
  push_loaded_output "${LOAD_OUT}"
fi

# Also load any standalone 3P archives mirrored from external_images.txt (`offline-images/*.tar*`)
if [[ -d "${BUNDLE_DIR}/offline-images" ]]; then
  for archive in "${BUNDLE_DIR}/offline-images/"*.tar "${BUNDLE_DIR}/offline-images/"*.tar.gz; do
    [[ -e "${archive}" ]] || continue
    echo "Loading 3P image archive ${archive}..."
    LOAD_OUT="$(docker load -i "${archive}")"
    echo "${LOAD_OUT}"
    push_loaded_output "${LOAD_OUT}"
  done
fi

echo "=================================================================="
echo " Unpack complete! Next steps on GDC-ag:"
echo "   1. Stage 1 Global PNP (apply pnp-intra-project-egress.yaml BEFORE disabling DEP)"
echo "   2. Stage 2 Zonal CRDs (manifests/gdc/db, storage, iam, monitoring)"
echo "   3. Stage 5 Workload Cluster (helm upgrade --install p15-jobs ${OUTPUT_DIR}/chart ...)"
echo "=================================================================="
