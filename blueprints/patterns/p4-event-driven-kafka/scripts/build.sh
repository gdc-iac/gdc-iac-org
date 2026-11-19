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

PROJECT_ID=${PROJECT_ID:-"test-project"}
REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/iac"}
TAG="v1"

echo "Building and pushing images for Pattern 4 (Event Driven Kafka)..."

# 1. Build Producer
echo "Building Producer..."
docker build -t "${REGISTRY_HOST}/p4-producer:${TAG}" p4-event-driven-kafka/example-app/producer
docker push "${REGISTRY_HOST}/p4-producer:${TAG}"

# 2. Build Consumer
echo "Building Consumer..."
docker build -t "${REGISTRY_HOST}/p4-consumer:${TAG}" p4-event-driven-kafka/example-app/consumer
docker push "${REGISTRY_HOST}/p4-consumer:${TAG}"

# 3. Mirror Native StatefulSet OSS Dependencies into Project Managed Harbor / Artifact Registry
# (Avoid pushing unsigned images to System Harbor `library/`, which enforces Cosign verification)
echo "Mirroring external OSS dependencies (apache/kafka:3.9.0, busybox:1.36)..."
docker pull docker.io/apache/kafka:3.9.0
docker tag docker.io/apache/kafka:3.9.0 "${REGISTRY_HOST}/kafka:3.9.0"
docker push "${REGISTRY_HOST}/kafka:3.9.0"

docker pull busybox:1.36
docker tag busybox:1.36 "${REGISTRY_HOST}/busybox:1.36"
docker push "${REGISTRY_HOST}/busybox:1.36"

echo "Build complete!"
