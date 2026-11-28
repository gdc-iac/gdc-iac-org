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

PROJECT_ID="${PROJECT_ID:-my-gdc-project}"
REGISTRY_HOST="${REGISTRY_HOST:-${REGISTRY:-harbor.gdc.local/blueprint-images}}"
TAG="${TAG:-${IMAGE_TAG:-v1.0.0}}"
PLATFORM="${PLATFORM:-linux/amd64}"
NO_PUSH=false
SAVE_TAR=false
TAR_OUTPUT_DIR="."

usage() {
  cat <<EOF
Usage: ./scripts/build.sh [OPTIONS]

Build and optionally push Pattern 15 (p15-job-orchestrator) container images:
  - p15-job-manager:${TAG}
  - p15-reference-worker:${TAG}
  - p15-mock-notifier:${TAG}  (GKE Stepping-Stone notification verification sink)

Note: Stages shared modules from example-app/common/ into each service build
context prior to invoking 'docker build --platform ${PLATFORM}'.

Options:
  --registry <url>      Target OCI registry prefix (default: \${REGISTRY_HOST})
  --tag <tag>           Immutable non-latest image tag (default: v1.0.0)
  --platform <arch>     Target build platform (default: linux/amd64)
  --push                Push built images to remote registry (default behavior)
  --no-push             Build images locally without pushing to remote registry
  --save-tar [dir]      Save built images to an offline .tar.gz archive
  -h, --help            Show this help message
EOF
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --registry)
      REGISTRY_HOST="${2%/}"
      shift
      ;;
    --tag)
      TAG="$2"
      shift
      ;;
    --platform)
      PLATFORM="$2"
      shift
      ;;
    --push)
      NO_PUSH=false
      ;;
    --no-push)
      NO_PUSH=true
      ;;
    --save-tar)
      SAVE_TAR=true
      if [[ -n "${2:-}" && "${2:-}" != --* ]]; then
        TAR_OUTPUT_DIR="$2"
        shift
      fi
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

if [[ "${TAG}" == "latest" ]]; then
  echo "ERROR: Mutable ':latest' image tags are prohibited by REQ-SEC-005. Specify a pinned tag (e.g., --tag v1.0.0)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

JOB_MANAGER_IMAGE="${REGISTRY_HOST}/p15-job-manager:${TAG}"
WORKER_IMAGE="${REGISTRY_HOST}/p15-reference-worker:${TAG}"
MOCK_NOTIFIER_IMAGE="${REGISTRY_HOST}/p15-mock-notifier:${TAG}"

echo "=================================================================="
echo " Building Pattern 15 (p15-job-orchestrator) Container Images"
echo " Target Registry : ${REGISTRY_HOST}"
echo " Image Tag       : ${TAG}"
echo " Platform        : ${PLATFORM}"
echo " Push to Remote  : $([[ "${NO_PUSH}" == "true" ]] && echo "No" || echo "Yes")"
echo "=================================================================="

# Stage shared `example-app/common` package into each service build context before `docker build`
for ctx in "job-manager" "jobs" "mock-notifier"; do
  target_ctx="${PATTERN_DIR}/example-app/${ctx}"
  if [[ -d "${target_ctx}" ]]; then
    rm -rf "${target_ctx}/common"
    cp -r "${PATTERN_DIR}/example-app/common" "${target_ctx}/common"
    echo "Staged example-app/common -> example-app/${ctx}/common"
  fi
done

echo "[1/3] Building ${JOB_MANAGER_IMAGE}..."
docker build --platform "${PLATFORM}" -t "${JOB_MANAGER_IMAGE}" "${PATTERN_DIR}/example-app/job-manager"

echo "[2/3] Building ${WORKER_IMAGE}..."
docker build --platform "${PLATFORM}" -t "${WORKER_IMAGE}" "${PATTERN_DIR}/example-app/jobs"

IMAGES_TO_SAVE=("${JOB_MANAGER_IMAGE}" "${WORKER_IMAGE}")
if [[ -d "${PATTERN_DIR}/example-app/mock-notifier" ]]; then
  echo "[3/3] Building ${MOCK_NOTIFIER_IMAGE}..."
  docker build --platform "${PLATFORM}" -t "${MOCK_NOTIFIER_IMAGE}" "${PATTERN_DIR}/example-app/mock-notifier"
  IMAGES_TO_SAVE+=("${MOCK_NOTIFIER_IMAGE}")
else
  echo "[3/3] Skipping p15-mock-notifier (excluded from GDC-ag production staging)."
fi

if [[ "${NO_PUSH}" == "false" ]]; then
  echo "Pushing images to ${REGISTRY_HOST}..."
  for img in "${IMAGES_TO_SAVE[@]}"; do
    docker push "${img}"
  done
  echo "Remote push complete."
fi

if [[ "${SAVE_TAR}" == "true" ]]; then
  mkdir -p "${TAR_OUTPUT_DIR}"
  ARCHIVE_PATH="${TAR_OUTPUT_DIR}/p15-job-orchestrator-images-${TAG}.tar.gz"
  echo "Saving offline image archive to ${ARCHIVE_PATH}..."
  docker save "${IMAGES_TO_SAVE[@]}" | gzip > "${ARCHIVE_PATH}"
  echo "Saved archive: ${ARCHIVE_PATH}"
fi

echo "=================================================================="
echo " Pattern 15 images built successfully!"
echo "=================================================================="
