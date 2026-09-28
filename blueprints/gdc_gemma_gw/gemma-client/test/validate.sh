#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0;0m'

echo "========================================"
echo "Validating Gemma Client K8s Manifests"
echo "========================================"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PATTERN_DIR="$(dirname "$SCRIPT_DIR")"

FAILED=0

validate_file() {
    local file="$1"
    echo -n "Validating $(basename "$file")... "
    if kubectl apply --dry-run=client -f "$file" > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC}"
    else
        echo -e "${RED}[FAILED]${NC}"
        FAILED=$((FAILED + 1))
    fi
}

# Validate GDC App Manifests
if [ -d "$PATTERN_DIR/manifests/gdc/apps" ]; then
    for f in "$PATTERN_DIR/manifests/gdc/apps"/*.yaml; do
        [ -e "$f" ] || continue
        validate_file "$f"
    done
fi

# Validate GDC DB Manifests
if [ -d "$PATTERN_DIR/manifests/gdc/db" ]; then
    for f in "$PATTERN_DIR/manifests/gdc/db"/*.yaml; do
        [ -e "$f" ] || continue
        validate_file "$f"
    done
fi

# Validate GCP (Stepping Stone) App Manifests
if [ -d "$PATTERN_DIR/manifests/apps" ]; then
    for f in "$PATTERN_DIR/manifests/apps"/*.yaml; do
        [ -e "$f" ] || continue
        validate_file "$f"
    done
fi

# Validate GCP (Stepping Stone) Data Manifests
if [ -d "$PATTERN_DIR/manifests/gcp" ]; then
    for f in "$PATTERN_DIR/manifests/gcp"/*.yaml; do
        [ -e "$f" ] || continue
        validate_file "$f"
    done
fi

echo "========================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}Validation successful! All manifests are syntactically correct.${NC}"
    exit 0
else
    echo -e "${RED}Validation failed. $FAILED file(s) contain syntax/schema errors.${NC}"
    exit 1
fi
