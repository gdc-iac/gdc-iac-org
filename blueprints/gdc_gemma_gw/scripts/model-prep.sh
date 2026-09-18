#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Model Preparation Script for GDC-ag
# Purpose: Downloads Gemma 4 weights for both Ollama and vLLM backends, formatting them for air-gapped PVC ingestion.

export HF_TOKEN=$1
GGUF_MODEL="gemma:7b" # Update to 'gemma:27b' for Gemma 4 larger variants when available
HF_MODEL_ID="google/gemma-1.1-7b-it" # Update to google/gemma-4-26b-it when available

OUTPUT_DIR="./gemma-models"
OLLAMA_DIR="$OUTPUT_DIR/ollama"
VLLM_DIR="$OUTPUT_DIR/vllm"

if [ -z "$HF_TOKEN" ]; then
  echo "❌ Error: HuggingFace Token required. Usage: ./model-prep.sh <hf_token>"
  exit 1
fi

mkdir -p $OLLAMA_DIR $VLLM_DIR

echo "--- 1. Downloading Ollama (GGUF) Weights ---"
echo "NOTE: This requires the 'ollama' CLI installed locally."
# Start Ollama temporarily and pull the model to our specific directory
OLLAMA_MODELS=$OLLAMA_DIR ollama pull $GGUF_MODEL

echo "--- 2. Downloading vLLM (Safetensors) Weights ---"
echo "Downloading $HF_MODEL_ID from HuggingFace..."
# Install HF CLI if not present
pip install -U "huggingface_hub[cli]"
huggingface-cli download $HF_MODEL_ID --local-dir $VLLM_DIR --token $HF_TOKEN

echo "✅ Model weights prepared."
echo "- Ollama blobs stored in: $OLLAMA_DIR"
echo "- vLLM weights stored in: $VLLM_DIR"
echo ""
echo "📦 To load into GDC-ag: Tar these directories, transfer via Data Appliance, and extract into the respective GKE PVCs."
