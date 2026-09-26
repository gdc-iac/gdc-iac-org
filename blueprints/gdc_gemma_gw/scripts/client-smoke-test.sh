#!/bin/bash
# Gemma Client Backend - Zero-Dependency Smoke-Test Script
# Verifies the client backend endpoints and RBAC policies using native curl.

set -e

# Colors for premium terminal output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLIENT_URL=${CLIENT_URL:-"http://localhost:50084"}

echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}      Gemma Client - Zero-Dependency Smoke Test       ${NC}"
echo -e "${BLUE}=====================================================${NC}"
echo -e "🎯 Target Client URL: ${YELLOW}${CLIENT_URL}${NC}\n"

# Helper function to print test status
print_status() {
    local name="$1"
    local status="$2"
    if [ "$status" = "PASS" ]; then
        echo -e "  [${GREEN}PASS${NC}] $name"
    else
        echo -e "  [${RED}FAIL${NC}] $name"
        exit 1
    fi
}

# 1. Check Client Health
echo -e "${BLUE}[1/4] Checking Client Backend Health...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${CLIENT_URL}/health" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    HEALTH_JSON=$(curl -s "${CLIENT_URL}/health")
    echo -e "  Health status: ${YELLOW}${HEALTH_JSON}${NC}"
    print_status "Client Health" "PASS"
else
    echo -e "  ${RED}Error: Received HTTP status ${HTTP_CODE} from /health${NC}"
    echo -e "  💡 Tip: Ensure you are running 'kubectl port-forward svc/backend-svc 50084:8000 -n test-project' (or your client namespace) in a background tab!"
    print_status "Client Health" "FAIL"
fi
echo ""

# 2. Check Dynamic Model Discovery
echo -e "${BLUE}[2/4] Checking Dynamic Models Mapping...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${CLIENT_URL}/models" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    MODELS_JSON=$(curl -s "${CLIENT_URL}/models")
    echo -e "  Mapped models: ${YELLOW}${MODELS_JSON}${NC}"
    print_status "Client Models Discovery" "PASS"
else
    print_status "Client Models Discovery" "FAIL"
fi
echo ""

# 3. Test File Retrieval
echo -e "${BLUE}[3/4] Checking Files Fetch...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-User-ID: test-user" -H "X-User-Role: user" "${CLIENT_URL}/files" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    FILES_JSON=$(curl -s -H "X-User-ID: test-user" -H "X-User-Role: user" "${CLIENT_URL}/files")
    echo -e "  Files found: ${YELLOW}${FILES_JSON}${NC}"
    print_status "Files Retrieval" "PASS"
else
    print_status "Files Retrieval" "FAIL"
fi
echo ""

# 4. Test RBAC Security on Shared Uploads
echo -e "${BLUE}[4/4] Testing RBAC Security Policies (Shared Upload)...${NC}"

# Create temporary mock file to upload
MOCK_FILE="/tmp/rbac_test_doc.txt"
echo "Gemma 4 Ground Truth Security Test Document." > "$MOCK_FILE"

# A. Standard user attempting shared upload (MUST fail with 403)
echo -e "  A. Standard User ('X-User-Role: user') uploading shared file..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${CLIENT_URL}/upload" \
  -H "X-User-ID: standard-user" \
  -H "X-User-Role: user" \
  -F "file=@${MOCK_FILE}" \
  -F "is_shared=true" || echo "000")

if [ "$HTTP_CODE" = "403" ]; then
    echo -e "    Standard User blocked cleanly with ${GREEN}403 Forbidden${NC}."
    print_status "RBAC User Block" "PASS"
else
    echo -e "    ${RED}Fail: Standard User was not blocked (HTTP Code: ${HTTP_CODE})${NC}"
    print_status "RBAC User Block" "FAIL"
fi

# B. Admin user attempting shared upload (MUST succeed with 200)
echo -e "  B. Admin User ('X-User-Role: admin') uploading shared file..."
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "${CLIENT_URL}/upload" \
  -H "X-User-ID: admin-user" \
  -H "X-User-Role: admin" \
  -F "file=@${MOCK_FILE}" \
  -F "is_shared=true" || echo "000")

HTTP_BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
HTTP_CODE=$(echo "$RESPONSE" | grep -o 'HTTP_STATUS:[0-9]*' | cut -d: -f2)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "    Admin User successfully authorized with ${GREEN}200 OK${NC}."
    echo -e "    Response: ${YELLOW}${HTTP_BODY}${NC}"
    print_status "RBAC Admin Upload" "PASS"
else
    echo -e "    ${RED}Fail: Admin User was rejected (HTTP Code: ${HTTP_CODE})${NC}"
    print_status "RBAC Admin Upload" "FAIL"
fi

# Cleanup
rm -f "$MOCK_FILE"

echo -e "\n${GREEN}🎉 Zero-Dependency Client Smoke Test Successful! Client RBAC security is fully verified!${NC}"
exit 0
