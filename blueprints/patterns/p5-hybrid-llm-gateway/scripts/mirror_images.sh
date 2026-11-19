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

# p5-hybrid-llm-gateway/scripts/mirror_images.sh
#
# Usage: ./mirror_images.sh <OUTPUT_DIR>
# Example: ./mirror_images.sh ./artifacts
#
# This script pulls the public Docker images required for Pattern 5 (Ollama, vLLM)
# and saves them as .tar archives for transfer to an air-gapped environment.

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <OUTPUT_DIR>"
    echo "Example: $0 ./artifacts"
    exit 1
fi

OUTPUT_DIR=$1
mkdir -p "$OUTPUT_DIR"

# List of images to mirror
IMAGES=(
    "ollama/ollama:latest"
    "vllm/vllm-openai:latest"
)

echo "Preparing images for air-gapped transfer..."

for IMG in "${IMAGES[@]}"; do
    echo "---------------------------------------------------"
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
    SHORT_NAME=$(echo "$IMG" | cut -d'/' -f2 | cut -d':' -f1) # Extracts 'ollama' from 'ollama/ollama:latest'
    
    echo "   docker load -i ${FILENAME}"
    echo "   docker tag ${IMG} \${REGISTRY}/${SHORT_NAME}:latest"
    echo "   docker push \${REGISTRY}/${SHORT_NAME}:latest"
    echo ""
done
