#!/bin/bash
set -e
# Self-contained GDC packaging script for Gemma Gateway

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ROOT="$(dirname "$SCRIPT_DIR")"

REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/gemma-repo"}
TAG=${TAG:-"latest"}
SKIP_IMAGES=false
INFERENCE_ENGINE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-images|-s)
      SKIP_IMAGES=true
      shift
      ;;
    *)
      INFERENCE_ENGINE="$1"
      shift
      ;;
  esac
done

INFERENCE_ENGINE=${INFERENCE_ENGINE:-"all"}

if [ "$INFERENCE_ENGINE" = "huggingface" ]; then INFERENCE_ENGINE="vllm"; fi
if [ "$INFERENCE_ENGINE" = "both" ]; then INFERENCE_ENGINE="all"; fi

if [ "$SKIP_IMAGES" = true ]; then
  echo "⏭️  Bypassing local image build and container export (--skip-images enabled)."
else
  echo "📦 0. Checking and building required Gemma Gateway container images locally..."
  "$SCRIPT_DIR/build-images.sh" "$INFERENCE_ENGINE"
fi


STAGING_DIR="${PROD_ROOT}/packages/gemma-gateway-gdc"
OUTPUT_DIR="${PROD_ROOT}/packages"

echo "🧹 Cleaning up and creating staging directories..."
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/gateway/ollama"
mkdir -p "$STAGING_DIR/gateway/vllm"
mkdir -p "$STAGING_DIR/client"
mkdir -p "$STAGING_DIR/common-scripts"

if [ "$INFERENCE_ENGINE" = "ollama" ]; then
    echo "📦 1. Exporting Ollama manifest payload..."
    tar -czf "$STAGING_DIR/gateway/ollama/gemma-gateway-ollama-manifests.tar.gz" -C "$PROD_ROOT" blueprints/ollama-gke/ standalone/ gateway/

elif [ "$INFERENCE_ENGINE" = "vllm" ]; then
    echo "📦 1. Exporting vLLM/HuggingFace manifest payload..."
    tar -czf "$STAGING_DIR/gateway/vllm/gemma-gateway-vllm-manifests.tar.gz" -C "$PROD_ROOT" blueprints/vllm-gke/ standalone/ gateway/

elif [ "$INFERENCE_ENGINE" = "client" ]; then
    echo "📦 1. Exporting Client manifest payload..."
    tar -czf "$STAGING_DIR/client/gemma-client-manifests.tar.gz" -C "$PROD_ROOT" gemma-client/

else
    echo "📦 1. Exporting Dual Backend Gateway manifest payload..."
    tar -czf "$STAGING_DIR/gemma-gateway-gdc-manifests.tar.gz" -C "$PROD_ROOT" blueprints/ standalone/ gateway/ gemma-client/
fi

echo "📦 2. Copying documentation and helper scripts..."
if [ -f "$PROD_ROOT/README.md" ]; then
  cp "$PROD_ROOT/README.md" "$STAGING_DIR/gemma-gateway-README.md"
fi
cp -r "$SCRIPT_DIR"/* "$STAGING_DIR/common-scripts/"

echo "📦 3. Generating Checksum BOM (Bill of Materials)..."
cd "$STAGING_DIR"
find . -type f -not -name "gemma-gateway-BOM.txt" -not -name "gemma-gateway-manifest.txt" -exec shasum -a 256 {} \; > "gemma-gateway-BOM.txt"
cp "gemma-gateway-BOM.txt" "gemma-gateway-manifest.txt"
cd ../

echo "✅ All assets packaged into $STAGING_DIR successfully."
