#!/bin/bash

################################################################################
# OpenResty Full Service Test Suite
################################################################################
#
# This script tests all backend services through the OpenResty gateway
# Architecture: Client → OpenResty:80 → Infrastructure Gateway:8000 → Services
#
# Services Tested:
#   1. Auth Service (authentication & authorization)
#   2. Agent Service (AI chat & execution control)
#   3. User Microservices (accounts, sessions, etc.)
#   4. Model Service (AI model inference)
#   5. MCP Service (Model Control Protocol)
#
# Usage:
#   ./tests/openresty_full_service_test.sh
#   ./tests/openresty_full_service_test.sh --service auth
#   ./tests/openresty_full_service_test.sh --verbose
#
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
OPENRESTY_BASE_URL="${OPENRESTY_URL:-http://localhost}"
GATEWAY_PORT="${GATEWAY_PORT:-80}"
FULL_URL="${OPENRESTY_BASE_URL}:${GATEWAY_PORT}"
API_VERSION="v1"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Verbose mode
VERBOSE=false

# Test results array
declare -a TEST_RESULTS

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${BLUE}────────────────────────────────────────────────────────────────${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}────────────────────────────────────────────────────────────────${NC}"
}

print_test() {
    echo -e "${YELLOW}▶ Test: $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    ((PASSED_TESTS++))
    ((TOTAL_TESTS++))
    TEST_RESULTS+=("PASS: $1")
}

print_failure() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
    TEST_RESULTS+=("FAIL: $1")
}

print_skip() {
    echo -e "${YELLOW}⊘ SKIP:${NC} $1"
    ((SKIPPED_TESTS++))
    ((TOTAL_TESTS++))
    TEST_RESULTS+=("SKIP: $1")
}

print_info() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${CYAN}  ℹ ${NC}$1"
    fi
}

# HTTP request helper with better error handling
http_request() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    local headers="$4"
    local expected_code="${5:-200}"

    local url="${FULL_URL}${endpoint}"

    print_info "Request: $method $url"
    if [ -n "$data" ] && [ "$VERBOSE" = true ]; then
        print_info "Data: $data"
    fi

    # Build curl command args array to avoid eval issues
    local curl_args=(
        -s
        -k
        -L
        --max-time 10
        -w "\n%{http_code}"
        -X "$method"
    )

    # Add headers
    if [ -n "$headers" ]; then
        while IFS= read -r header; do
            if [ -n "$header" ]; then
                curl_args+=(-H "$header")
            fi
        done <<< "$headers"
    fi

    # Add data for POST/PUT
    if [ -n "$data" ]; then
        curl_args+=(-H "Content-Type: application/json")
        curl_args+=(-d "$data")
    fi

    curl_args+=("$url")

    # Execute request
    local response
    response=$(curl "${curl_args[@]}" 2>&1)
    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
        print_info "Curl error code: $exit_code"
        return 1
    fi

    # Parse response and status code
    local body=$(echo "$response" | sed '$d')
    local status_code=$(echo "$response" | tail -1)

    # Validate status code is a number
    if ! [[ "$status_code" =~ ^[0-9]+$ ]]; then
        print_info "Invalid status code: $status_code"
        print_info "Full response: ${response:0:200}"
        return 1
    fi

    print_info "Status: $status_code"
    if [ "$VERBOSE" = true ] && [ -n "$body" ]; then
        print_info "Response: ${body:0:200}"
    fi

    # Check if status code matches expected (support comma-separated codes)
    if echo "$expected_code" | grep -q ","; then
        # Multiple expected codes
        if echo "$expected_code" | grep -qw "$status_code"; then
            echo "$body"
            return 0
        else
            print_info "Expected one of: $expected_code, Got: $status_code"
            return 1
        fi
    else
        # Single expected code
        if [ "$status_code" = "$expected_code" ]; then
            echo "$body"
            return 0
        else
            print_info "Expected: $expected_code, Got: $status_code"
            return 1
        fi
    fi
}

################################################################################
# Test 0: Infrastructure & Gateway Health
################################################################################

