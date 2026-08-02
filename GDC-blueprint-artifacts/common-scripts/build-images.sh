#!/bin/bash
set -e
# Self-contained local image builder/puller script for deploy-to-production

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ROOT="$(dirname "$SCRIPT_DIR")"

ENGINE="both"
SKIP_LLM_MODELS=false
PATTERN_ARG=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-llm-models|--skip-llm)
      SKIP_LLM_MODELS=true
      shift
      ;;
    --engine|-e)
      ENGINE="$2"
      shift 2
      ;;
    *)
      PATTERN_ARG="$1"
      shift
      ;;
  esac
done

PATTERN_ARG=${PATTERN_ARG:-"all"}

echo "Checking and building local container images for deploy-to-production (Engine: $ENGINE, Skip LLM Models: $SKIP_LLM_MODELS)..."

if [ "$PATTERN_ARG" = "all" ] || [ "$PATTERN_ARG" = "all-patterns" ]; then
  PATTERNS=$(find "${PROD_ROOT}/patterns" -maxdepth 1 -mindepth 1 -type d | sort)
else
  if [[ "$PATTERN_ARG" == patterns/* ]]; then
    PATTERNS="${PROD_ROOT}/${PATTERN_ARG}"
  else
    PATTERNS="${PROD_ROOT}/patterns/${PATTERN_ARG}"
  fi
fi

for PATTERN_DIR in $PATTERNS; do
  PATTERN_NAME=$(basename "$PATTERN_DIR")
  if [ ! -d "$PATTERN_DIR" ]; then
    continue
  fi

  echo ""
  echo "=================================================="
  echo "Processing container images for $PATTERN_NAME..."
  echo "=================================================="

  # 1. Check/Pull 3P Images from external_images.txt
  if [ -f "$PATTERN_DIR/external_images.txt" ]; then
    while read -r img; do
      if [ -z "$img" ] || [[ "$img" =~ ^[[:space:]]*# ]]; then
        continue
      fi

      if [ "$SKIP_LLM_MODELS" = true ] && [[ "$img" == *"ollama"* || "$img" == *"vllm"* || "$img" == *"huggingface"* ]]; then
        echo "   ⏭️  SKIPPED LLM MODEL IMAGE: $img (--skip-llm-models enabled)"
        continue
      fi

      if [ "$ENGINE" = "ollama" ] && [[ "$img" == *"vllm"* || "$img" == *"huggingface"* ]]; then
        echo "   ⏭️  SKIPPED 3P IMAGE: $img (Bypassed via --engine ollama)"
        continue
      fi
      if [[ "$ENGINE" == "vllm" || "$ENGINE" == "huggingface" ]] && [[ "$img" == *"ollama"* ]]; then
        echo "   ⏭️  SKIPPED 3P IMAGE: $img (Bypassed via --engine $ENGINE)"
        continue
      fi

      if docker image inspect "$img" >/dev/null 2>&1; then
        echo "   ✅ FOUND 3P IMAGE: $img (Local cache)"
      else
        echo "   ⬇️  PULLING 3P IMAGE: $img..."
        docker pull "$img" || echo "   ⚠️  Could not pull $img"
      fi
    done < "$PATTERN_DIR/external_images.txt"
  fi

  # 2. Check/Build Custom Dockerfiles
  find "$PATTERN_DIR" -type f -name "Dockerfile*" | while read -r dockerfile; do
    df_dir=$(dirname "$dockerfile")
    component_name=$(basename "$df_dir")
    
    IMAGES_IN_MANIFESTS=$(grep -rhE '^\s*image:\s*' "$PATTERN_DIR/manifests" 2>/dev/null | awk '{print $2}' | tr -d '"{}' | grep "$component_name" || true)

    if [ -z "$IMAGES_IN_MANIFESTS" ]; then
      REGISTRY=${REGISTRY_HOST:-"harbor.gdc.local"}
      IMAGES_IN_MANIFESTS="${REGISTRY}/${PATTERN_NAME}-${component_name}:latest"
    fi

    for img in $IMAGES_IN_MANIFESTS; do
      if [ "$SKIP_LLM_MODELS" = true ] && [[ "$img" == *"ollama"* || "$img" == *"vllm"* || "$img" == *"huggingface"* || "$img" == *"mock-llm"* ]]; then
        echo "   ⏭️  SKIPPED CUSTOM LLM IMAGE: $img (--skip-llm-models enabled)"
        continue
      fi
      if docker image inspect "$img" >/dev/null 2>&1; then
        echo "   ✅ FOUND CUSTOM IMAGE: $img (Local cache)"
      else
        echo "   🔨 BUILDING CUSTOM IMAGE: $img from $dockerfile..."
        docker build -f "$dockerfile" -t "$img" "$df_dir" || echo "   ⚠️  Build failed for $img"
      fi
    done
  done
done

echo ""
echo "✅ Local image check and build process complete."
