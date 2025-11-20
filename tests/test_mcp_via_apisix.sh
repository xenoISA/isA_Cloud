#!/bin/bash
# MCP Service Test Suite via APISIX Gateway

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config - Using APISIX Gateway with base path /api/v1/mcp
# MCP service exposes endpoints at /mcp, /health, /search, etc.
# APISIX routes /api/v1/mcp/* and rewrites to /* (so /api/v1/mcp/mcp -> /mcp)
APISIX_URL="${APISIX_URL:-http://localhost}"
MCP_BASE_PATH="/api/v1/mcp"
MCP_URL="${APISIX_URL}${MCP_BASE_PATH}"
VERBOSE="${VERBOSE:-false}"
TESTS_PASSED=0
TESTS_FAILED=0

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    ((TESTS_PASSED++))
}

print_fail() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    ((TESTS_FAILED++))
}

print_debug() {
    echo -e "${YELLOW}[DEBUG]${NC} $1"
}

show_request_response() {
    local test_name="$1"
    local request="$2"
    local response="$3"

    echo -e "${YELLOW}┌─────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│ 📋 $test_name${NC}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────┘${NC}"
    echo -e "${YELLOW}📤 REQUEST:${NC}"
    echo "$request" | jq -C '.' 2>/dev/null || echo "$request"
    echo -e "\n${YELLOW}📥 RESPONSE:${NC}"
    echo "$response" | jq -C '.' 2>/dev/null || echo "$response"
    echo ""
}

echo "======================================================================"
echo "MCP Server Tests via APISIX Gateway"
echo "APISIX URL: $APISIX_URL"
echo "MCP Base Path: $MCP_BASE_PATH"
echo "Full MCP URL: $MCP_URL"
echo "======================================================================"

# ============================================
# Test 1: Health Check
# ============================================
print_header "Test 1: Health Check"

REQUEST_URL="$MCP_URL/health"
HEALTH=$(curl -s "$REQUEST_URL")
STATUS=$(echo "$HEALTH" | jq -r '.status' 2>/dev/null)
TOOLS=$(echo "$HEALTH" | jq -r '.capabilities.tools' 2>/dev/null)

show_request_response "Health Check" "GET $REQUEST_URL" "$HEALTH"

if [ -n "$STATUS" ] && [ "$TOOLS" -gt 0 ]; then
    print_success "Health check - $TOOLS tools registered"
else
    print_fail "Health check failed"
fi

# ============================================
# Test 2: Tools List
# ============================================
print_header "Test 2: MCP Tools/List"

REQUEST_PAYLOAD='{"jsonrpc":"2.0","method":"tools/list","id":1}'
TOOLS_RESP=$(curl -s -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "$REQUEST_PAYLOAD")

TOOLS_DATA=$(echo "$TOOLS_RESP" | grep "^data: " | sed 's/^data: //')
TOOL_COUNT=$(echo "$TOOLS_DATA" | jq -r '.result.tools | length' 2>/dev/null)

show_request_response "Tools List" "$REQUEST_PAYLOAD" "$TOOLS_DATA"

if [ "$TOOL_COUNT" -gt 0 ]; then
    print_success "Tools list - Found $TOOL_COUNT tools"
else
    print_fail "Tools list - No tools found"
fi

# ============================================
# Test 3: Call a Tool
# ============================================
print_header "Test 3: Call get_weather Tool"

REQUEST_PAYLOAD='{"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":"get_weather","arguments":{"city":"Tokyo"}}}'
CALL_RESP=$(curl -s -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "$REQUEST_PAYLOAD")

CALL_DATA=$(echo "$CALL_RESP" | grep "^data: " | sed 's/^data: //')
HAS_RESULT=$(echo "$CALL_DATA" | jq -r '.result' 2>/dev/null)

show_request_response "Call get_weather" "$REQUEST_PAYLOAD" "$CALL_DATA"

