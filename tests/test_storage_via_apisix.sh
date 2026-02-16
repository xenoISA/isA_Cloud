#!/bin/bash
# Storage Service - File Operations Test via APISIX Gateway
# Tests: Health, Upload, List, Get Info, Download, Delete

# Use APISIX Gateway (Port 80) instead of direct service access
BASE_URL="http://localhost"
API_BASE="${BASE_URL}/api/v1"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Test counters
PASSED=0
FAILED=0
TOTAL=0

# Test result function
test_result() {
    TOTAL=$((TOTAL + 1))
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗ FAILED${NC}"
        FAILED=$((FAILED + 1))
    fi
}

echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}   STORAGE SERVICE - FILE OPERATIONS TEST (via APISIX Gateway)${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo -e "${GREEN}Testing via: ${CYAN}${BASE_URL}${NC}"
echo -e "${GREEN}Gateway: ${CYAN}Apache APISIX${NC}"
echo ""

# Use test user from seed_test_data.sql
TEST_USER_ID="test_user_001"
echo -e "${GREEN}Using test user: ${CYAN}$TEST_USER_ID${NC}"
echo ""

# Test 1: Check MinIO Status (via APISIX)
echo -e "${YELLOW}Test 1: Check MinIO Connection Status via APISIX${NC}"
echo "GET /api/v1/storage/test/minio-status"
RESPONSE=$(curl -s "${API_BASE}/storage/test/minio-status")
echo "$RESPONSE" | python3 -m json.tool
if echo "$RESPONSE" | grep -q '"status":"connected"'; then
    test_result 0
else
    test_result 1
fi
echo ""

# Create a test file for upload
TEST_FILE="/tmp/storage_apisix_test_$(date +%s).txt"
echo "This is a test file via APISIX gateway." > "$TEST_FILE"
echo "Created at: $(date)" >> "$TEST_FILE"
echo "Gateway: APISIX" >> "$TEST_FILE"
echo "Test user: $TEST_USER_ID" >> "$TEST_FILE"

# Test 2: Upload File via APISIX
echo -e "${YELLOW}Test 2: Upload File via APISIX${NC}"
echo "POST /api/v1/storage/files/upload"
UPLOAD_RESPONSE=$(curl -s -X POST "${API_BASE}/storage/files/upload" \
  -F "file=@${TEST_FILE}" \
  -F "user_id=${TEST_USER_ID}" \
  -F "access_level=private" \
  -F "tags=apisix,gateway,test" \
  -F "enable_indexing=false" \
  -F "metadata={\"gateway\":\"apisix\",\"test\":true}")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

if echo "$UPLOAD_RESPONSE" | grep -q '"file_id"'; then
    FILE_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['file_id'])")
    echo -e "${GREEN}✓ File uploaded via APISIX: $FILE_ID${NC}"
    test_result 0
else
    echo -e "${RED}✗ Upload failed${NC}"
    test_result 1
    FILE_ID=""
fi
echo ""

# Test 3: List Files via APISIX
echo -e "${YELLOW}Test 3: List User Files via APISIX${NC}"
echo "GET /api/v1/storage/files?user_id=${TEST_USER_ID}"
RESPONSE=$(curl -s "${API_BASE}/storage/files?user_id=${TEST_USER_ID}&limit=10")
echo "$RESPONSE" | python3 -m json.tool | head -50
if echo "$RESPONSE" | grep -q '\['; then
    FILE_COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
    echo -e "${GREEN}✓ Found $FILE_COUNT files via APISIX${NC}"
    test_result 0
else
    test_result 1
fi
echo ""

# Test 4: Get File Info via APISIX
if [ -n "$FILE_ID" ]; then
    echo -e "${YELLOW}Test 4: Get File Information via APISIX${NC}"
    echo "GET /api/v1/storage/files/${FILE_ID}?user_id=${TEST_USER_ID}"
    RESPONSE=$(curl -s "${API_BASE}/storage/files/${FILE_ID}?user_id=${TEST_USER_ID}")
    echo "$RESPONSE" | python3 -m json.tool
    if echo "$RESPONSE" | grep -q '"file_id"'; then
        test_result 0
    else
        test_result 1
    fi
    echo ""
else
    echo -e "${YELLOW}Test 4: Get File Information - SKIPPED (no file_id)${NC}"
    echo ""
fi

# Test 5: Get Download URL via APISIX
if [ -n "$FILE_ID" ]; then
    echo -e "${YELLOW}Test 5: Get File Download URL via APISIX${NC}"
    echo "GET /api/v1/storage/files/${FILE_ID}/download?user_id=${TEST_USER_ID}"
    RESPONSE=$(curl -s "${API_BASE}/storage/files/${FILE_ID}/download?user_id=${TEST_USER_ID}")
    echo "$RESPONSE" | python3 -m json.tool
    if echo "$RESPONSE" | grep -q '"download_url"'; then
        DOWNLOAD_URL=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['download_url'])" 2>/dev/null || echo "")
        if [ -n "$DOWNLOAD_URL" ]; then
            echo -e "${GREEN}✓ Download URL obtained via APISIX${NC}"
            test_result 0
        else
            test_result 1
        fi
    else
        test_result 1
    fi
    echo ""
else
    echo -e "${YELLOW}Test 5: Get File Download URL - SKIPPED (no file_id)${NC}"
    echo ""
fi

# Test 6: Delete File via APISIX (Soft Delete)
if [ -n "$FILE_ID" ]; then
    echo -e "${YELLOW}Test 6: Delete File via APISIX (Soft Delete)${NC}"
    echo "DELETE /api/v1/storage/files/${FILE_ID}?user_id=${TEST_USER_ID}"
    RESPONSE=$(curl -s -X DELETE "${API_BASE}/storage/files/${FILE_ID}?user_id=${TEST_USER_ID}")
    echo "$RESPONSE" | python3 -m json.tool
    if echo "$RESPONSE" | grep -q "deleted successfully"; then
        test_result 0
    else
        test_result 1
    fi
    echo ""
else
    echo -e "${YELLOW}Test 6: Delete File - SKIPPED (no file_id)${NC}"
    echo ""
fi

# Cleanup
rm -f "$TEST_FILE"

# Print summary
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}                         TEST SUMMARY${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo -e "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL STORAGE TESTS VIA APISIX PASSED!${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    exit 1
fi