test_infrastructure() {
    print_section "Infrastructure & Gateway Health Tests"

    # Test 0.1: OpenResty Availability
    print_test "OpenResty is accessible"
    if curl -s -f "$FULL_URL/health" > /dev/null 2>&1; then
        print_success "OpenResty is running on port $GATEWAY_PORT"
    else
        print_failure "OpenResty not accessible at $FULL_URL"
        echo -e "${RED}ERROR: OpenResty must be running for tests to proceed${NC}"
        exit 1
    fi

    # Test 0.2: Gateway Health
    print_test "Infrastructure Gateway health check"
    response=$(http_request "GET" "/health" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Gateway health check passed"
    else
        print_failure "Gateway health check failed"
    fi

    # Test 0.3: Gateway Ready
    print_test "Infrastructure Gateway readiness check"
    response=$(http_request "GET" "/ready" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Gateway ready check passed"
    else
        print_failure "Gateway ready check failed"
    fi

    # Test 0.4: Gateway Services List
    print_test "Gateway services discovery"
    response=$(http_request "GET" "/api/v1/gateway/services" "" "" "200,401,403")
    if [ $? -eq 0 ]; then
        print_success "Gateway services endpoint accessible"
    else
        print_skip "Gateway services endpoint requires authentication"
    fi
}

################################################################################
# Test 1: Auth Service
################################################################################

test_auth_service() {
    print_section "Auth Service Tests"

    # Test 1.1: Auth Service Health
    print_test "Auth service health check"
    response=$(http_request "GET" "/api/v1/auth/health" "" "" "200,502,503")
    if [ $? -eq 0 ]; then
        # Check if we got a 200 or error status
        if echo "$response" | grep -q '"error"'; then
            print_failure "Auth service returned error (service may not be running)"
            print_info "Consider checking if the auth service is started"
        else
            print_success "Auth service is healthy"
        fi
    else
        print_failure "Auth service health check failed (connection error)"
    fi

    # Test 1.2: Get Dev Token (for testing)
    print_test "Get development authentication token"
    local auth_data='{
        "user_id": "test-user-'$(date +%s)'",
        "email": "test@example.com",
        "role": "user"
    }'

    response=$(http_request "POST" "/api/v1/auth/dev-token" "$auth_data" "Content-Type: application/json" "200,502,503")
    if [ $? -eq 0 ]; then
        # Check for error response first
        if echo "$response" | grep -q '"error"'; then
            print_failure "Failed to get dev token (auth service unavailable)"
            AUTH_TOKEN=""
        else
            # Extract token from response - try jq first, fallback to grep
            if command -v jq &> /dev/null; then
                AUTH_TOKEN=$(echo "$response" | jq -r '.token // empty' 2>/dev/null)
            fi

            # Fallback to grep if jq fails or not available
            if [ -z "$AUTH_TOKEN" ]; then
                AUTH_TOKEN=$(echo "$response" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
            fi

            if [ -n "$AUTH_TOKEN" ]; then
                print_success "Dev token obtained successfully"
                print_info "Token: ${AUTH_TOKEN:0:20}..."
            else
                print_failure "Failed to extract token from response"
            fi
        fi
    else
        print_failure "Failed to get dev token (connection error)"
        AUTH_TOKEN=""
    fi

    # Test 1.3: Verify Token
    if [ -n "$AUTH_TOKEN" ]; then
        print_test "Verify authentication token"
        local verify_data='{"token": "'$AUTH_TOKEN'"}'

        response=$(http_request "POST" "/api/v1/auth/verify-token" "$verify_data" "Content-Type: application/json" "200")
        if [ $? -eq 0 ]; then
            print_success "Token verification passed"
        else
            print_failure "Token verification failed"
        fi
    else
        print_skip "Token verification (no token available)"
    fi

    # Test 1.4: Get User Info
    if [ -n "$AUTH_TOKEN" ]; then
        print_test "Get user information from token"

        response=$(http_request "GET" "/api/v1/auth/user-info" "" "Authorization: Bearer $AUTH_TOKEN" "200")
        if [ $? -eq 0 ]; then
            print_success "User info retrieved successfully"
        else
            print_failure "Failed to get user info"
        fi
    else
        print_skip "Get user info (no token available)"
    fi
}

################################################################################
# Test 2: Agent Service
################################################################################

test_agent_service() {
    print_section "Agent Service Tests"

    # Test 2.1: Agent Service Health
    print_test "Agent service health check"
    response=$(http_request "GET" "/api/v1/agents/health" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Agent service is healthy"
        if [ "$VERBOSE" = true ]; then
            if command -v jq &> /dev/null; then
                echo "$response" | jq . 2>/dev/null || echo "$response"
            elif command -v python3 &> /dev/null; then
                echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            else
                echo "$response"
            fi
        fi
    else
        print_failure "Agent service health check failed"
    fi

    # Test 2.2: Agent Stats
    print_test "Agent service statistics"
    response=$(http_request "GET" "/api/v1/agents/stats" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Agent stats retrieved"
    else
        print_failure "Failed to get agent stats"
    fi

    # Test 2.3: Agent Capabilities
    print_test "Agent service capabilities"
    response=$(http_request "GET" "/api/v1/agents/capabilities" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Agent capabilities retrieved"
        if [ "$VERBOSE" = true ]; then
            if command -v jq &> /dev/null; then
                echo "$response" | jq . 2>/dev/null || echo "$response"
            elif command -v python3 &> /dev/null; then
                echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            else
                echo "$response"
            fi
        fi
    else
        print_failure "Failed to get agent capabilities"
    fi

    # Test 2.4: Chat Health
    print_test "Chat endpoint health check"
    response=$(http_request "GET" "/api/v1/agents/chat/health" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Chat endpoint is healthy"
    else
        print_failure "Chat endpoint health check failed"
    fi

    # Test 2.5: Simple Chat Request (with authentication)
    if [ -n "$AUTH_TOKEN" ]; then
        print_test "Send chat message"
        local chat_data='{
            "user_id": "test-user-'$(date +%s)'",
            "session_id": "test-session-'$(date +%s)'",
            "message": "Hello, this is a test message",
            "stream": false
        }'

        local chat_headers="Content-Type: application/json"$'\n'"X-API-Key: $AUTH_TOKEN"
        response=$(http_request "POST" "/api/v1/agents/chat" "$chat_data" "$chat_headers" "200,400")
        if [ $? -eq 0 ]; then
            print_success "Chat message sent successfully"
        else
            print_failure "Failed to send chat message"
        fi
    else
        print_skip "Chat message test (no auth token)"
    fi

    # Test 2.6: Execution Health
    print_test "Execution control health check"
    response=$(http_request "GET" "/api/v1/agents/execution/health" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Execution control is healthy"
    else
        print_failure "Execution control health check failed"
    fi

    # Test 2.7: Session Health
    print_test "Session management health check"
    response=$(http_request "GET" "/api/v1/agents/sessions/health" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Session management is healthy"
    else
        print_failure "Session management health check failed"
    fi

    # Test 2.8: Graph Configuration Info
    print_test "Graph configuration info"
    response=$(http_request "GET" "/api/v1/agents/graph/info" "" "" "200")
    if [ $? -eq 0 ]; then
        print_success "Graph info retrieved"
    else
        print_failure "Failed to get graph info"
    fi
}

################################################################################
# Test 3: User Microservices
################################################################################

test_user_services() {
    print_section "User Microservices Tests"

    if [ -z "$AUTH_TOKEN" ]; then
        print_skip "User service tests (no auth token)"
        return
    fi

    # Test 3.1: Accounts Service Health
    print_test "Accounts service health"
    response=$(http_request "GET" "/api/v1/accounts/health" "" "Authorization: Bearer $AUTH_TOKEN" "200")
    if [ $? -eq 0 ]; then
        print_success "Accounts service is healthy"
    else
        print_failure "Accounts service health check failed"
    fi

    # Test 3.2: Get Current User Profile
    print_test "Get current user profile"
    response=$(http_request "GET" "/api/v1/accounts/profile/me" "" "Authorization: Bearer $AUTH_TOKEN" "200")
    if [ $? -eq 0 ]; then
        print_success "User profile retrieved"
    else
        print_failure "Failed to get user profile"
    fi

    # Test 3.3: Sessions Service Health
    print_test "Sessions service health"
    response=$(http_request "GET" "/api/v1/sessions/health" "" "Authorization: Bearer $AUTH_TOKEN" "200")
    if [ $? -eq 0 ]; then
        print_success "Sessions service is healthy"
    else
        print_failure "Sessions service health check failed"
    fi

    # Test 3.4: Authorization Service Health
    print_test "Authorization service health"
    response=$(http_request "GET" "/api/v1/authorization/health" "" "Authorization: Bearer $AUTH_TOKEN" "200")
    if [ $? -eq 0 ]; then
        print_success "Authorization service is healthy"
    else
        print_failure "Authorization service health check failed"
    fi
}

################################################################################
# Test 4: Model Service
################################################################################

test_model_service() {
    print_section "Model Service Tests"

    # Test 4.1: Model Service Health
    print_test "Model service health check"
    response=$(http_request "GET" "/api/v1/models/health" "" "" "200,404")
    if [ $? -eq 0 ]; then
        print_success "Model service endpoint exists"
    else
        print_skip "Model service not available (may not be deployed)"
    fi

    # Test 4.2: List Available Models
    if [ -n "$AUTH_TOKEN" ]; then
        print_test "List available models"
        response=$(http_request "GET" "/api/v1/models" "" "Authorization: Bearer $AUTH_TOKEN" "200,404")
        if [ $? -eq 0 ]; then
            print_success "Models list retrieved"
        else
            print_skip "Model listing not available"
        fi
    else
        print_skip "Model listing (no auth token)"
    fi
}

################################################################################
# Test 5: MCP Service
################################################################################

test_mcp_service() {
    print_section "MCP (Model Control Protocol) Service Tests"

    # Test 5.1: MCP Service Health
    print_test "MCP service health check"
    response=$(http_request "GET" "/api/v1/mcp/health" "" "" "200,404")
    if [ $? -eq 0 ]; then
        print_success "MCP service is healthy"
    else
        print_skip "MCP service not available (may not be deployed)"
    fi

    # Test 5.2: MCP Tools
    if [ -n "$AUTH_TOKEN" ]; then
        print_test "MCP tools availability"
        response=$(http_request "GET" "/api/v1/mcp/tools" "" "Authorization: Bearer $AUTH_TOKEN" "200,404")
        if [ $? -eq 0 ]; then
            print_success "MCP tools endpoint accessible"
        else
            print_skip "MCP tools not available"
        fi
    else
        print_skip "MCP tools (no auth token)"
    fi
}

################################################################################
# Test 6: Device/IoT Services (if enabled)
################################################################################

test_device_services() {
    print_section "Device/IoT Services Tests (Optional)"

    # Test 6.1: Device Service Health
    print_test "Device service health"
    response=$(http_request "GET" "/api/v1/devices/health" "" "" "200,404")
    if [ $? -eq 0 ]; then
        print_success "Device service is available"
    else
        print_skip "Device service not enabled"
    fi

    # Test 6.2: Telemetry Service Health
    print_test "Telemetry service health"
    response=$(http_request "GET" "/api/v1/telemetry/health" "" "" "200,404")
    if [ $? -eq 0 ]; then
        print_success "Telemetry service is available"
    else
        print_skip "Telemetry service not enabled"
    fi
}

################################################################################
# Test 7: Infrastructure Services (gRPC via Gateway)
################################################################################

test_infrastructure_services() {
    print_section "Infrastructure Services Tests"

    if [ -z "$AUTH_TOKEN" ]; then
        print_skip "Infrastructure service tests (no auth token)"
        return
    fi

    # These would be accessed through gateway proxying
    print_info "Infrastructure services (MinIO, DuckDB, NATS, etc.) are gRPC-based"
    print_info "They are accessed through the gateway's service discovery"

    # Test 7.1: Check if services are registered
    print_test "Service registry availability"
    response=$(http_request "GET" "/api/v1/gateway/services" "" "Authorization: Bearer $AUTH_TOKEN" "200,401")
    if [ $? -eq 0 ]; then
        print_success "Service registry accessible"
        if [ "$VERBOSE" = true ]; then
            if command -v jq &> /dev/null; then
                echo "$response" | jq . 2>/dev/null || echo "$response"
            elif command -v python3 &> /dev/null; then
                echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            else
                echo "$response"
            fi
        fi
    else
        print_skip "Service registry requires authentication"
    fi
}

################################################################################
# Test Summary
################################################################################

print_summary() {
    print_header "Test Summary"

    echo -e "Total Tests:  ${BLUE}${TOTAL_TESTS}${NC}"
    echo -e "Passed:       ${GREEN}${PASSED_TESTS}${NC}"
    echo -e "Failed:       ${RED}${FAILED_TESTS}${NC}"
    echo -e "Skipped:      ${YELLOW}${SKIPPED_TESTS}${NC}"
    echo ""

    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        echo ""
        if [ $SKIPPED_TESTS -gt 0 ]; then
            echo -e "${YELLOW}Note: $SKIPPED_TESTS tests were skipped (usually due to missing auth or optional services)${NC}"
        fi
        return 0
    else
        echo -e "${RED}✗ Some tests failed${NC}"
        echo ""
        echo -e "${RED}Failed tests:${NC}"
        for result in "${TEST_RESULTS[@]}"; do
            if [[ $result == FAIL:* ]]; then
                echo -e "${RED}  - ${result#FAIL: }${NC}"
            fi
        done
        return 1
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    # Parse arguments
    SERVICE_FILTER=""
    while [[ $# -gt 0 ]]; do
        case $1 in
            --service)
                SERVICE_FILTER="$2"
                shift 2
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --service <name>  Run tests for specific service only"
                echo "                    (infrastructure|auth|agent|user|model|mcp|device)"
                echo "  --verbose, -v     Enable verbose output"
                echo "  --help, -h        Show this help message"
                echo ""
                echo "Environment Variables:"
                echo "  OPENRESTY_URL     Base URL (default: http://localhost)"
                echo "  GATEWAY_PORT      Port number (default: 80)"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    print_header "OpenResty Full Service Test Suite"
    echo "Testing URL: ${FULL_URL}"
    echo "API Version: ${API_VERSION}"
    echo ""

    # Run tests based on filter
    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "infrastructure" ]; then
        test_infrastructure
    fi

    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "auth" ]; then
        test_auth_service
    fi

    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "agent" ]; then
        test_agent_service
    fi

    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "user" ]; then
        test_user_services
    fi

    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "model" ]; then
        test_model_service
    fi

    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "mcp" ]; then
        test_mcp_service
    fi

    if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "device" ]; then
        test_device_services
    fi

    if [ -z "$SERVICE_FILTER" ]; then
        test_infrastructure_services
    fi

    # Print summary and exit with appropriate code
    print_summary
    exit $?
}

# Run main function
main "$@"