if [ "$HAS_RESULT" != "null" ] && [ -n "$HAS_RESULT" ]; then
    print_success "Call tool - get_weather executed successfully"
else
    print_fail "Call tool - get_weather failed"
fi

# ============================================
# Test 4: Prompts List
# ============================================
print_header "Test 4: MCP Prompts/List"

REQUEST_PAYLOAD='{"jsonrpc":"2.0","method":"prompts/list","id":1}'
PROMPTS_RESP=$(curl -s -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "$REQUEST_PAYLOAD")

PROMPTS_DATA=$(echo "$PROMPTS_RESP" | grep "^data: " | sed 's/^data: //')
PROMPT_COUNT=$(echo "$PROMPTS_DATA" | jq -r '.result.prompts | length' 2>/dev/null)

show_request_response "Prompts List" "$REQUEST_PAYLOAD" "$PROMPTS_DATA"

if [ "$PROMPT_COUNT" -gt 0 ]; then
    print_success "Prompts list - Found $PROMPT_COUNT prompts"
else
    print_fail "Prompts list - No prompts found"
fi

# ============================================
# Test 5: Get a Prompt
# ============================================
print_header "Test 5: Get intelligent_rag_search_prompt"

REQUEST_PAYLOAD='{"jsonrpc":"2.0","method":"prompts/get","id":1,"params":{"name":"intelligent_rag_search_prompt","arguments":{"query":"test query"}}}'
GET_PROMPT_RESP=$(curl -s -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "$REQUEST_PAYLOAD")

PROMPT_DATA=$(echo "$GET_PROMPT_RESP" | grep "^data: " | sed 's/^data: //')
HAS_MESSAGES=$(echo "$PROMPT_DATA" | jq -r '.result.messages' 2>/dev/null)

show_request_response "Get Prompt" "$REQUEST_PAYLOAD" "$PROMPT_DATA"

if [ "$HAS_MESSAGES" != "null" ] && [ -n "$HAS_MESSAGES" ]; then
    print_success "Get prompt - Retrieved successfully"
else
    print_fail "Get prompt - Failed"
fi

# ============================================
# Test 6: Resources List
# ============================================
print_header "Test 6: MCP Resources/List"

REQUEST_PAYLOAD='{"jsonrpc":"2.0","method":"resources/list","id":1}'
RESOURCES_RESP=$(curl -s -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "$REQUEST_PAYLOAD")

RESOURCES_DATA=$(echo "$RESOURCES_RESP" | grep "^data: " | sed 's/^data: //')
RESOURCE_COUNT=$(echo "$RESOURCES_DATA" | jq -r '.result.resources | length' 2>/dev/null)

show_request_response "Resources List" "$REQUEST_PAYLOAD" "$RESOURCES_DATA"

if [ "$RESOURCE_COUNT" -gt 0 ]; then
    print_success "Resources list - Found $RESOURCE_COUNT resources"
else
    print_fail "Resources list - No resources found"
fi

# ============================================
# Test 7: Search Service - Tool Search
# ============================================
print_header "Test 7: Search Service - Search for 'calculator'"

