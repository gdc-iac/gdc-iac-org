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
PATTERN_DIR="$(dirname "$SCRIPT_DIR")"
BRIDGE_SRC="${PATTERN_DIR}/src/gdc-kms-bridge"

REGISTRY_HOST=${REGISTRY_HOST:-"harbor001-iac-root.org-12345.zone1.google.gdch.test/iac"}
BRIDGE_TAG=${BRIDGE_TAG:-"1.0.0"}
VAULT_TAG=${VAULT_TAG:-"1.15.0"}

echo "Building GDCag KMS Auto-Unseal Bridge (${REGISTRY_HOST}/gdc-kms-bridge:${BRIDGE_TAG})..."
docker build -t "${REGISTRY_HOST}/gdc-kms-bridge:${BRIDGE_TAG}" "${BRIDGE_SRC}"

if [ "${PUSH_IMAGES:-false}" = "true" ]; then
  echo "Pushing ${REGISTRY_HOST}/gdc-kms-bridge:${BRIDGE_TAG}..."
  docker push "${REGISTRY_HOST}/gdc-kms-bridge:${BRIDGE_TAG}"

  echo "Mirroring OSS hashicorp/vault:${VAULT_TAG} -> ${REGISTRY_HOST}/vault:${VAULT_TAG}..."
  docker pull "hashicorp/vault:${VAULT_TAG}"
  docker tag "hashicorp/vault:${VAULT_TAG}" "${REGISTRY_HOST}/vault:${VAULT_TAG}"
  docker push "${REGISTRY_HOST}/vault:${VAULT_TAG}"
fi

echo "Build complete for p11-vault!"
