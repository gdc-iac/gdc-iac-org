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

set -e
# Self-contained bulk image mirroring for deploy-to-production
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR=${1:-"${BASE_DIR}/artifacts/mirrored-images"}

echo "Starting bulk image mirroring for deploy-to-production patterns..."
echo "Output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

PATTERNS_WITH_EXTERNAL_IMAGES=$(find "${BASE_DIR}/patterns" -maxdepth 2 -name "external_images.txt" | xargs dirname | sort)

if [ -z "$PATTERNS_WITH_EXTERNAL_IMAGES" ]; then
  echo "No external_images.txt files found in patterns."
  exit 0
fi

for PATTERN_DIR in $PATTERNS_WITH_EXTERNAL_IMAGES; do
  PATTERN_NAME=$(basename "$PATTERN_DIR")
  echo ""
  echo "=================================================="
  echo "Mirroring images for $PATTERN_NAME..."
  echo "=================================================="
  PATTERN_OUT_DIR="${BASE_DIR}/packages/$PATTERN_NAME/external-dependencies/images"
  mkdir -p "$PATTERN_OUT_DIR"
  "$SCRIPT_DIR/mirror_images.sh" "$PATTERN_DIR" "$PATTERN_OUT_DIR"
done

echo ""
echo "=================================================="
echo "SUCCESS! All external images mirrored to $OUTPUT_DIR"
echo "=================================================="
