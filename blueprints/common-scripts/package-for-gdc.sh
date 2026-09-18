#!/bin/bash
set -e
# Self-contained GDC packaging script for deploy-to-production

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ROOT="$(dirname "$SCRIPT_DIR")"

ENGINE="both"
SKIP_IMAGES=false
SKIP_LLM_MODELS=false
PATTERN_ARG=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-images|-s)
      SKIP_IMAGES=true
      shift
      ;;
    --skip-llm-models|--skip-llm)
      SKIP_LLM_MODELS=true
      shift
      ;;
    --engine|-e)
      ENGINE="$2"
      shift 2
      ;;
    --skip-vllm)
      ENGINE="ollama"
      shift
      ;;
    *)
      PATTERN_ARG="$1"
      shift
      ;;
  esac
done

if [ -z "$PATTERN_ARG" ]; then
  echo "Usage: $0 [--skip-images] [--skip-llm-models] [--engine ollama|vllm|huggingface|both] <pattern-name|all>"
  echo "Examples:"
  echo "  $0 all                                           # Package ALL patterns"
  echo "  $0 --engine ollama all                          # Package ALL patterns with Ollama LLM models"
  echo "  $0 --skip-llm-models all                        # Package ALL patterns, omitting heavy LLM models"
  echo "  $0 --skip-images all                            # Package ALL patterns (manifests only)"
  echo "  $0 p6-resilient-rag-agent                      # Package single pattern"
  exit 1
fi

