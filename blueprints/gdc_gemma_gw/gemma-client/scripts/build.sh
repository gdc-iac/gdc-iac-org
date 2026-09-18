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

# Default values
PROJECT_ID=${PROJECT_ID:-""}
REGISTRY_URL=${REGISTRY_HOST:-""}

# Parse flags
while getopts "p:r:" opt; do
  case $opt in
    p) PROJECT_ID="$OPTARG" ;;
    r) REGISTRY_URL="$OPTARG" ;;
    *) echo "Usage: $0 -p <PROJECT_ID> -r <REGISTRY_URL>" >&2; exit 1 ;;
  esac
done

if [ -z "$PROJECT_ID" ] || [ -z "$REGISTRY_URL" ]; then
    echo "Error: Project ID and Registry URL are required."
    echo "Usage: $0 -p <PROJECT_ID> -r <REGISTRY_URL>"
    exit 1
fi

# Determine the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Go to the pattern root (parent of scripts/)
cd "${SCRIPT_DIR}/.."

echo "Building Backend..."
docker build -t $REGISTRY_URL/gemma-client-backend:latest src/backend
docker push $REGISTRY_URL/gemma-client-backend:latest

echo "Building Frontend..."
docker build -t $REGISTRY_URL/gemma-client-frontend:latest src/frontend
docker push $REGISTRY_URL/gemma-client-frontend:latest

echo "Build Complete!"
