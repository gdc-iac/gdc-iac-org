#!/bin/bash
# Sideloading Export Script for GDC-ag
# Purpose: Creates a complete self-contained transfer bundle mirroring the GDC blueprints structure with distinct gateway and client paths.

set -e

REGISTRY_HOST=${REGISTRY_HOST:-"us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"}
TAG=${TAG:-"latest"}
INFERENCE_ENGINE=${INFERENCE_ENGINE:-"ollama"}

STAGING_DIR="./packages/gemma-gateway-gdc"
OUTPUT_DIR="./packages"

echo "🧹 Cleaning up and creating staging directories..."
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/gateway/ollama"
mkdir -p "$STAGING_DIR/gateway/vllm"
mkdir -p "$STAGING_DIR/client"
mkdir -p "$STAGING_DIR/helper-scripts"

if [ "$INFERENCE_ENGINE" = "ollama" ]; then
    echo "📦 1. Bundling and Exporting Ollama container images..."
    docker save \
      "${REGISTRY_HOST}/gemma-proxy:${TAG}" \
      "${REGISTRY_HOST}/ollama-gemma-26b:${TAG}" \
      "${REGISTRY_HOST}/ollama-gemma-31b:${TAG}" \
      -o "${STAGING_DIR}/gateway/ollama/gemma-gateway-gdc-images.tar"

    cat <<EOF > "$STAGING_DIR/gateway/ollama/images_list.txt"
${REGISTRY_HOST}/gemma-proxy:${TAG}
${REGISTRY_HOST}/ollama-gemma-26b:${TAG}
${REGISTRY_HOST}/ollama-gemma-31b:${TAG}
EOF

    echo "📦 2. Archiving Ollama Helm charts and manifests..."
    tar -czf "$STAGING_DIR/gateway/ollama/gemma-gateway-gdc-manifests.tar.gz" blueprints/ollama-gke/ standalone/

elif [ "$INFERENCE_ENGINE" = "vllm" ]; then
    echo "📦 1. Bundling and Exporting vLLM container images..."
    docker save \
      "${REGISTRY_HOST}/gemma-proxy:${TAG}" \
      "${REGISTRY_HOST}/vllm-gemma-26b:${TAG}" \
      "${REGISTRY_HOST}/vllm-gemma-31b:${TAG}" \
      -o "${STAGING_DIR}/gateway/vllm/gemma-gateway-gdc-images.tar"

    cat <<EOF > "$STAGING_DIR/gateway/vllm/images_list.txt"
${REGISTRY_HOST}/gemma-proxy:${TAG}
${REGISTRY_HOST}/vllm-gemma-26b:${TAG}
${REGISTRY_HOST}/vllm-gemma-31b:${TAG}
EOF

    echo "📦 2. Archiving vLLM Helm charts and manifests..."
    tar -czf "$STAGING_DIR/gateway/vllm/gemma-gateway-gdc-manifests.tar.gz" blueprints/vllm-gke/ standalone/

elif [ "$INFERENCE_ENGINE" = "client" ]; then
    echo "📦 1. Bundling and Exporting Client container images only..."
    docker save \
      "${REGISTRY_HOST}/gemma-client-backend:${TAG}" \
      "${REGISTRY_HOST}/gemma-client-frontend:${TAG}" \
      -o "${STAGING_DIR}/client/gemma-gateway-gdc-images.tar"

    cat <<EOF > "$STAGING_DIR/client/images_list.txt"
${REGISTRY_HOST}/gemma-client-backend:${TAG}
${REGISTRY_HOST}/gemma-client-frontend:${TAG}
EOF

    echo "📦 2. Archiving Client manifests..."
    tar -czf "$STAGING_DIR/client/gemma-client-manifests.tar.gz" gemma-client/

else
    echo "📦 1. Bundling and Exporting all container images (Dual Backend mode)..."
    docker save \
      "${REGISTRY_HOST}/gemma-proxy:${TAG}" \
      "${REGISTRY_HOST}/ollama-gemma-26b:${TAG}" \
      "${REGISTRY_HOST}/ollama-gemma-31b:${TAG}" \
      "${REGISTRY_HOST}/vllm-gemma-26b:${TAG}" \
      "${REGISTRY_HOST}/vllm-gemma-31b:${TAG}" \
      "${REGISTRY_HOST}/gemma-client-backend:${TAG}" \
      "${REGISTRY_HOST}/gemma-client-frontend:${TAG}" \
      -o "${STAGING_DIR}/gemma-gateway-gdc-images.tar"

    cat <<EOF > "$STAGING_DIR/images_list.txt"
${REGISTRY_HOST}/gemma-proxy:${TAG}
${REGISTRY_HOST}/ollama-gemma-26b:${TAG}
${REGISTRY_HOST}/ollama-gemma-31b:${TAG}
${REGISTRY_HOST}/vllm-gemma-26b:${TAG}
${REGISTRY_HOST}/vllm-gemma-31b:${TAG}
${REGISTRY_HOST}/gemma-client-backend:${TAG}
${REGISTRY_HOST}/gemma-client-frontend:${TAG}
EOF

    echo "📦 2. Archiving all Helm charts, manifests, and client..."
    tar -czf "$STAGING_DIR/gemma-gateway-gdc-manifests.tar.gz" blueprints/ standalone/ gemma-client/
fi

echo "📦 3. Copying documentation and helper scripts..."
cp README.md "$STAGING_DIR/gemma-gateway-README.md"
cp scripts/*.sh "$STAGING_DIR/helper-scripts/"

echo "📦 4. Creating configuration parameters manifest..."
cat <<EOF > "$STAGING_DIR/configuration_parameters.txt"
# Destination Variables for Disconnected GDC Ingestion
PROJECT_ID=""
NAMESPACE="gemma-inference"
REGISTRY_HOST="${REGISTRY_HOST}"
OLLAMA_MODEL_VARIANT="26b"
EOF

echo "📦 5. Generating Checksum BOM (Bill of Materials)..."
cd "$STAGING_DIR"
find . -type f -not -name "gemma-gateway-BOM.txt" -not -name "gemma-gateway-manifest.txt" -exec shasum -a 256 {} \; > "gemma-gateway-BOM.txt"
cp "gemma-gateway-BOM.txt" "gemma-gateway-manifest.txt"
cd ../../

echo "✅ All assets packaged into $STAGING_DIR successfully."
ls -la "$STAGING_DIR/"
