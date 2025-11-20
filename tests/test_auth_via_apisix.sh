#!/bin/bash

# JWT Authentication Testing Script via APISIX Gateway
# Tests JWT token generation, verification, and user info extraction

# Use APISIX Gateway (Port 80) instead of direct service access
BASE_URL="http://localhost"
API_BASE="${BASE_URL}/api/v1/auth"

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

echo "======================================================================"
echo "JWT Authentication Service Tests (via APISIX Gateway)"
echo "======================================================================"
echo -e "${GREEN}Testing via: ${CYAN}${BASE_URL}${NC}"
echo -e "${GREEN}Gateway: ${CYAN}Apache APISIX${NC}"
echo ""

# Function to print test result
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}: $2"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}: $2"
        ((TESTS_FAILED++))
    fi
}

# Function to print section header
print_section() {
    echo ""
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""
}

# Test 1: Get Auth Service Info via APISIX
print_section "Test 1: Get Auth Service Info via APISIX"
echo "GET ${API_BASE}/info"
INFO_RESPONSE=$(curl -s -w "\n%{http_code}" "${API_BASE}/info")
HTTP_CODE=$(echo "$INFO_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$INFO_RESPONSE" | sed '$d')

echo "Response:"
echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    print_result 0 "Auth service info retrieved via APISIX"
else
    print_result 1 "Failed to get auth service info"
fi

# Test 2: Generate Development Token via APISIX
print_section "Test 2: Generate Development Token via APISIX"
echo "POST ${API_BASE}/dev-token"
DEV_TOKEN_PAYLOAD='{
  "user_id": "apisix_test_user_123",
  "email": "apisix-test@example.com",
  "expires_in": 3600
}'
echo "Request Body:"
echo "$DEV_TOKEN_PAYLOAD" | jq '.'

TOKEN_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/dev-token" \
  -H "Content-Type: application/json" \
  -d "$DEV_TOKEN_PAYLOAD")
HTTP_CODE=$(echo "$TOKEN_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$TOKEN_RESPONSE" | sed '$d')

echo "Response:"
echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
echo "HTTP Status: $HTTP_CODE"

JWT_TOKEN=""
if [ "$HTTP_CODE" = "200" ]; then
    JWT_TOKEN=$(echo "$RESPONSE_BODY" | jq -r '.token')
    if [ -n "$JWT_TOKEN" ] && [ "$JWT_TOKEN" != "null" ]; then
        print_result 0 "Development token generated via APISIX"
        echo -e "${YELLOW}Token (first 50 chars): ${JWT_TOKEN:0:50}...${NC}"
    else
        print_result 1 "Token generation returned success but no token found"
    fi
else
    print_result 1 "Failed to generate development token via APISIX"
fi

# Test 3: Verify JWT Token via APISIX (with provider=local)
if [ -n "$JWT_TOKEN" ] && [ "$JWT_TOKEN" != "null" ]; then
    print_section "Test 3: Verify JWT Token via APISIX (provider=local)"
    echo "POST ${API_BASE}/verify-token"
    VERIFY_PAYLOAD="{
  \"token\": \"$JWT_TOKEN\",
  \"provider\": \"local\"
}"
    echo "Request Body:"
    echo "$VERIFY_PAYLOAD" | jq '.'

    VERIFY_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/verify-token" \
      -H "Content-Type: application/json" \
      -d "$VERIFY_PAYLOAD")
    HTTP_CODE=$(echo "$VERIFY_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$VERIFY_RESPONSE" | sed '$d')

    echo "Response:"
    echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
    echo "HTTP Status: $HTTP_CODE"

    IS_VALID=$(echo "$RESPONSE_BODY" | jq -r '.valid')
    if [ "$HTTP_CODE" = "200" ] && [ "$IS_VALID" = "true" ]; then
        print_result 0 "JWT token verified via APISIX"
    else
        print_result 1 "JWT token verification via APISIX failed"
    fi
