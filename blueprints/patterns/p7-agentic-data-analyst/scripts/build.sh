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

echo "Building and Pushing images for Pattern 7 (Agentic Data Analyst)..."

# 1. Build Agent
echo "Building Agent..."
docker build -t "${REGISTRY_HOST}/p7-agent:${TAG}" p7-agentic-data-analyst/example-app/agent
docker push "${REGISTRY_HOST}/p7-agent:${TAG}"


echo "Build complete!"
