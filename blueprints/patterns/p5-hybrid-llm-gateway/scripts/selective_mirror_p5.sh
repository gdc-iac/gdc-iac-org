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

# p5-hybrid-llm-gateway/scripts/selective_mirror_p5.sh
#
# Usage: ./selective_mirror_p5.sh <OUTPUT_DIR> [ollama|vllm|all]
#
# This script is a custom wrapper for Pattern 5 that allows users to mirror 
# only the images required for their chosen LLM backend (Ollama or vLLM).
#
# If no backend is specified, it prompts the user for a choice.

set -e

OUTPUT_DIR=$1
COMPONENT=$2

if [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: $0 <OUTPUT_DIR> [ollama|vllm|all]"
    echo "Example: $0 ./artifacts ollama"
    exit 1
fi

# If component not specified, ask user
if [ -z "$COMPONENT" ]; then
    echo "Which LLM backend are you deploying?"
    echo "1) Ollama (Recommended for smaller models/simpler setup)"
    echo "2) vLLM (Recommended for production/high-throughput)"
    echo "3) Both (Mirror everything)"
    read -p "Select option [1-3]: " CHOICE
    
    case $CHOICE in
        1) COMPONENT="ollama" ;;
        2) COMPONENT="vllm" ;;
        3) COMPONENT="all" ;;
        *) echo "Invalid choice"; exit 1 ;;
    esac
fi

# Define images based on selection
IMAGES=()

if [ "$COMPONENT" == "ollama" ] || [ "$COMPONENT" == "all" ]; then
    IMAGES+=("ollama/ollama:latest")
fi

if [ "$COMPONENT" == "vllm" ] || [ "$COMPONENT" == "all" ]; then
    # Note: vLLM image is large, mirroring only if needed saves time/bandwidth
    IMAGES+=("vllm/vllm-openai:latest")
fi

echo "Detailed Selection: $COMPONENT"
echo "Images to mirror:"
for img in "${IMAGES[@]}"; do
    echo " - $img"
done
echo "---------------------------------------------------"

mkdir -p "$OUTPUT_DIR"

for IMG in "${IMAGES[@]}"; do
    echo "Processing: $IMG"
    
    # 1. Pull
    echo "  > Pulling image..."
    docker pull "$IMG"

    # 2. Save
    FILENAME=$(echo "$IMG" | tr '/:' '_').tar
    FILEPATH="${OUTPUT_DIR}/${FILENAME}"
    
    echo "  > Saving to ${FILEPATH}..."
    docker save -o "$FILEPATH" "$IMG"
    
    echo "  > Done: ${FILEPATH}"
done

echo "---------------------------------------------------"
echo "✅ Selected P5 images saved to ${OUTPUT_DIR}"
echo ""
echo "NEXT STEPS (Air-Gapped Workstation):"
echo "export REGISTRY=<YOUR_INTERNAL_REGISTRY_URL>"
echo ""
for IMG in "${IMAGES[@]}"; do
    FILENAME=$(echo "$IMG" | tr '/:' '_').tar
    # Determine short name logic: ollama/ollama -> ollama, vllm/vllm-openai -> vllm-openai
    REPO_NAME=$(echo "$IMG" | cut -d':' -f1)
    IMAGE_NAME=$(basename "$REPO_NAME")
    TAG=$(echo "$IMG" | cut -d':' -f2)
    
    echo "docker load -i ${FILENAME}"
    echo "docker tag ${IMG} \${REGISTRY}/${IMAGE_NAME}:${TAG}"
    echo "docker push \${REGISTRY}/${IMAGE_NAME}:${TAG}"
    echo ""
done
