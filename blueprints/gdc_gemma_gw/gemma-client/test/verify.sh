#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0;0m'

# Default namespace if none provided
NAMESPACE=${NAMESPACE:-"gemma-inference"}

echo "========================================"
echo "Verifying Deployed Gemma Client Resources"
echo "Namespace: $NAMESPACE"
echo "========================================"

FAILED=0

check_pods() {
    local selector="$1"
    local label="$2"
    echo -n "Checking $label pods... "
    
    local status=$(kubectl get pods -n "$NAMESPACE" -l "$selector" -o jsonpath='{.items[*].status.phase}' 2>/dev/null)
    
    if [[ -z "$status" ]]; then
        echo -e "${RED}[NOT FOUND]${NC}"
        FAILED=$((FAILED + 1))
        return 1
    fi
    
    local all_running=true
    for p in $status; do
        if [[ "$p" != "Running" ]]; then
            all_running=false
        fi
    done
    
    if [ "$all_running" = true ]; then
        echo -e "${GREEN}[RUNNING]${NC}"
    else
        echo -e "${RED}[PENDING/FAILED]${NC} (Status: $status)"
        FAILED=$((FAILED + 1))
    fi
}

check_service() {
    local name="$1"
    echo -n "Checking Service $name... "
    if kubectl get svc "$name" -n "$NAMESPACE" > /dev/null 2>&1; then
        echo -e "${GREEN}[FOUND]${NC}"
    else
        echo -e "${RED}[MISSING]${NC}"
        FAILED=$((FAILED + 1))
    fi
}

# Verify Postgres (Data Storage Emulator)
check_pods "app=postgres" "PostgreSQL Database"
check_service "postgres-svc"

# Verify Backend Service
check_pods "app=backend" "FastAPI Backend"
check_service "backend-svc"

# Verify Frontend Service
check_pods "app=frontend" "React Frontend"
check_service "frontend-svc"

echo "========================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}Verification successful! All client pods and services are healthy.${NC}"
    exit 0
else
    echo -e "${RED}Verification failed. $FAILED component(s) are not in a healthy/active state.${NC}"
    exit 1
fi
