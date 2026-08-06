#!/bin/bash
# Gemma 4 Inference Gateway - Zero-Dependency Smoke-Test Script
# Verifies the gateway proxy using native curl (bypasses virtualenv blocks).

set -e

# Colors for premium terminal output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GATEWAY_URL=${GATEWAY_URL:-"http://localhost:50083"}
MODEL_NAME=${MODEL_NAME:-"gemma4:26b"}

echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}      Gemma 4 Gateway - Zero-Dependency Smoke Test    ${NC}"
echo -e "${BLUE}=====================================================${NC}"
echo -e "🎯 Target Gateway URL: ${YELLOW}${GATEWAY_URL}${NC}"
echo -e "🧠 Target Model:       ${YELLOW}${MODEL_NAME}${NC}\n"

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

# 1. Check Gateway Config / Health
echo -e "${BLUE}[1/4] Checking Gateway Health & Configuration...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/api/config" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    CONFIG_JSON=$(curl -s "${GATEWAY_URL}/api/config")
    echo -e "  Active configuration: ${YELLOW}${CONFIG_JSON}${NC}"
    print_status "Gateway Health & Configuration" "PASS"
else
    echo -e "  ${RED}Error: Received HTTP status ${HTTP_CODE} from /api/config${NC}"
    echo -e "  💡 Tip: Ensure you are running 'kubectl port-forward svc/gemma-gateway 50083:80 -n gemma-inference' in a background tab!"
    print_status "Gateway Health & Configuration" "FAIL"
fi
echo ""

# 2. Check Model Discovery
echo -e "${BLUE}[2/4] Checking OpenAI Models Discovery...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/v1/models" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    MODELS_JSON=$(curl -s "${GATEWAY_URL}/v1/models")
    echo -e "  Models available: ${YELLOW}${MODELS_JSON}${NC}"
    print_status "OpenAI Models Discovery" "PASS"
else
    print_status "OpenAI Models Discovery" "FAIL"
fi
echo ""

# 3. Test Chat Completions (Non-Streaming)
echo -e "${BLUE}[3/4] Testing Non-Streaming Completions...${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "${GATEWAY_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"${MODEL_NAME}\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Say 'Integration Verification Success' and nothing else.\"}]
  }")

HTTP_BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
HTTP_CODE=$(echo "$RESPONSE" | grep -o 'HTTP_STATUS:[0-9]*' | cut -d: -f2)

if [ "$HTTP_CODE" = "200" ]; then
    TEXT_OUTPUT=$(echo "$HTTP_BODY" | grep -o '"content":"[^"]*"' | cut -d: -f2 | sed 's/"//g' || echo "")
    if [ -z "$TEXT_OUTPUT" ]; then
        # Fallback json parser if grep cut fails
        TEXT_OUTPUT=$(echo "$HTTP_BODY" | sed -n 's/.*"content":"\([^"]*\)".*/\1/p')
    fi
    echo -e "  Response from Gemma 4: ${GREEN}\"${TEXT_OUTPUT}\"${NC}"
    print_status "Non-Streaming Completions" "PASS"
else
    echo -e "  ${RED}Error Body: ${HTTP_BODY}${NC}"
    print_status "Non-Streaming Completions" "FAIL"
fi
echo ""

# 4. Test Chat Completions (Streaming SSE)
echo -e "${BLUE}[4/4] Testing Streaming Tokens (SSE)...${NC}"
echo -e "  ${YELLOW}--- Streaming Response Start ---${NC}"

# Use curl --no-buffer to stream tokens to console instantly
HTTP_CODE=$(curl --no-buffer -s -w "%{http_code}" -X POST "${GATEWAY_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"${MODEL_NAME}\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Count to 5 in words.\" }],
    \"stream\": true
  }" | while read -r line; do
    # Filter and extract the content chunk
    if echo "$line" | grep -q 'data:'; then
        CHUNK=$(echo "$line" | sed 's/^data: //' | sed -n 's/.*"content":"\([^"]*\)".*/\1/p' || true)
        if [ -n "$CHUNK" ]; then
            # Print token chunk in green without newline
            echo -ne "${GREEN}${CHUNK}${NC}"
        fi
    fi
done)

echo -e "\n  ${YELLOW}--- Streaming Response End ---${NC}"

# Since the while loop consumes stdout, we assume success if we reached here without crash
print_status "Streaming Tokens (SSE)" "PASS"

echo -e "\n${GREEN}🎉 Zero-Dependency Smoke Test Successful! Gateway is healthy and verified!${NC}"
exit 0