else
    echo -e "${YELLOW}Skipping Test 3: No token available${NC}"
    ((TESTS_FAILED++))
fi

# Test 4: Get User Info from Token via APISIX
if [ -n "$JWT_TOKEN" ] && [ "$JWT_TOKEN" != "null" ]; then
    print_section "Test 4: Get User Info from Token via APISIX"
    echo "GET ${API_BASE}/user-info?token=..."

    USER_INFO_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${API_BASE}/user-info?token=${JWT_TOKEN}")
    HTTP_CODE=$(echo "$USER_INFO_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$USER_INFO_RESPONSE" | sed '$d')

    echo "Response:"
    echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
    echo "HTTP Status: $HTTP_CODE"

    if [ "$HTTP_CODE" = "200" ]; then
        USER_ID=$(echo "$RESPONSE_BODY" | jq -r '.user_id')
        EMAIL=$(echo "$RESPONSE_BODY" | jq -r '.email')
        if [ -n "$USER_ID" ] && [ "$USER_ID" != "null" ]; then
            print_result 0 "User info extracted via APISIX"
            echo -e "${YELLOW}User ID: $USER_ID${NC}"
            echo -e "${YELLOW}Email: $EMAIL${NC}"
        else
            print_result 1 "User info extraction returned 200 but no user_id"
        fi
    else
        print_result 1 "Failed to extract user info via APISIX"
    fi
else
    echo -e "${YELLOW}Skipping Test 4: No token available${NC}"
    ((TESTS_FAILED++))
fi

# Test 5: Generate Token Pair via APISIX
print_section "Test 5: Generate Token Pair via APISIX (Access + Refresh)"
echo "POST ${API_BASE}/token-pair"
TOKEN_PAIR_PAYLOAD='{
  "user_id": "apisix_pair_user_789",
  "email": "apisix-pair@example.com",
  "organization_id": "org_apisix_123",
  "permissions": ["read:data", "write:data"],
  "metadata": {
    "role": "admin",
    "department": "engineering",
    "gateway": "apisix"
  }
}'
echo "Request Body:"
echo "$TOKEN_PAIR_PAYLOAD" | jq '.'

PAIR_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/token-pair" \
  -H "Content-Type: application/json" \
  -d "$TOKEN_PAIR_PAYLOAD")
HTTP_CODE=$(echo "$PAIR_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$PAIR_RESPONSE" | sed '$d')

echo "Response:"
echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
echo "HTTP Status: $HTTP_CODE"

ACCESS_TOKEN=""
REFRESH_TOKEN=""
if [ "$HTTP_CODE" = "200" ]; then
    ACCESS_TOKEN=$(echo "$RESPONSE_BODY" | jq -r '.access_token')
    REFRESH_TOKEN=$(echo "$RESPONSE_BODY" | jq -r '.refresh_token')
    if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ] && [ -n "$REFRESH_TOKEN" ] && [ "$REFRESH_TOKEN" != "null" ]; then
        print_result 0 "Token pair generated via APISIX"
        echo -e "${YELLOW}Access Token (first 50 chars): ${ACCESS_TOKEN:0:50}...${NC}"
        echo -e "${YELLOW}Refresh Token (first 50 chars): ${REFRESH_TOKEN:0:50}...${NC}"
    else
        print_result 1 "Token pair generation returned success but tokens missing"
    fi
else
    print_result 1 "Failed to generate token pair via APISIX"
fi

