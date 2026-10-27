#!/bin/bash
# Build and Push Script for GDC-ag Pattern
# Purpose: Builds Gateway Proxy and baked Ollama model images, then pushes them to registry.

set -e

# Configuration
REGISTRY_HOST=${REGISTRY_HOST:-"us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"}
TAG=${TAG:-"latest"}

echo "🚀 Starting Build and Push process..."

# 1. Build and Push the Proxy Image
echo "Building Gateway Proxy image..."
cd gateway/proxy
docker build -t "${REGISTRY_HOST}/gemma-proxy:${TAG}" .
echo "Pushing Gateway Proxy image..."
docker push "${REGISTRY_HOST}/gemma-proxy:${TAG}"
cd ../../

# 2. Build and Push the Baked Ollama Images
# We build baked images containing the model weights for both 26B and 31B variants.

MODELS=(
  "26b:gemma4:26b"
  "31b:gemma4:31b"
)

for MODEL_SPEC in "${MODELS[@]}"; do
  VARIANT=$(echo "$MODEL_SPEC" | cut -d':' -f1)
  MODEL_TAG=$(echo "$MODEL_SPEC" | cut -d':' -f2-)

  IMAGE_NAME="ollama-gemma-${VARIANT}"
  DOCKERFILE="gateway/ollama-baked/Dockerfile.${VARIANT}"

  echo "Building Baked Ollama image for variant ${VARIANT} with tag ${MODEL_TAG}..."
  docker build -t "${REGISTRY_HOST}/${IMAGE_NAME}:${TAG}" \
    --build-arg MODEL_TAG="${MODEL_TAG}" \
    -f "${DOCKERFILE}" \
    gateway/ollama-baked

  echo "Pushing Baked Ollama image ${IMAGE_NAME}..."
  docker push "${REGISTRY_HOST}/${IMAGE_NAME}:${TAG}"
done

echo "✅ All images built and pushed to ${REGISTRY_HOST} successfully."
