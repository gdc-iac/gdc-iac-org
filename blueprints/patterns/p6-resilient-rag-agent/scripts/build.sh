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

# scripts/build.sh
# Builds and pushes the Docker images for the P6 Resilient RAG Agent.

PROJECT_ID=${PROJECT_ID:-"test-project"}
REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/iac"}
TAG="v7"

echo "Building and Pushing images to ${REGISTRY_HOST}..."

# 1. Ingestion Service
echo "Building rag-ingest:${TAG}..."
docker build -t "${REGISTRY_HOST}/rag-ingest:${TAG}" p6-resilient-rag-agent/example-app/ingestion
docker push "${REGISTRY_HOST}/rag-ingest:${TAG}"

# 2. Query Service
echo "Building rag-query:${TAG}..."
docker build -t "${REGISTRY_HOST}/rag-query:${TAG}" p6-resilient-rag-agent/example-app/query-service
docker push "${REGISTRY_HOST}/rag-query:${TAG}"

# 3. Frontend Service
echo "Building rag-frontend:${TAG}..."
docker build -t "${REGISTRY_HOST}/rag-frontend:${TAG}" p6-resilient-rag-agent/example-app/frontend
docker push "${REGISTRY_HOST}/rag-frontend:${TAG}"

echo "Build complete!"
