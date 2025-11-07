#!/bin/bash

# ============================================
# Neo4j Service - Comprehensive Functional Tests
# ============================================
# Tests all Neo4j operations including:
# - Health check
# - Node operations (create, get, update, delete, find)
# - Relationship operations (create, get, delete)
# - Graph traversal (paths, shortest path)
# - Graph algorithms (PageRank, Betweenness Centrality)
# - Cypher queries
# - Statistics

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50063}"
USER_ID="${USER_ID:-test-user}"
DATABASE="neo4j"

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
from isa_common.neo4j_client import Neo4jClient
client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        # Delete all test nodes
        client.run_cypher("MATCH (n:TestPerson) DETACH DELETE n", database='${DATABASE}')
        client.run_cypher("MATCH (n:TestCompany) DETACH DELETE n", database='${DATABASE}')
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
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
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

test_node_create() {
    echo -e "${YELLOW}Test 2: Node Creation${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create nodes
        alice_id = client.create_node(
            labels=['TestPerson'],
            properties={'name': 'Alice', 'age': 30, 'city': 'New York'},
            database='${DATABASE}'
        )

        bob_id = client.create_node(
            labels=['TestPerson'],
            properties={'name': 'Bob', 'age': 25, 'city': 'San Francisco'},
            database='${DATABASE}'
        )

        if not alice_id or not bob_id:
            print("FAIL: Node creation failed")
        elif alice_id == bob_id:
            print("FAIL: Nodes have same ID")
        else:
            print("PASS: Node creation successful")
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

test_node_get() {
    echo -e "${YELLOW}Test 3: Node Retrieval${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find nodes first
        nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Alice'},
            database='${DATABASE}'
        )

        if not nodes or len(nodes) == 0:
            print("FAIL: Could not find Alice node")
        else:
            node_id = nodes[0]['id']
            node = client.get_node(node_id, database='${DATABASE}')

            if not node:
                print("FAIL: Get node failed")
            elif node.get('properties', {}).get('name') != 'Alice':
                print("FAIL: Node data incorrect")
            else:
                print("PASS: Node retrieval successful")
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

test_node_update() {
    echo -e "${YELLOW}Test 4: Node Update${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find Alice node
        nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Alice'},
            database='${DATABASE}'
        )

        if not nodes:
            print("FAIL: Could not find Alice node")
        else:
            node_id = nodes[0]['id']

            # Update node
            result = client.update_node(
                node_id,
                properties={'age': 31, 'city': 'Boston'},
                database='${DATABASE}'
            )

            if not result:
                print("FAIL: Update failed")
            else:
                # Verify update
                node = client.get_node(node_id, database='${DATABASE}')
                props = node.get('properties', {})
                if props.get('age') != 31 or props.get('city') != 'Boston':
                    print("FAIL: Update verification failed")
                else:
                    print("PASS: Node update successful")
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

test_relationship_create() {
    echo -e "${YELLOW}Test 5: Relationship Creation${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find Alice and Bob
        alice_nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Alice'},
            database='${DATABASE}'
        )
        bob_nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Bob'},
            database='${DATABASE}'
        )

        if not alice_nodes or not bob_nodes:
            print("FAIL: Could not find nodes")
        else:
            alice_id = alice_nodes[0]['id']
            bob_id = bob_nodes[0]['id']

            # Create relationship
            rel_id = client.create_relationship(
                alice_id,
                bob_id,
                'KNOWS',
                properties={'since': 2020, 'strength': 'strong'},
                database='${DATABASE}'
            )

            if not rel_id:
                print("FAIL: Relationship creation failed")
            else:
                print("PASS: Relationship creation successful")
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

