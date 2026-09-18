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

PROJECT_ID=${PROJECT_ID:-"my-gdc-project"}
REGISTRY_HOST=${REGISTRY_HOST:-"harbor.shared-services.gdc.local/my-org"}
TAG=${TAG:-"latest"}
SAVE_TAR=false
NO_PUSH=false
BUILD_WORKSPACE=false
TAR_OUTPUT_DIR="."

# Parse CLI arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --save-tar)
            SAVE_TAR=true
            if [[ -n "$2" && "$2" != --* ]]; then
                TAR_OUTPUT_DIR="$2"
                shift
            fi
            ;;
        --no-push)
            NO_PUSH=true
            ;;
        --with-workspace)
            BUILD_WORKSPACE=true
            ;;
        --registry)
            REGISTRY_HOST="$2"
            shift
            ;;
        --tag)
            TAG="$2"
            shift
            ;;
        -h|--help)
            echo "Usage: ./build.sh [OPTIONS]"
            echo ""
            echo "Build and package Pattern 13 (GDC Dev - gdc-dev) container images."
            echo "Compatible with both GCP Emulation (Artifact Registry) and GDC Air-Gapped (Harbor / Tarball)."
            echo ""
            echo "Options:"
            echo "  --registry <host>     Target Docker registry (default: \${REGISTRY_HOST:-harbor.shared-services.gdc.local/my-org})"
            echo "  --tag <tag>           Image tag (default: latest)"
            echo "  --with-workspace      Also build and package the custom developer workspace session image"
            echo "  --save-tar [dir]      Export images to a .tar.gz archive for offline sneakernet transfer"
            echo "  --no-push             Build images without pushing to remote registry"
            echo "  -h, --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1 (use --help for options)"
            exit 1
            ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LANDING_IMAGE="${REGISTRY_HOST}/gdc-dev-landing-page:${TAG}"
OPERATOR_IMAGE="${REGISTRY_HOST}/gdc-dev-operator:${TAG}"
WORKSPACE_IMAGE="${REGISTRY_HOST}/gdc-dev-workspace:${TAG}"

echo "============================================================"
echo " Building images for Pattern 13 (GDC Dev - gdc-dev) "
echo " Target Registry: ${REGISTRY_HOST}"
echo " Image Tag:       ${TAG}"
echo " With Workspace:  $([ "$BUILD_WORKSPACE" = true ] && echo "Yes" || echo "No")"
echo " Push to Remote:  $([ "$NO_PUSH" = true ] && echo "No" || echo "Yes")"
echo " Export Tarball:  $([ "$SAVE_TAR" = true ] && echo "Yes (${TAR_OUTPUT_DIR})" || echo "No")"
echo "============================================================"

# 1. Build Landing Page (pre-baked with git, kubectl, helm, gdcloud, docker-cli)
echo "[1/2] Building gdc-dev-landing-page..."
docker build -t "${LANDING_IMAGE}" "${PATTERN_DIR}/example-app/landing-page"

# 2. Build Operator (pre-baked with management & runtime tooling)
echo "[2/2] Building gdc-dev-operator..."
docker build -t "${OPERATOR_IMAGE}" "${PATTERN_DIR}/example-app/operator"

# Optional: Build Custom Developer Workspace Session Image
ALL_IMAGES="${LANDING_IMAGE} ${OPERATOR_IMAGE}"
if [ "$BUILD_WORKSPACE" = true ]; then
    echo "[3/3] Building gdc-dev-workspace..."
    docker build -t "${WORKSPACE_IMAGE}" "${PATTERN_DIR}/example-app/workspace"
    ALL_IMAGES="${ALL_IMAGES} ${WORKSPACE_IMAGE}"
fi

# Push to Remote Registry (if not disabled)
if [ "$NO_PUSH" = false ]; then
    echo "Pushing images to ${REGISTRY_HOST}..."
    docker push "${LANDING_IMAGE}"
    docker push "${OPERATOR_IMAGE}"
    if [ "$BUILD_WORKSPACE" = true ]; then
        docker push "${WORKSPACE_IMAGE}"
    fi
    echo "✅ Remote push complete."
fi

# Export Tarball for Air-Gapped Sneakernet Transfer (if requested)
if [ "$SAVE_TAR" = true ]; then
    mkdir -p "${TAR_OUTPUT_DIR}"
    TAR_FILE="${TAR_OUTPUT_DIR}/gdc-dev-images.tar.gz"
    echo "Exporting container images to ${TAR_FILE} for air-gapped transfer..."
    docker save ${ALL_IMAGES} | gzip > "${TAR_FILE}"
    echo "✅ Offline image archive created: ${TAR_FILE} ($(du -h "${TAR_FILE}" | awk '{print $1}'))"
fi

echo "============================================================"
echo "✅ Pattern 13 images built successfully!"
echo "============================================================"
