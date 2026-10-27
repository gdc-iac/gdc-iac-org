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

# Check for positional arguments
if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <patch_file> <target_file>"
    echo "Example: $0 v.1.23.3.patch config-sync-manifest-v.1.23.3.yaml"
    exit 1
fi

PATCH_FILE="$1"
TARGET_FILE="$2"
OUT_FILE="patched-$(basename "${TARGET_FILE}")"

if [ ! -f "${PATCH_FILE}" ]; then
    echo "Error: Patch file not found: ${PATCH_FILE}"
    exit 1
fi

if [ ! -f "${TARGET_FILE}" ]; then
    echo "Error: Target file not found: ${TARGET_FILE}"
    exit 1
fi

echo "Applying patch ${PATCH_FILE} to ${TARGET_FILE}..."
echo "Output will be saved to ${OUT_FILE}"

# Apply patch, overriding the filename in the patch with TARGET_FILE
patch -o "${OUT_FILE}" "${TARGET_FILE}" < "${PATCH_FILE}"

if [ $? -eq 0 ]; then
    echo "Patch applied successfully."
else
    echo "Error: Failed to apply patch."
    exit 1
fi
