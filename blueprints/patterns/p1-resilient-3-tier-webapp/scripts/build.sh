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

PROJECT_ID=${PROJECT_ID:-"test-project"}
REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/iac"}
TAG="v1"

echo "Building and Pushing images for Pattern 1 (Resilient 3-Tier Webapp)..."

# 1. Build Backend (API Server)
echo "Building Backend..."
docker build -t "${REGISTRY_HOST}/my-org/api-server:${TAG}" p1-resilient-3-tier-webapp/example-app/src/backend
docker push "${REGISTRY_HOST}/my-org/api-server:${TAG}"

# 2. Build Frontend (Web Tier)
echo "Building Frontend..."
docker build -t "${REGISTRY_HOST}/p1-frontend:latest" p1-resilient-3-tier-webapp/example-app/src/frontend
docker push "${REGISTRY_HOST}/p1-frontend:latest"

echo "Build complete!"