package_single_pattern() {
  local PATTERN_DIR="$1"
  local PATTERN_NAME=$(basename "$PATTERN_DIR")

  if [ ! -d "$PATTERN_DIR" ]; then
    echo "Error: Directory $PATTERN_DIR does not exist."
    return 1
  fi

  echo ""
  echo "=================================================="
  echo "📦 Packaging $PATTERN_NAME for GDC production..."
  echo "=================================================="

  if [ "$SKIP_IMAGES" = true ]; then
    echo "⏭️  Bypassing local image build and container tarball export (--skip-images enabled)."
  else
    echo "📦 Checking and building required images locally (Engine: $ENGINE, Skip LLM Models: $SKIP_LLM_MODELS)..."
    local BUILD_FLAGS=""
    if [ "$SKIP_LLM_MODELS" = true ]; then BUILD_FLAGS="$BUILD_FLAGS --skip-llm-models"; fi
    BUILD_FLAGS="$BUILD_FLAGS --engine $ENGINE"
    "$SCRIPT_DIR/build-images.sh" $BUILD_FLAGS "$PATTERN_NAME"
  fi

  PACKAGE_DIR="${PROD_ROOT}/packages/${PATTERN_NAME}"
  STAGING_DIR="/tmp/${PATTERN_NAME}-gdc-package"

  mkdir -p "$PACKAGE_DIR"
  rm -rf "$STAGING_DIR"
  mkdir -p "$STAGING_DIR"

  cp -r "$PATTERN_DIR/manifests" "$STAGING_DIR/"
  for d in example-app src manual charts; do
    if [ -d "$PATTERN_DIR/$d" ]; then
      cp -r "$PATTERN_DIR/$d" "$STAGING_DIR/"
    fi
  done

  if [ -f "$PATTERN_DIR/README.md" ]; then
    cp "$PATTERN_DIR/README.md" "$STAGING_DIR/"
  fi
  if [ -f "$PATTERN_DIR/implementation-guide.md" ]; then
    cp "$PATTERN_DIR/implementation-guide.md" "$STAGING_DIR/"
  fi

  MANIFESTS_TAR="${PACKAGE_DIR}/${PATTERN_NAME}-gdc-manifests.tar.gz"
  echo "Creating manifests tarball: $MANIFESTS_TAR"
  tar -czf "$MANIFESTS_TAR" -C "$STAGING_DIR" .

  IMAGES_TAR="${PACKAGE_DIR}/${PATTERN_NAME}-gdc-images.tar"
  EXISTING_IMAGES=""
  FAILED_IMAGES=""
  SKIPPED_IMAGES=""

  if [ "$SKIP_IMAGES" = false ]; then
    IMAGES=$(grep -rhE '^\s*image:\s*' "$PATTERN_DIR/manifests" | awk '{print $2}' | tr -d '"{}' | sort | uniq)

    # Add external images if present
    if [ -f "$PATTERN_DIR/external_images.txt" ]; then
      while read -r ext_img; do
        if [ -n "$ext_img" ] && [[ ! "$ext_img" =~ ^# ]]; then
          IMAGES="$IMAGES $ext_img"
        fi
      done < "$PATTERN_DIR/external_images.txt"
    fi

    if [ -n "$IMAGES" ]; then
      echo "🔍 Tracking Required Container Images:"
      for img in $IMAGES; do
        if [ "$SKIP_LLM_MODELS" = true ] && [[ "$img" == *"ollama"* || "$img" == *"vllm"* || "$img" == *"huggingface"* || "$img" == *"mock-llm"* ]]; then
          echo "   ⏭️  SKIPPED: $img (LLM model image omitted via --skip-llm-models)"
          SKIPPED_IMAGES="$SKIPPED_IMAGES $img"
          continue
        fi

        if [ "$ENGINE" = "ollama" ] && [[ "$img" == *"vllm"* || "$img" == *"huggingface"* ]]; then
          echo "   ⏭️  SKIPPED: $img (vLLM/HuggingFace image bypassed via --engine ollama)"
          SKIPPED_IMAGES="$SKIPPED_IMAGES $img"
          continue
        fi
        if [[ "$ENGINE" == "vllm" || "$ENGINE" == "huggingface" ]] && [[ "$img" == *"ollama"* ]]; then
          echo "   ⏭️  SKIPPED: $img (Ollama image bypassed via --engine $ENGINE)"
          SKIPPED_IMAGES="$SKIPPED_IMAGES $img"
          continue
        fi

        if docker image inspect "$img" >/dev/null 2>&1; then
          echo "   ✅ FOUND:   $img"
          EXISTING_IMAGES="$EXISTING_IMAGES $img"
        elif docker pull "$img" >/dev/null 2>&1; then
          echo "   ✅ LOADED:  $img"
          EXISTING_IMAGES="$EXISTING_IMAGES $img"
        else
          echo "   ❌ FAILED:  $img"
          FAILED_IMAGES="$FAILED_IMAGES $img"
        fi
      done

      if [ -n "$EXISTING_IMAGES" ]; then
        docker save -o "$IMAGES_TAR" $EXISTING_IMAGES
        echo "✅ Wrote payload to $IMAGES_TAR"
      fi
    fi
  fi

  BOM_TXT="${PACKAGE_DIR}/${PATTERN_NAME}-BOM.txt"
  echo "Bill of Materials (BOM) - $PATTERN_NAME" > "$BOM_TXT"
  echo "Generated on: $(date)" >> "$BOM_TXT"
  echo "Engine Mode: $ENGINE" >> "$BOM_TXT"
  echo "Skip Images: $SKIP_IMAGES" >> "$BOM_TXT"
  echo "Skip LLM Models: $SKIP_LLM_MODELS" >> "$BOM_TXT"
  echo "==================================================" >> "$BOM_TXT"
  for img in $EXISTING_IMAGES; do echo "  - $img" >> "$BOM_TXT"; done

  MANIFEST_TXT="${PACKAGE_DIR}/${PATTERN_NAME}-manifest.txt"
  rm -f "$MANIFEST_TXT"
  if [ -f "$MANIFESTS_TAR" ]; then shasum -a 256 "$MANIFESTS_TAR" >> "$MANIFEST_TXT"; fi
  if [ -f "$IMAGES_TAR" ]; then shasum -a 256 "$IMAGES_TAR" >> "$MANIFEST_TXT"; fi

  README_FILE="${PACKAGE_DIR}/${PATTERN_NAME}-README.md"
  if [ -f "$PATTERN_DIR/README.md" ]; then
    cp "$PATTERN_DIR/README.md" "$README_FILE"
  fi

  mkdir -p "$PACKAGE_DIR/helper-scripts"
  cp "$SCRIPT_DIR/unpack-for-gdc.sh" "$PACKAGE_DIR/helper-scripts/"
  cp "$SCRIPT_DIR/configure-blueprints.sh" "$PACKAGE_DIR/helper-scripts/"
  cp "$SCRIPT_DIR/build-images.sh" "$PACKAGE_DIR/helper-scripts/"

  rm -rf "$STAGING_DIR"
  echo "✅ Packaging complete for $PATTERN_NAME in $PACKAGE_DIR"
}

if [ "$PATTERN_ARG" = "all" ] || [ "$PATTERN_ARG" = "all-patterns" ]; then
  echo "🚀 Bulk packaging ALL production patterns (Engine: $ENGINE, Skip LLM Models: $SKIP_LLM_MODELS, Skip Images: $SKIP_IMAGES)..."
  ALL_PATTERN_DIRS=$(find "${PROD_ROOT}/patterns" -maxdepth 1 -mindepth 1 -type d | sort)
  for pdir in $ALL_PATTERN_DIRS; do
    package_single_pattern "$pdir"
  done
  echo ""
  echo "=================================================="
  echo "🎉 SUCCESS! Bulk packaging complete for all patterns in ${PROD_ROOT}/packages/"
  echo "=================================================="
else
  if [[ "$PATTERN_ARG" == patterns/* ]]; then
    TARGET_P_DIR="${PROD_ROOT}/${PATTERN_ARG}"
  elif [[ "$PATTERN_ARG" == /* ]]; then
    TARGET_P_DIR="$PATTERN_ARG"
  else
    TARGET_P_DIR="${PROD_ROOT}/patterns/${PATTERN_ARG}"
  fi
  package_single_pattern "$TARGET_P_DIR"
fi
