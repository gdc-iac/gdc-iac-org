#!/bin/bash
# Direct-to-Cluster (D2C) installation script for GDC-ag standalone testing.
# Emulates the GitOps / ConfigSync workflow by applying charts locally.

set -e

# Move to the directory of the script so relative paths work
cd "$(dirname "$0")"

NAMESPACE="gemma-inference"

echo "🔄 Hydrating and installing Gemma Gateway manifests directly to GKE..."

# 1. Create Namespace
kubectl apply -f manifests/00-namespace.yaml

# 2. Install Inference Backend (Ollama by default, or vLLM)
INFERENCE_ENGINE=${INFERENCE_ENGINE:-ollama}
OLLAMA_MODEL_VARIANT=${OLLAMA_MODEL_VARIANT:-26b}

if [ "$INFERENCE_ENGINE" = "ollama" ]; then
    if [ -n "$REGISTRY_HOST" ]; then
        echo "📦 Installing Ollama Backend (26B)..."
        helm template ollama-26b ../blueprints/ollama-gke \
          --set image.repository="${REGISTRY_HOST}/ollama-gemma-26b" \
          --set image.tag="latest" \
          --set fullnameOverride="ollama-26b" \
          --set model.variant="26b" \
          --set persistence.enabled=false | kubectl apply -n $NAMESPACE -f -

        echo "📦 Installing Ollama Backend (31B)..."
        helm template ollama-31b ../blueprints/ollama-gke \
          --set image.repository="${REGISTRY_HOST}/ollama-gemma-31b" \
          --set image.tag="latest" \
          --set fullnameOverride="ollama-31b" \
          --set model.variant="31b" \
          --set persistence.enabled=false | kubectl apply -n $NAMESPACE -f -
    else
        echo "📦 Installing Ollama Backend (Default)..."
        helm template ollama ../blueprints/ollama-gke | kubectl apply -n $NAMESPACE -f -
    fi
elif [ "$INFERENCE_ENGINE" = "vllm" ]; then
    echo "ℹ️ vLLM Serving Engine is managed natively via Helm 'upgrade --install' commands. Skipping script-based template to prevent resource clashes."
else
    echo "❌ Invalid INFERENCE_ENGINE specified. Use 'ollama' or 'vllm'."
    exit 1
fi

# 3. Deploy Gateway Proxy
GATEWAY_MANIFEST="manifests/01-gateway.yaml"
if [ "$INFERENCE_ENGINE" = "ollama" ]; then
    GATEWAY_MANIFEST="manifests/01-gateway-ollama.yaml"
fi

if [ -n "$REGISTRY_HOST" ]; then
    echo "✏️ Overriding placeholder image in ${GATEWAY_MANIFEST} with ${REGISTRY_HOST}/gemma-proxy:latest..."
    sed -i "s|image: gemma-gateway:latest|image: ${REGISTRY_HOST}/gemma-proxy:latest|g" "${GATEWAY_MANIFEST}"
fi

if [ "$INFERENCE_ENGINE" = "ollama" ]; then
    echo "✏️ Injecting OLLAMA_MODEL_VARIANT=${OLLAMA_MODEL_VARIANT} into ${GATEWAY_MANIFEST}..."
    sed -i "s|value: \"26b\"|value: \"${OLLAMA_MODEL_VARIANT}\"|g" "${GATEWAY_MANIFEST}"
fi

kubectl apply -n $NAMESPACE -f "${GATEWAY_MANIFEST}"

echo "✅ Deployment complete. Verify pods using:"
echo "kubectl get pods -n $NAMESPACE"
