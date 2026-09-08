#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0;0m' # No Color

# Usage
if [ -z "$1" ]; then
    echo "Usage: $0 <registry-url-prefix> [--dry-run]"
    echo "Example: $0 us-central1-docker.pkg.dev/my-project/my-repo"
    echo "Example: $0 harbor.gdc.local/library --dry-run"
    exit 1
fi

REGISTRY="$1"
DRY_RUN=false

if [ "$2" == "--dry-run" ]; then
    DRY_RUN=true
    echo "Running in DRY RUN mode. No images will be built or pushed."
fi

# Remove trailing slash if present
REGISTRY=${REGISTRY%/}

# Array of "image_name:build_context_path"
# Paths are relative to the repository root
# MUST MATCH scripts/stage1-local-test.sh
IMAGES=(
    "p1-frontend:p1-resilient-3-tier-webapp/example-app/src/frontend"
    "p1-backend:p1-resilient-3-tier-webapp/example-app/src/backend"
    "p3-legacy-app:p3-legacy-vm-modern-db/example-app/legacy-app"
    "p4-producer:p4-event-driven-kafka/example-app/producer"
    "p4-consumer:p4-event-driven-kafka/example-app/consumer"
    "p5-gateway:p5-hybrid-llm-gateway/example-app/gateway"
    "p6-mock-llm:p6-resilient-rag-agent/example-app/mock-llm"
    "p6-ingestion:p6-resilient-rag-agent/example-app/ingestion"
    "p6-query-service:p6-resilient-rag-agent/example-app/query-service"
    "p7-mock-llm:p7-agentic-data-analyst/example-app/mock-llm"
    "p7-agent:p7-agentic-data-analyst/example-app/agent"
    "p8-training-pipeline:p8-closed-loop-mlops/example-app/training-pipeline"
)

# Get the repository root directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOTAL=${#IMAGES[@]}
FAILED=0

echo "Starting Bulk Push for $TOTAL Example Application images to $REGISTRY..."
echo "---------------------------------------------------"

for item in "${IMAGES[@]}"; do
    IMAGE_KEY="${item%%:*}"
    BUILD_CONTEXT="${item#*:}"
    FULL_PATH="$REPO_ROOT/$BUILD_CONTEXT"
    
    # Target Image Name: registry/image_key:latest
    # You can change 'latest' to a version if needed, or pass it as an arg in future
    TARGET_IMAGE="$REGISTRY/$IMAGE_KEY:latest"

    echo "Processing $IMAGE_KEY..."
    
    if [ ! -d "$FULL_PATH" ]; then
        echo -e "${RED}[FAIL] Directory not found: $BUILD_CONTEXT${NC}"
        FAILED=$((FAILED + 1))
        continue
    fi

    if [ "$DRY_RUN" = true ]; then
        echo -e "  ${GREEN}[DRY-RUN]${NC} docker build -t $TARGET_IMAGE $FULL_PATH"
        echo -e "  ${GREEN}[DRY-RUN]${NC} docker push $TARGET_IMAGE"
    else
        echo "  - Building $TARGET_IMAGE..."
        if docker build -t "$TARGET_IMAGE" "$FULL_PATH"; then
            echo "  - Pushing $TARGET_IMAGE..."
            if docker push "$TARGET_IMAGE"; then
                echo -e "    ${GREEN}Success${NC}"
            else
                echo -e "    ${RED}Push Failed${NC}"
                FAILED=$((FAILED + 1))
            fi
        else
            echo -e "    ${RED}Build Failed${NC}"
            FAILED=$((FAILED + 1))
        fi
    fi
    echo "---------------------------------------------------"
done

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}Bulk push completed with $FAILED errors.${NC}"
    exit 1
else
    echo -e "${GREEN}All images processed successfully!${NC}"
    exit 0
fi
