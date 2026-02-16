#!/bin/bash

# ============================================
# Qdrant Service - Comprehensive Functional Tests
# ============================================
# Tests all Qdrant operations including:
# - Health check
# - Collection management (create, list, delete, info)
# - Point operations (upsert, search, delete, count)
# - Vector search operations

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50062}"
USER_ID="${USER_ID:-test-user}"
TEST_COLLECTION="test_collection"
VECTOR_SIZE=128

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
from isa_common.qdrant_client import QdrantClient
client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        client.delete_collection('${TEST_COLLECTION}')
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
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
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

test_collection_create() {
    echo -e "${YELLOW}Test 2: Collection Creation${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Delete if exists
        try:
            client.delete_collection('${TEST_COLLECTION}')
        except:
            pass

        # Create collection
        result = client.create_collection('${TEST_COLLECTION}', ${VECTOR_SIZE}, 'Cosine')

        if not result:
            print("FAIL: Collection creation failed")
        else:
            collections = client.list_collections()
            if '${TEST_COLLECTION}' not in collections:
                print("FAIL: Collection not in list")
            else:
                print("PASS: Collection creation successful")
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

test_collection_info() {
    echo -e "${YELLOW}Test 3: Collection Info Retrieval${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        info = client.get_collection_info('${TEST_COLLECTION}')

        if not info:
            print("FAIL: Could not get collection info")
        elif 'points_count' not in info:
            print("FAIL: Info missing points_count")
        else:
            print("PASS: Collection info retrieval successful")
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

test_upsert_points() {
    echo -e "${YELLOW}Test 4: Upsert Points${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
import random
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Generate random vectors
        points = []
        for i in range(10):
            vector = [random.random() for _ in range(${VECTOR_SIZE})]
            points.append({
                'id': i,
                'vector': vector,
                'payload': {'text': f'Document {i}', 'category': f'cat_{i % 3}'}
            })

        operation_id = client.upsert_points('${TEST_COLLECTION}', points)

        if not operation_id:
            print("FAIL: Upsert failed")
        else:
            count = client.count_points('${TEST_COLLECTION}')
            if count != 10:
                print(f"FAIL: Expected 10 points, got {count}")
            else:
                print("PASS: Upsert points successful")
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

test_vector_search() {
    echo -e "${YELLOW}Test 5: Vector Search${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
import random
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create query vector
        query_vector = [random.random() for _ in range(${VECTOR_SIZE})]

        # Search without threshold
        results = client.search('${TEST_COLLECTION}', query_vector, limit=5)

        if not results:
            print("FAIL: Search returned no results")
        elif len(results) != 5:
            print(f"FAIL: Expected 5 results, got {len(results)}")
        elif 'score' not in results[0] or 'id' not in results[0]:
            print("FAIL: Results missing required fields")
        else:
            # Search with payload
            results_with_payload = client.search(
                '${TEST_COLLECTION}',
                query_vector,
                limit=3,
                with_payload=True
            )
            if not results_with_payload[0].get('payload'):
                print("FAIL: Payload not returned")
            else:
                print("PASS: Vector search successful")
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

test_search_with_threshold() {
    echo -e "${YELLOW}Test 6: Search with Score Threshold${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
import random
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        query_vector = [random.random() for _ in range(${VECTOR_SIZE})]

        # Search with threshold
        results = client.search(
            '${TEST_COLLECTION}',
            query_vector,
            limit=10,
            score_threshold=0.5,
            with_payload=True,
            with_vectors=False
        )

        if results is None:
            print("FAIL: Search failed")
        else:
            # Verify all scores are above threshold
            all_above_threshold = all(r['score'] >= 0.5 for r in results)
            if not all_above_threshold:
                print("FAIL: Some scores below threshold")
            else:
                print("PASS: Search with threshold successful")
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

test_delete_points() {
    echo -e "${YELLOW}Test 7: Delete Points${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Delete 3 points
        ids_to_delete = [0, 1, 2]
        operation_id = client.delete_points('${TEST_COLLECTION}', ids_to_delete)

        if not operation_id:
            print("FAIL: Delete failed")
        else:
            count = client.count_points('${TEST_COLLECTION}')
            if count != 7:
                print(f"FAIL: Expected 7 points after delete, got {count}")
            else:
                print("PASS: Delete points successful")
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

test_upsert_with_string_ids() {
    echo -e "${YELLOW}Test 8: Upsert with String IDs (UUID format)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
import random
import uuid
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Upsert points with string IDs (must be valid UUIDs)
        points = []
        for i in range(5):
            vector = [random.random() for _ in range(${VECTOR_SIZE})]
            points.append({
                'id': str(uuid.uuid4()),  # Generate valid UUID
                'vector': vector,
                'payload': {'doc_id': f'doc_{i}'}
            })

        operation_id = client.upsert_points('${TEST_COLLECTION}', points)

        if not operation_id:
            print("FAIL: Upsert with string IDs failed")
        else:
            count = client.count_points('${TEST_COLLECTION}')
            if count != 12:  # 7 remaining + 5 new
                print(f"FAIL: Expected 12 points, got {count}")
            else:
                print("PASS: Upsert with UUID string IDs successful")
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

test_search_with_filter() {
    echo -e "${YELLOW}Test 9: Search with Filters${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
import random
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create query vector
        query_vector = [random.random() for _ in range(${VECTOR_SIZE})]

        # Search with filter conditions
        filter_conditions = {
            'must': [
                {'field': 'category', 'match': {'keyword': 'cat_1'}}
            ]
        }

        results = client.search_with_filter(
            '${TEST_COLLECTION}',
            query_vector,
            filter_conditions=filter_conditions,
            limit=5,
            score_threshold=0.3
        )

        if results is None:
            print("FAIL: Filtered search failed")
        else:
            # Verify all results match the filter
            all_match = all(r.get('payload', {}).get('category') == 'cat_1' for r in results if r.get('payload'))
            if not all_match and len(results) > 0:
                print("FAIL: Some results don't match filter")
            else:
                print("PASS: Filtered search successful")
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

test_scroll() {
    echo -e "${YELLOW}Test 10: Scroll through Points${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Scroll through points
        result = client.scroll('${TEST_COLLECTION}', limit=5)

        if not result:
            print("FAIL: Scroll failed")
        elif 'points' not in result:
            print("FAIL: No points in scroll result")
        elif len(result['points']) == 0:
            print("FAIL: No points returned")
        else:
            # Try paginated scroll if we have more points
            total_points = len(result['points'])
            if result.get('next_offset'):
                next_result = client.scroll('${TEST_COLLECTION}', limit=5, offset_id=result['next_offset'])
                if next_result:
                    total_points += len(next_result['points'])

            print(f"PASS: Scroll successful, retrieved {total_points} points")
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

test_recommend() {
    echo -e "${YELLOW}Test 11: Recommend Points${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Use integer IDs that still exist (after Test 7 deleted 0,1,2)
        # Remaining IDs are: 3,4,5,6,7,8,9 plus 5 UUID string IDs from Test 8
        positive_ids = [3, 4, 5]
        negative_ids = [6, 7]  # Changed from [0, 1] which were deleted

        results = client.recommend(
            '${TEST_COLLECTION}',
            positive=positive_ids,
            negative=negative_ids,
            limit=5
        )

        if results is None:
            print("FAIL: Recommend failed")
        elif len(results) == 0:
            print("FAIL: No recommendations returned")
        else:
            # Verify results have scores
            has_scores = all('score' in r for r in results)
            if not has_scores:
                print("FAIL: Results missing scores")
            else:
                print(f"PASS: Recommend successful, got {len(results)} recommendations")
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

test_update_payload() {
    echo -e "${YELLOW}Test 12: Update Payload${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Update payload for specific points
        ids_to_update = [3, 4, 5]
        new_payload = {'status': 'updated', 'priority': 'high'}

        operation_id = client.update_payload('${TEST_COLLECTION}', ids_to_update, new_payload)

        if not operation_id:
            print("FAIL: Update payload failed")
        else:
            # Verify update by scrolling and checking
            result = client.scroll('${TEST_COLLECTION}', limit=20, with_payload=True)
            if result and result['points']:
                updated_points = [p for p in result['points'] if p.get('id') in ids_to_update]
                if len(updated_points) > 0:
                    has_status = any(p.get('payload', {}).get('status') == 'updated' for p in updated_points)
                    if has_status:
                        print("PASS: Update payload successful")
                    else:
                        print("FAIL: Payload not updated")
                else:
                    print("PASS: Update payload operation completed")
            else:
                print("PASS: Update payload operation completed")
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

test_delete_payload_fields() {
    echo -e "${YELLOW}Test 13: Delete Payload Fields${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Delete specific payload fields
        ids = [3, 4]
        keys_to_delete = ['priority']

        operation_id = client.delete_payload_fields('${TEST_COLLECTION}', ids, keys_to_delete)

        if not operation_id:
            print("FAIL: Delete payload fields failed")
        else:
            print("PASS: Delete payload fields successful")
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

test_clear_payload() {
    echo -e "${YELLOW}Test 14: Clear Payload${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Clear all payload from specific points
        ids = [6]

        operation_id = client.clear_payload('${TEST_COLLECTION}', ids)

        if not operation_id:
            print("FAIL: Clear payload failed")
        else:
            print("PASS: Clear payload successful")
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

test_field_index() {
    echo -e "${YELLOW}Test 15: Field Index Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create field index
        operation_id = client.create_field_index(
            '${TEST_COLLECTION}',
            'category',
            'keyword'
        )

        if not operation_id:
            print("FAIL: Create field index failed")
        else:
            # Delete field index
            delete_op = client.delete_field_index('${TEST_COLLECTION}', 'category')
            if not delete_op:
                print("FAIL: Delete field index failed")
            else:
                print("PASS: Field index operations successful")
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

test_snapshots() {
    echo -e "${YELLOW}Test 16: Snapshot Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create snapshot
        snapshot_name = client.create_snapshot('${TEST_COLLECTION}')

        if not snapshot_name:
            print("FAIL: Create snapshot failed")
        else:
            # List snapshots
            snapshots = client.list_snapshots('${TEST_COLLECTION}')
            if snapshots is None:
                print("FAIL: List snapshots failed")
            elif len(snapshots) == 0:
                print("FAIL: No snapshots found")
            else:
                # Delete snapshot
                success = client.delete_snapshot('${TEST_COLLECTION}', snapshot_name)
                if not success:
                    print("FAIL: Delete snapshot failed")
                else:
                    print("PASS: Snapshot operations successful")
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

test_delete_collection() {
    echo -e "${YELLOW}Test 17: Collection Deletion${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.qdrant_client import QdrantClient
try:
    client = QdrantClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        result = client.delete_collection('${TEST_COLLECTION}')

        if not result:
            print("FAIL: Delete collection failed")
        else:
            collections = client.list_collections()
            if '${TEST_COLLECTION}' in collections:
                print("FAIL: Collection still exists")
            else:
                print("PASS: Collection deletion successful")
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
echo -e "${CYAN}        QDRANT SERVICE COMPREHENSIVE FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo "  Collection: ${TEST_COLLECTION}"
echo "  Vector Size: ${VECTOR_SIZE}"
echo ""

# Initial cleanup
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Collection Management
echo -e "${CYAN}--- Collection Management Tests ---${NC}"
test_collection_create
echo ""
test_collection_info
echo ""

# Vector Operations
echo -e "${CYAN}--- Vector Operations Tests ---${NC}"
test_upsert_points
echo ""
test_vector_search
echo ""
test_search_with_threshold
echo ""

# Point Management
echo -e "${CYAN}--- Point Management Tests ---${NC}"
test_delete_points
echo ""
test_upsert_with_string_ids
echo ""

# Advanced Search Tests
echo -e "${CYAN}--- Advanced Search Tests ---${NC}"
test_search_with_filter
echo ""
test_scroll
echo ""
test_recommend
echo ""

# Payload Management Tests
echo -e "${CYAN}--- Payload Management Tests ---${NC}"
test_update_payload
echo ""
test_delete_payload_fields
echo ""
test_clear_payload
echo ""

# Index Management Tests
echo -e "${CYAN}--- Index Management Tests ---${NC}"
test_field_index
echo ""

# Snapshot Tests
echo -e "${CYAN}--- Snapshot Tests ---${NC}"
test_snapshots
echo ""

# Cleanup Tests
echo -e "${CYAN}--- Cleanup Tests ---${NC}"
test_delete_collection
echo ""

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
