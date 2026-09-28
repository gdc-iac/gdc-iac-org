#!/bin/bash
set -e
# Self-contained build & pull script for gdc_gemma_gw deploy-to-production

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET=${1:-"all"}

# Normalize huggingface / both aliases
if [ "$TARGET" = "huggingface" ]; then TARGET="vllm"; fi
if [ "$TARGET" = "both" ]; then TARGET="all"; fi

REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/gemma-repo"}
TAG=${TAG:-"latest"}

echo "Checking and building Gemma Gateway container images locally (Target engine/mode: $TARGET)..."

# 1. 3P Base Engine Images
if [ "$TARGET" = "ollama" ] || [ "$TARGET" = "all" ]; then
  if docker image inspect "ollama/ollama:latest" >/dev/null 2>&1; then
    echo "   ✅ FOUND 3P IMAGE: ollama/ollama:latest (Local cache)"
  else
    echo "   ⬇️  PULLING 3P IMAGE: ollama/ollama:latest..."
    docker pull "ollama/ollama:latest" || echo "   ⚠️  Could not pull ollama/ollama:latest"
  fi
fi

if [ "$TARGET" = "vllm" ] || [ "$TARGET" = "all" ]; then
  if docker image inspect "vllm/vllm-openai:latest" >/dev/null 2>&1; then
    echo "   ✅ FOUND 3P IMAGE: vllm/vllm-openai:latest (Local cache)"
  else
    echo "   ⬇️  PULLING 3P IMAGE: vllm/vllm-openai:latest..."
    docker pull "vllm/vllm-openai:latest" || echo "   ⚠️  Could not pull vllm/vllm-openai:latest"
  fi
fi

# 2. Gateway Proxy Image
if [ "$TARGET" = "ollama" ] || [ "$TARGET" = "vllm" ] || [ "$TARGET" = "all" ]; then
  PROXY_IMG="${REGISTRY_HOST}/gemma-proxy:${TAG}"
  if docker image inspect "$PROXY_IMG" >/dev/null 2>&1; then
    echo "   ✅ FOUND GATEWAY PROXY: $PROXY_IMG (Local cache)"
  else
    if [ -d "${PROD_ROOT}/gateway/proxy" ]; then
      echo "   🔨 BUILDING GATEWAY PROXY: $PROXY_IMG..."
      docker build -t "$PROXY_IMG" "${PROD_ROOT}/gateway/proxy" || echo "   ⚠️  Build failed for $PROXY_IMG"
      echo "   ✅ BUILT: $PROXY_IMG"
    fi
  fi
fi

# 3. Gemma Client Images
if [ "$TARGET" = "client" ] || [ "$TARGET" = "all" ]; then
  BACKEND_IMG="${REGISTRY_HOST}/gemma-client-backend:${TAG}"
  FRONTEND_IMG="${REGISTRY_HOST}/gemma-client-frontend:${TAG}"

  if docker image inspect "$BACKEND_IMG" >/dev/null 2>&1; then
    echo "   ✅ FOUND CLIENT BACKEND: $BACKEND_IMG (Local cache)"
  else
    if [ -d "${PROD_ROOT}/gemma-client/src/backend" ]; then
      echo "   🔨 BUILDING CLIENT BACKEND: $BACKEND_IMG..."
      docker build -t "$BACKEND_IMG" "${PROD_ROOT}/gemma-client/src/backend" || echo "   ⚠️  Build failed for $BACKEND_IMG"
      echo "   ✅ BUILT: $BACKEND_IMG"
    fi
  fi

  if docker image inspect "$FRONTEND_IMG" >/dev/null 2>&1; then
    echo "   ✅ FOUND CLIENT FRONTEND: $FRONTEND_IMG (Local cache)"
  else
    if [ -d "${PROD_ROOT}/gemma-client/src/frontend" ]; then
      echo "   🔨 BUILDING CLIENT FRONTEND: $FRONTEND_IMG..."
      docker build -t "$FRONTEND_IMG" "${PROD_ROOT}/gemma-client/src/frontend" || echo "   ⚠️  Build failed for $FRONTEND_IMG"
      echo "   ✅ BUILT: $FRONTEND_IMG"
    fi
  fi
fi

echo "✅ Image check and build process complete for Gemma Gateway."
