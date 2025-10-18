#!/bin/bash

# ============================================
# MinIO Service - Comprehensive Functional Tests
# ============================================
# Tests all MinIO operations including:
# - Bucket management (create, list, delete, policies, tags)
# - Object operations (upload, download, copy, delete)
# - Metadata and tags
# - Presigned URLs
# - Versioning
# - Lifecycle policies

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50051}"
USER_ID="${USER_ID:-test-user}"  # DNS-compliant: no underscores
TEST_BUCKET="${USER_ID}-test-bucket"
TEST_PREFIX="functional-test"

# Counters
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

# Cleanup function
cleanup() {
    echo ""
    echo -e "${CYAN}Cleaning up test resources...${NC}"
    python3 <<EOF 2>/dev/null
from isa_common.minio_client import MinIOClient
client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        # Disable versioning first to allow deletion
        try:
            client.set_bucket_versioning('${TEST_BUCKET}', False)
        except:
            pass
        # Force delete bucket (includes all objects)
        client.delete_bucket('${TEST_BUCKET}', force=True)
except Exception:
    pass
EOF
}

# ========================================
# Test Functions
# ========================================

test_service_health() {
    echo -e "${YELLOW}Test 1: Service Health Check${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        health = client.health_check()
        if health and health.get('healthy'):
            print("PASS")
        else:
            print("FAIL")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
        echo -e "${RED}Cannot proceed without healthy service${NC}"
        exit 1
    fi
}

