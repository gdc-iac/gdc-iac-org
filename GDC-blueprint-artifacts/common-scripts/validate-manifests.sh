#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "Starting Bulk Manifest Validation..."
echo "---------------------------------------------------"

# Check for cluster connectivity
if ! kubectl cluster-info >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Unable to connect to a Kubernetes cluster.${NC}"
    echo "Manifest validation requires a running cluster (e.g., kind, minikube, docker-desktop)"
    echo "to validate Custom Resources (DBCluster, VirtualMachine, etc)."
    echo ""
    echo "Please start a local cluster and try again."
    exit 1
fi


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

if [ -d "${BASE_DIR}/patterns" ]; then
    PATTERNS_DIR="${BASE_DIR}/patterns"
else
    PATTERNS_DIR="${BASE_DIR}"
fi

PATTERN_DIRS=$(find "$PATTERNS_DIR" -maxdepth 1 -mindepth 1 -type d -name "p*" ! -name "*deprecated*" | sort)

PASSED=0
FAILED=0
FAILED_PATTERNS=()

for pattern_path in $PATTERN_DIRS; do
    pattern=$(basename "$pattern_path")
    echo "Validating $pattern..."
    MANIFEST_DIR="$pattern_path/manifests"
    
    if [ ! -d "$MANIFEST_DIR" ]; then
        echo -e "  ${RED}[FAIL] Manifest directory not found: $MANIFEST_DIR${NC}"
        FAILED=$((FAILED + 1))
        FAILED_PATTERNS+=("$pattern (Missing manifests)")
        continue
    fi

    # Check if we can validate against a server or if we need to warn about CRDs
    # If kubectl can't connect to a server, it will fail on CRDs unless we do something clever.
    # But 'apply --dry-run=client' DOES NOT require a server for standard resources.
    # It DOES require a server (or local schema) for CRDs.
    
    # We try to validate. If it fails due to "no matches for kind", we warn the user.
    OUTPUT=$(kubectl apply --dry-run=client --validate=false -R -f "$MANIFEST_DIR" 2>&1)
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "  ${GREEN}Validation Passed${NC}"
        PASSED=$((PASSED + 1))
    else
        # Check if error is due to missing CRDs
        if echo "$OUTPUT" | grep -q "no matches for kind"; then
            echo -e "  ${RED}Validation Failed (Missing CRDs)${NC}"
            echo "  To fix this, you must have the GDC CRDs installed in your cluster."
            echo "  If you have a local cluster (e.g. kind), run:"
            echo "    kubectl apply -f tests/mock-crds.yaml"
        else
            echo -e "  ${RED}Validation Failed${NC}"
        fi
        echo "$OUTPUT" | sed 's/^/    /'
        FAILED=$((FAILED + 1))
        FAILED_PATTERNS+=("$pattern")
    fi
    echo "---------------------------------------------------"
done

echo ""
echo "Manifest Validation Summary:"
echo "---------------------------------------------------"
TOTAL_PATTERNS=$(echo "$PATTERN_DIRS" | wc -w)
echo -e "Total: $TOTAL_PATTERNS"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ ${#FAILED_PATTERNS[@]} -ne 0 ]; then
    exit 1
else
    exit 0
fi
