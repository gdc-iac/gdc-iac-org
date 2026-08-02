#!/bin/bash
# scripts/mirror_images.sh
#
# Usage: ./scripts/mirror_images.sh <PATTERN_DIR> <OUTPUT_DIR>
# Example: ./scripts/mirror_images.sh ./p5-hybrid-llm-gateway ./artifacts
#
# This script pulls the public Docker images required for a specific pattern
# (defined in <PATTERN_DIR>/external_images.txt) and saves them as .tar archives
# for transfer to an air-gapped environment.
#
# The external_images.txt file should contain one image per line, e.g.:
# ollama/ollama:latest
# vllm/vllm-openai:latest

set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <PATTERN_DIR> <OUTPUT_DIR>"
    echo "Example: $0 ./p5-hybrid-llm-gateway ./artifacts"
    exit 1
fi

PATTERN_DIR=$1
OUTPUT_DIR=$2
IMAGE_LIST="${PATTERN_DIR}/external_images.txt"

# Check if image list exists
if [ ! -f "$IMAGE_LIST" ]; then
    echo "Error: Image list file not found at $IMAGE_LIST"
    echo "Please create 'external_images.txt' in the pattern directory with a list of images."
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Read images from file, ignoring comments and empty lines
mapfile -t IMAGES < <(grep -v '^[[:space:]]*#' "$IMAGE_LIST" | grep -v '^[[:space:]]*$')

if [ ${#IMAGES[@]} -eq 0 ]; then
    echo "No images found in $IMAGE_LIST"
    exit 0
fi

echo "Preparing images for air-gapped transfer from ${PATTERN_DIR}..."

for IMG in "${IMAGES[@]}"; do
    echo "---------------------------------------------------"
    echo "Processing: $IMG"
    
    # Check if image should be skipped
    if [ -n "$SKIP_IMAGES" ] && echo "$IMG" | grep -qE "$SKIP_IMAGES"; then
        echo "  > Skipping $IMG (matches SKIP_IMAGES='$SKIP_IMAGES')"
        continue
    fi
    
    # 1. Pull
    echo "  > Pulling image..."
    docker pull "$IMG"

    # 2. Save
    # Transform image name to filename (replace / and : with _)
    FILENAME=$(echo "$IMG" | tr '/:' '_').tar
    FILEPATH="${OUTPUT_DIR}/${FILENAME}"
    
    echo "  > Saving to ${FILEPATH}..."
    docker save -o "$FILEPATH" "$IMG"
    
    echo "  > Done: ${FILEPATH}"
done

echo "---------------------------------------------------"
echo "✅ All images saved to ${OUTPUT_DIR}"
echo ""
echo "NEXT STEPS (On Air-Gapped Workstation):"
echo "1. Transfer the .tar files to the secure environment."
echo "2. Load and push them to your internal registry:"
echo ""
echo "   export REGISTRY=<YOUR_INTERNAL_REGISTRY>"
echo ""

for IMG in "${IMAGES[@]}"; do
    FILENAME=$(echo "$IMG" | tr '/:' '_').tar
    # Extract short name for tagging, assuming typical format repo/image:tag or image:tag
    # We want the last component of the path before the tag
    # e.g. ollama/ollama:latest -> ollama
    # vllm/vllm-openai:latest -> vllm-openai
    # library/postgres:14 -> postgres
    
    # Logic: remove tag, then take basename
    IMAGE_NO_TAG=$(echo "$IMG" | cut -d':' -f1)
    SHORT_NAME=$(basename "$IMAGE_NO_TAG")
    
    echo "   docker load -i ${FILENAME}"
    echo "   docker tag ${IMG} \${REGISTRY}/${SHORT_NAME}:latest"
    echo "   docker push \${REGISTRY}/${SHORT_NAME}:latest"
    echo ""
done