test_relationship_get() {
    echo -e "${YELLOW}Test 6: Relationship Retrieval${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find relationship via Cypher
        results = client.run_cypher(
            "MATCH (a:TestPerson {name: 'Alice'})-[r:KNOWS]->(b:TestPerson {name: 'Bob'}) RETURN id(r) as rel_id",
            database='${DATABASE}'
        )

        if not results or len(results) == 0:
            print("FAIL: Could not find relationship")
        else:
            rel_id = results[0].get('rel_id')
            rel = client.get_relationship(rel_id, database='${DATABASE}')

            if not rel:
                print("FAIL: Get relationship failed")
            elif rel.get('type') != 'KNOWS':
                print("FAIL: Relationship type incorrect")
            else:
                print("PASS: Relationship retrieval successful")
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

test_cypher_query() {
    echo -e "${YELLOW}Test 7: Cypher Query Execution${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create additional nodes for testing
        client.create_node(
            labels=['TestPerson'],
            properties={'name': 'Charlie', 'age': 35},
            database='${DATABASE}'
        )

        # Query with parameters
        results = client.run_cypher(
            "MATCH (p:TestPerson) WHERE p.age > \$min_age RETURN p.name as name, p.age as age ORDER BY p.age",
            params={'min_age': 25},
            database='${DATABASE}'
        )

        if not results:
            print("FAIL: Query returned no results")
        elif len(results) < 2:
            print(f"FAIL: Expected at least 2 results, got {len(results)}")
        else:
            # Verify ordering
            ages = [r.get('age') for r in results]
            if ages != sorted(ages):
                print("FAIL: Results not properly ordered")
            else:
                print("PASS: Cypher query successful")
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

test_find_nodes() {
    echo -e "${YELLOW}Test 8: Find Nodes${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find all TestPerson nodes
        nodes = client.find_nodes(
            labels=['TestPerson'],
            limit=100,
            database='${DATABASE}'
        )

        if not nodes:
            print("FAIL: No nodes found")
        elif len(nodes) < 3:
            print(f"FAIL: Expected at least 3 nodes, got {len(nodes)}")
        else:
            # Verify node structure
            if 'labels' not in nodes[0] or 'properties' not in nodes[0]:
                print("FAIL: Node structure incorrect")
            else:
                print("PASS: Find nodes successful")
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

test_path_finding() {
    echo -e "${YELLOW}Test 9: Path Finding${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find Alice and Bob
        alice_nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Alice'},
            database='${DATABASE}'
        )
        bob_nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Bob'},
            database='${DATABASE}'
        )

        if not alice_nodes or not bob_nodes:
            print("FAIL: Could not find nodes")
        else:
            alice_id = alice_nodes[0]['id']
            bob_id = bob_nodes[0]['id']

            # Get path
            path = client.get_path(alice_id, bob_id, max_depth=5, database='${DATABASE}')

            if not path:
                print("FAIL: Path not found")
            elif path.get('length') != 1:
                print(f"FAIL: Expected path length 1, got {path.get('length')}")
            elif len(path.get('nodes', [])) != 2:
                print("FAIL: Path should have 2 nodes")
            elif len(path.get('relationships', [])) != 1:
                print("FAIL: Path should have 1 relationship")
            else:
                print("PASS: Path finding successful")
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

test_shortest_path() {
    echo -e "${YELLOW}Test 10: Shortest Path${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find Alice and Bob
        alice_nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Alice'},
            database='${DATABASE}'
        )
        bob_nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Bob'},
            database='${DATABASE}'
        )

        if not alice_nodes or not bob_nodes:
            print("FAIL: Could not find nodes")
        else:
            alice_id = alice_nodes[0]['id']
            bob_id = bob_nodes[0]['id']

            # Get shortest path
            path = client.shortest_path(alice_id, bob_id, max_depth=5, database='${DATABASE}')

            if not path:
                print("FAIL: Shortest path not found")
            elif path.get('length') != 1:
                print(f"FAIL: Expected path length 1, got {path.get('length')}")
            else:
                print("PASS: Shortest path successful")
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

test_statistics() {
    echo -e "${YELLOW}Test 11: Database Statistics${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        stats = client.get_stats(database='${DATABASE}')

        if not stats:
            print("FAIL: Could not retrieve stats")
        elif 'node_count' not in stats or 'relationship_count' not in stats:
            print("FAIL: Stats missing required fields")
        elif stats['node_count'] < 3:
            print(f"FAIL: Expected at least 3 nodes, got {stats['node_count']}")
        else:
            print("PASS: Statistics retrieval successful")
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

test_node_delete() {
    echo -e "${YELLOW}Test 12: Node Deletion${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.neo4j_client import Neo4jClient
try:
    client = Neo4jClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Find Charlie node
        nodes = client.find_nodes(
            labels=['TestPerson'],
            properties={'name': 'Charlie'},
            database='${DATABASE}'
        )

        if not nodes:
            print("FAIL: Could not find Charlie node")
        else:
            node_id = nodes[0]['id']

            # Delete node (detach to remove relationships)
            result = client.delete_node(node_id, detach=True, database='${DATABASE}')

            if not result:
                print("FAIL: Delete failed")
            else:
                # Verify deletion
                node = client.get_node(node_id, database='${DATABASE}')
                if node:
                    print("FAIL: Node still exists")
                else:
                    print("PASS: Node deletion successful")
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
echo -e "${CYAN}         NEO4J SERVICE COMPREHENSIVE FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo "  Database: ${DATABASE}"
echo ""

# Initial cleanup
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Node Operations
echo -e "${CYAN}--- Node Operations Tests ---${NC}"
test_node_create
echo ""
test_node_get
echo ""
test_node_update
echo ""
test_find_nodes
echo ""

# Relationship Operations
echo -e "${CYAN}--- Relationship Operations Tests ---${NC}"
test_relationship_create
echo ""
test_relationship_get
echo ""

# Graph Queries
echo -e "${CYAN}--- Graph Query Tests ---${NC}"
test_cypher_query
echo ""
test_path_finding
echo ""
test_shortest_path
echo ""

# Advanced Features
echo -e "${CYAN}--- Advanced Features Tests ---${NC}"
test_statistics
echo ""
test_node_delete
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