# Test 6: Verify Custom JWT Access Token via APISIX
if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
    print_section "Test 6: Verify Custom JWT Access Token via APISIX"
    echo "POST ${API_BASE}/verify-token"
    VERIFY_CUSTOM_PAYLOAD="{
  \"token\": \"$ACCESS_TOKEN\"
}"
    echo "Request Body:"
    echo "$VERIFY_CUSTOM_PAYLOAD" | jq '.'

    VERIFY_CUSTOM_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/verify-token" \
      -H "Content-Type: application/json" \
      -d "$VERIFY_CUSTOM_PAYLOAD")
    HTTP_CODE=$(echo "$VERIFY_CUSTOM_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$VERIFY_CUSTOM_RESPONSE" | sed '$d')

    echo "Response:"
    echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
    echo "HTTP Status: $HTTP_CODE"

    IS_VALID=$(echo "$RESPONSE_BODY" | jq -r '.valid')
    PROVIDER=$(echo "$RESPONSE_BODY" | jq -r '.provider')
    if [ "$HTTP_CODE" = "200" ] && [ "$IS_VALID" = "true" ]; then
        print_result 0 "Custom JWT access token verified via APISIX (Provider: $PROVIDER)"
        # Check for custom claims
        ORG_ID=$(echo "$RESPONSE_BODY" | jq -r '.organization_id')
        PERMS=$(echo "$RESPONSE_BODY" | jq -r '.permissions')
        echo -e "${YELLOW}Organization ID: $ORG_ID${NC}"
        echo -e "${YELLOW}Permissions: $PERMS${NC}"
    else
        print_result 1 "Custom JWT access token verification via APISIX failed"
    fi
else
    echo -e "${YELLOW}Skipping Test 6: No access token available${NC}"
    ((TESTS_FAILED++))
fi

# Test 7: Refresh Access Token via APISIX
if [ -n "$REFRESH_TOKEN" ] && [ "$REFRESH_TOKEN" != "null" ]; then
    print_section "Test 7: Refresh Access Token via APISIX"
    echo "POST ${API_BASE}/refresh"
    REFRESH_PAYLOAD="{
  \"refresh_token\": \"$REFRESH_TOKEN\"
}"
    echo "Request Body:"
    echo "$REFRESH_PAYLOAD" | jq '.'

    REFRESH_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/refresh" \
      -H "Content-Type: application/json" \
      -d "$REFRESH_PAYLOAD")
    HTTP_CODE=$(echo "$REFRESH_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$REFRESH_RESPONSE" | sed '$d')

    echo "Response:"
    echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
    echo "HTTP Status: $HTTP_CODE"

    NEW_ACCESS_TOKEN=""
    if [ "$HTTP_CODE" = "200" ]; then
        NEW_ACCESS_TOKEN=$(echo "$RESPONSE_BODY" | jq -r '.access_token')
        if [ -n "$NEW_ACCESS_TOKEN" ] && [ "$NEW_ACCESS_TOKEN" != "null" ]; then
            print_result 0 "Access token refreshed via APISIX"
            echo -e "${YELLOW}New Access Token (first 50 chars): ${NEW_ACCESS_TOKEN:0:50}...${NC}"
        else
            print_result 1 "Token refresh returned success but no new token"
        fi
    else
        print_result 1 "Failed to refresh access token via APISIX"
    fi
else
    echo -e "${YELLOW}Skipping Test 7: No refresh token available${NC}"
    ((TESTS_FAILED++))
fi

# Test 8: Get Auth Stats via APISIX
print_section "Test 8: Get Auth Service Statistics via APISIX"
echo "GET ${API_BASE}/stats"
STATS_RESPONSE=$(curl -s -w "\n%{http_code}" "${API_BASE}/stats")
HTTP_CODE=$(echo "$STATS_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$STATS_RESPONSE" | sed '$d')

echo "Response:"
echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    print_result 0 "Auth service statistics retrieved via APISIX"
else
    print_result 1 "Failed to get auth service statistics via APISIX"
fi

# Summary
echo ""
echo "======================================================================"
echo -e "${BLUE}Test Summary (via APISIX Gateway)${NC}"
echo "======================================================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
TOTAL=$((TESTS_PASSED + TESTS_FAILED))
echo "Total: $TOTAL"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All auth tests via APISIX passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please review the output above.${NC}"
    exit 1
fi