REQUEST_PAYLOAD='{"query":"calculator","type":"tool","limit":5,"score_threshold":0.3}'
SEARCH_RESP=$(curl -s -X POST "$MCP_URL/search" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

SEARCH_COUNT=$(echo "$SEARCH_RESP" | jq -r '.count' 2>/dev/null)
TOP_SCORE=$(echo "$SEARCH_RESP" | jq -r '.results[0].score' 2>/dev/null)
TOP_NAME=$(echo "$SEARCH_RESP" | jq -r '.results[0].name' 2>/dev/null)

show_request_response "Search Service (calculator)" "$REQUEST_PAYLOAD" "$SEARCH_RESP"

if [ "$SEARCH_COUNT" -gt 0 ] && [ "$TOP_NAME" = "calculator" ]; then
    print_success "Search Service - Found calculator with score $TOP_SCORE"
else
    print_fail "Search Service - Calculator not found"
fi

# ============================================
# Test 8: Search Service - Data Analysis Tools
# ============================================
print_header "Test 8: Search Service - Search for 'analyze data'"

REQUEST_PAYLOAD='{"query":"analyze data","type":"tool","limit":3,"score_threshold":0.3}'
SEARCH_RESP=$(curl -s -X POST "$MCP_URL/search" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

SEARCH_COUNT=$(echo "$SEARCH_RESP" | jq -r '.count' 2>/dev/null)
RESULTS_TEXT=$(echo "$SEARCH_RESP" | jq -r '.results[].name' 2>/dev/null | tr '\n' ' ')

show_request_response "Search Data Analysis Tools" "$REQUEST_PAYLOAD" "$SEARCH_RESP"

if [ "$SEARCH_COUNT" -gt 0 ]; then
    print_success "Search Service - Found $SEARCH_COUNT analysis tools: $RESULTS_TEXT"
else
    print_fail "Search Service - No analysis tools found"
fi

# ============================================
# Test 9: Search Service - Web Search Tools
# ============================================
print_header "Test 9: Search Service - Search for 'web search'"

REQUEST_PAYLOAD='{"query":"web search","type":"tool","limit":3,"score_threshold":0.3}'
SEMANTIC_RESP=$(curl -s -X POST "$MCP_URL/search" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

SEARCH_COUNT=$(echo "$SEMANTIC_RESP" | jq -r '.count' 2>/dev/null)
TOP_SCORE=$(echo "$SEMANTIC_RESP" | jq -r '.results[0].score' 2>/dev/null)
TOP_NAME=$(echo "$SEMANTIC_RESP" | jq -r '.results[0].name' 2>/dev/null)

show_request_response "Search Web Tools" "$REQUEST_PAYLOAD" "$SEMANTIC_RESP"

if [ "$SEARCH_COUNT" -gt 0 ]; then
    print_success "Search Service - Found $SEARCH_COUNT web tools, top: $TOP_NAME ($TOP_SCORE)"
else
    print_fail "Search Service - No web search tools found"
fi

# ============================================
# Test 10: Search Service - All Types
# ============================================
print_header "Test 10: Search Service - Search All Types"

REQUEST_PAYLOAD='{"query":"knowledge","limit":5,"score_threshold":0.2}'
ALL_SEARCH_RESP=$(curl -s -X POST "$MCP_URL/search" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

ALL_RESULTS=$(echo "$ALL_SEARCH_RESP" | jq -r '.results' 2>/dev/null)
TOOLS_FOUND=$(echo "$ALL_RESULTS" | jq -r '[.[] | select(.type == "tool")] | length' 2>/dev/null)
PROMPTS_FOUND=$(echo "$ALL_RESULTS" | jq -r '[.[] | select(.type == "prompt")] | length' 2>/dev/null)
RESOURCES_FOUND=$(echo "$ALL_RESULTS" | jq -r '[.[] | select(.type == "resource")] | length' 2>/dev/null)

show_request_response "Search All Types" "$REQUEST_PAYLOAD" "$ALL_SEARCH_RESP"

TOTAL_FOUND=$((TOOLS_FOUND + PROMPTS_FOUND + RESOURCES_FOUND))
if [ "$TOTAL_FOUND" -gt 0 ]; then
    print_success "Search All Types - Found $TOOLS_FOUND tools, $PROMPTS_FOUND prompts, $RESOURCES_FOUND resources"
else
    print_fail "Search All Types - No results found"
fi

# ============================================
# Summary
# ============================================
print_header "Test Summary"

TOTAL=$((TESTS_PASSED + TESTS_FAILED))
echo -e "${BLUE}Total Tests:${NC} $TOTAL"
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}🎉 All tests passed!${NC}\n"
    exit 0
else
    echo -e "\n${RED}❌ Some tests failed${NC}\n"
    exit 1
fi