test_bucket_create_delete() {
    echo -e "${YELLOW}Test 2: Bucket Create/Delete Lifecycle${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Cleanup first (force delete to remove any leftover objects)
        try:
            client.delete_bucket('${TEST_BUCKET}', force=True)
        except:
            pass

        # Create bucket
        result = client.create_bucket('${TEST_BUCKET}')
        if not result or not result.get('success'):
            print("FAIL: Create bucket failed")
        elif not client.bucket_exists('${TEST_BUCKET}'):
            print("FAIL: Bucket should exist")
        else:
            buckets = client.list_buckets()
            # Check if bucket exists in list (may have user prefix)
            bucket_found = any('${TEST_BUCKET}' in bucket for bucket in buckets)
            if not bucket_found:
                print(f"FAIL: Bucket not in list. Available: {buckets}")
            else:
                info = client.get_bucket_info('${TEST_BUCKET}')
                if not info:
                    print("FAIL: Could not get bucket info")
                elif '${TEST_BUCKET}' not in info.get('name', ''):
                    print(f"FAIL: Bucket name mismatch. Expected '${TEST_BUCKET}' in '{info.get('name')}'")
                else:
                    print("PASS: Bucket created successfully")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_bucket_policies() {
    echo -e "${YELLOW}Test 3: Bucket Policy Management${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import json
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::${TEST_BUCKET}/*"]
            }]
        }

        if not client.set_bucket_policy('${TEST_BUCKET}', json.dumps(policy)):
            print("FAIL: Set policy failed")
        elif not client.get_bucket_policy('${TEST_BUCKET}'):
            print("FAIL: Get policy failed")
        elif not client.delete_bucket_policy('${TEST_BUCKET}'):
            print("FAIL: Delete policy failed")
        else:
            print("PASS: Policy management successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_bucket_tags() {
    echo -e "${YELLOW}Test 4: Bucket Tagging${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        tags = {"Environment": "test", "Project": "isA-Platform"}

        if not client.set_bucket_tags('${TEST_BUCKET}', tags):
            print("FAIL: Set tags failed")
        else:
            retrieved = client.get_bucket_tags('${TEST_BUCKET}')
            if not retrieved or retrieved.get('Environment') != 'test':
                print("FAIL: Get tags failed")
            elif not client.delete_bucket_tags('${TEST_BUCKET}'):
                print("FAIL: Delete tags failed")
            else:
                print("PASS: Bucket tagging successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_object_upload_download() {
    echo -e "${YELLOW}Test 5: Object Upload/Download${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        object_name = '${TEST_PREFIX}/test-file.txt'
        content = b'Hello, MinIO! This is a test file.'

        if not client.put_object('${TEST_BUCKET}', object_name, io.BytesIO(content), len(content)):
            print("FAIL: Upload failed")
        else:
            data = client.get_object('${TEST_BUCKET}', object_name)
            if data != content:
                print("FAIL: Content mismatch")
            else:
                metadata = client.get_object_metadata('${TEST_BUCKET}', object_name)
                if not metadata or metadata['size'] != len(content):
                    print("FAIL: Metadata incorrect")
                else:
                    print("PASS: Upload/download successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_object_from_file() {
    echo -e "${YELLOW}Test 6: Object Upload from File${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import os
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        temp_file = '/tmp/test-upload.txt'
        test_content = 'File upload test content'

        with open(temp_file, 'w') as f:
            f.write(test_content)

        object_name = '${TEST_PREFIX}/uploaded-file.txt'

        if not client.upload_file('${TEST_BUCKET}', object_name, temp_file):
            os.remove(temp_file)
            print("FAIL: Upload from file failed")
        else:
            data = client.get_object('${TEST_BUCKET}', object_name)
            os.remove(temp_file)
            if data.decode('utf-8') != test_content:
                print("FAIL: Content mismatch")
            else:
                print("PASS: File upload successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_object_copy() {
    echo -e "${YELLOW}Test 7: Object Copy Operation${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        source = '${TEST_PREFIX}/source.txt'
        dest = '${TEST_PREFIX}/destination.txt'
        content = b'Content to copy'

        client.put_object('${TEST_BUCKET}', source, io.BytesIO(content), len(content))

        if not client.copy_object('${TEST_BUCKET}', dest, '${TEST_BUCKET}', source):
            print("FAIL: Copy failed")
        else:
            dest_data = client.get_object('${TEST_BUCKET}', dest)
            if dest_data != content:
                print("FAIL: Copied content mismatch")
            else:
                print("PASS: Copy operation successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_object_list_delete() {
    echo -e "${YELLOW}Test 8: Object List/Delete Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        objects = []
        prefix = '${TEST_PREFIX}/list-test/'

        # Upload 5 objects
        for i in range(5):
            obj = f'{prefix}file-{i}.txt'
            content = f'Content {i}'.encode()
            client.put_object('${TEST_BUCKET}', obj, io.BytesIO(content), len(content))
            objects.append(obj)

        listed = client.list_objects('${TEST_BUCKET}', prefix=prefix)
        if len(listed) != 5:
            print(f"FAIL: Expected 5 objects, got {len(listed)}")
        elif not client.delete_object('${TEST_BUCKET}', objects[0]):
            print("FAIL: Delete single failed")
        else:
            listed = client.list_objects('${TEST_BUCKET}', prefix=prefix)
            if len(listed) != 4:
                print("FAIL: Object not deleted")
            elif not client.delete_objects('${TEST_BUCKET}', objects[1:]):
                print("FAIL: Delete multiple failed")
            else:
                listed = client.list_objects('${TEST_BUCKET}', prefix=prefix)
                if len(listed) != 0:
                    print("FAIL: Not all objects deleted")
                else:
                    print("PASS: List/delete operations successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_presigned_urls() {
    echo -e "${YELLOW}Test 9: Presigned URL Generation${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        object_name = '${TEST_PREFIX}/presigned-test.txt'
        content = b'Presigned URL test'

        client.put_object('${TEST_BUCKET}', object_name, io.BytesIO(content), len(content))

        get_url = client.generate_presigned_url('${TEST_BUCKET}', object_name, expiry_seconds=3600)
        if not get_url or '${TEST_BUCKET}' not in get_url:
            print("FAIL: GET URL generation failed")
        else:
            put_url = client.generate_presigned_url('${TEST_BUCKET}', '${TEST_PREFIX}/presigned-put.txt',
                                                     expiry_seconds=3600, method='PUT')
            if not put_url:
                print("FAIL: PUT URL generation failed")
            else:
                print("PASS: Presigned URL generation successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_object_metadata_tags() {
    echo -e "${YELLOW}Test 10: Object Metadata and Tags${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        object_name = '${TEST_PREFIX}/metadata-test.txt'
        content = b'Metadata test'
        metadata = {"x-amz-meta-author": "test_user"}

        client.put_object('${TEST_BUCKET}', object_name, io.BytesIO(content),
                         len(content), metadata=metadata)

        tags = {"Type": "Test", "Status": "Active"}
        if not client.set_object_tags('${TEST_BUCKET}', object_name, tags):
            print("FAIL: Set tags failed")
        else:
            retrieved = client.get_object_tags('${TEST_BUCKET}', object_name)
            if not retrieved:
                print("FAIL: Get tags failed")
            else:
                print("PASS: Metadata and tags successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_large_file_upload() {
    echo -e "${YELLOW}Test 11: Large File Upload (6MB)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        object_name = '${TEST_PREFIX}/large-file.bin'
        size = 6 * 1024 * 1024  # 6MB
        data = bytes([i % 256 for i in range(size)])

        if not client.put_object('${TEST_BUCKET}', object_name, io.BytesIO(data), len(data)):
            print("FAIL: Large file upload failed")
        else:
            metadata = client.get_object_metadata('${TEST_BUCKET}', object_name)
            if not metadata or metadata['size'] != size:
                print("FAIL: Size mismatch")
            else:
                print("PASS: Large file upload successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_bucket_versioning() {
    echo -e "${YELLOW}Test 12: Bucket Versioning${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
import io
import time
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        if not client.set_bucket_versioning('${TEST_BUCKET}', True):
            print("FAIL: Enable versioning failed")
        elif not client.get_bucket_versioning('${TEST_BUCKET}'):
            print("FAIL: Versioning not enabled")
        else:
            # Upload multiple versions
            object_name = '${TEST_PREFIX}/versioned-file.txt'
            for i in range(3):
                content = f'Version {i}'.encode()
                client.put_object('${TEST_BUCKET}', object_name, io.BytesIO(content), len(content))
                time.sleep(0.5)

            # Note: list_object_versions is not yet implemented in the proto service
            # Skip version listing check for now
            if not client.set_bucket_versioning('${TEST_BUCKET}', False):
                print("FAIL: Disable versioning failed")
            else:
                print("PASS: Bucket versioning successful (note: list_object_versions not implemented)")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_bucket_lifecycle() {
    echo -e "${YELLOW}Test 13: Bucket Lifecycle Policies${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.minio_client import MinIOClient
try:
    client = MinIOClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        rules = [{
            "id": "delete-old-files",
            "status": "Enabled",
            "expiration": {"days": 30},
            "filter": {"prefix": "${TEST_PREFIX}/temp/"}
        }]

        if not client.set_bucket_lifecycle('${TEST_BUCKET}', rules):
            print("FAIL: Set lifecycle failed")
        elif client.get_bucket_lifecycle('${TEST_BUCKET}') is None:
            print("FAIL: Get lifecycle failed")
        elif not client.delete_bucket_lifecycle('${TEST_BUCKET}'):
            print("FAIL: Delete lifecycle failed")
        else:
            print("PASS: Bucket lifecycle successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

# ========================================
# Main Test Runner
# ========================================

echo ""
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}        MINIO SERVICE COMPREHENSIVE FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo "  Bucket: ${TEST_BUCKET}"
echo ""

# Initial cleanup to remove any leftover state from previous runs
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Bucket Management Tests
echo -e "${CYAN}--- Bucket Management Tests ---${NC}"
test_bucket_create_delete
echo ""
test_bucket_policies
echo ""
test_bucket_tags
echo ""

# Object Operations Tests
echo -e "${CYAN}--- Object Operations Tests ---${NC}"
test_object_upload_download
echo ""
test_object_from_file
echo ""
test_object_copy
echo ""
test_object_list_delete
echo ""
test_presigned_urls
echo ""
test_object_metadata_tags
echo ""

# Advanced Features Tests
echo -e "${CYAN}--- Advanced Features Tests ---${NC}"
test_large_file_upload
echo ""
test_bucket_versioning
echo ""
test_bucket_lifecycle
echo ""

# Cleanup
cleanup

# Print summary
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}                         TEST SUMMARY${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo -e "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"

if [ ${TOTAL} -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", (${PASSED}/${TOTAL})*100}")
    echo "Success Rate: ${SUCCESS_RATE}%"
fi
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    exit 1
fi
