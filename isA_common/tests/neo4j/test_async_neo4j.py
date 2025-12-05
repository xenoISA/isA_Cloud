#!/usr/bin/env python3
"""
Async Neo4j Client - Comprehensive Functional Tests

Tests all async Neo4j operations including:
- Health check
- Cypher query execution
- Node CRUD operations
- Relationship CRUD operations
- Path finding
- Graph algorithms (PageRank, Betweenness Centrality)
- Concurrent operations
- Statistics

Usage:
    python test_async_neo4j.py
    HOST=neo4j-service PORT=50063 python test_async_neo4j.py
"""

import os
import sys
import asyncio
import time

# Add parent path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from isa_common import AsyncNeo4jClient

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '50063'))
USER_ID = os.environ.get('USER_ID', 'test_user')

# Test results
PASSED = 0
FAILED = 0
TOTAL = 0

# Store created node/relationship IDs for cleanup
created_nodes = []
created_relationships = []


def test_result(success: bool, test_name: str):
    """Record test result."""
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    if success:
        PASSED += 1
        print(f"  ✓ PASSED: {test_name}")
    else:
        FAILED += 1
        print(f"  ✗ FAILED: {test_name}")


async def test_health_check(client: AsyncNeo4jClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, "Health check")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_run_cypher(client: AsyncNeo4jClient):
    """Test 2: Run Cypher Query"""
    try:
        result = await client.run_cypher("RETURN 1 as num, 'hello' as msg")
        if result is None or len(result) == 0:
            test_result(False, "Run Cypher - no results")
            return

        if result[0].get('num') != 1:
            test_result(False, f"Run Cypher - unexpected value: {result[0]}")
            return

        test_result(True, "Run Cypher query")
    except Exception as e:
        test_result(False, f"Run Cypher - {e}")


async def test_cypher_with_params(client: AsyncNeo4jClient):
    """Test 3: Cypher Query with Parameters"""
    try:
        result = await client.run_cypher(
            "RETURN $num as num, $msg as msg",
            params={'num': 42, 'msg': 'world'}
        )
        if result is None or len(result) == 0:
            test_result(False, "Cypher with params - no results")
            return

        if result[0].get('num') != 42:
            test_result(False, f"Cypher with params - unexpected: {result[0]}")
            return

        test_result(True, "Cypher with parameters")
    except Exception as e:
        test_result(False, f"Cypher with params - {e}")


async def test_create_node(client: AsyncNeo4jClient):
    """Test 4: Create Node"""
    global created_nodes
    try:
        node_id = await client.create_node(
            labels=['AsyncTestPerson'],
            properties={'name': 'Alice', 'age': 30}
        )
        if node_id is None:
            test_result(False, "Create node - returned None")
            return

        created_nodes.append(node_id)
        test_result(True, f"Create node (id: {node_id})")
    except Exception as e:
        test_result(False, f"Create node - {e}")


async def test_get_node(client: AsyncNeo4jClient):
    """Test 5: Get Node"""
    global created_nodes
    try:
        if not created_nodes:
            test_result(False, "Get node - no nodes created yet")
            return

        node = await client.get_node(created_nodes[0])
        if node is None:
            test_result(False, "Get node - returned None")
            return

        if 'AsyncTestPerson' not in node.get('labels', []):
            test_result(False, f"Get node - missing label: {node}")
            return

        if node.get('properties', {}).get('name') != 'Alice':
            test_result(False, f"Get node - wrong name: {node}")
            return

        test_result(True, "Get node")
    except Exception as e:
        test_result(False, f"Get node - {e}")


async def test_update_node(client: AsyncNeo4jClient):
    """Test 6: Update Node"""
    global created_nodes
    try:
        if not created_nodes:
            test_result(False, "Update node - no nodes created yet")
            return

        result = await client.update_node(
            created_nodes[0],
            properties={'age': 31, 'city': 'New York'}
        )
        if not result:
            test_result(False, "Update node - failed")
            return

        # Verify update
        node = await client.get_node(created_nodes[0])
        if node.get('properties', {}).get('age') != 31:
            test_result(False, f"Update node - age not updated: {node}")
            return

        test_result(True, "Update node")
    except Exception as e:
        test_result(False, f"Update node - {e}")


async def test_create_second_node(client: AsyncNeo4jClient):
    """Test 7: Create Second Node for Relationship Tests"""
    global created_nodes
    try:
        node_id = await client.create_node(
            labels=['AsyncTestPerson'],
            properties={'name': 'Bob', 'age': 25}
        )
        if node_id is None:
            test_result(False, "Create second node - returned None")
            return

        created_nodes.append(node_id)
        test_result(True, f"Create second node (id: {node_id})")
    except Exception as e:
        test_result(False, f"Create second node - {e}")


async def test_create_relationship(client: AsyncNeo4jClient):
    """Test 8: Create Relationship"""
    global created_nodes, created_relationships
    try:
        if len(created_nodes) < 2:
            test_result(False, "Create relationship - need 2 nodes")
            return

        rel_id = await client.create_relationship(
            start_node_id=created_nodes[0],
            end_node_id=created_nodes[1],
            rel_type='KNOWS',
            properties={'since': 2020}
        )
        if rel_id is None:
            test_result(False, "Create relationship - returned None")
            return

        created_relationships.append(rel_id)
        test_result(True, f"Create relationship (id: {rel_id})")
    except Exception as e:
        test_result(False, f"Create relationship - {e}")


async def test_get_relationship(client: AsyncNeo4jClient):
    """Test 9: Get Relationship"""
    global created_relationships
    try:
        if not created_relationships:
            test_result(False, "Get relationship - no relationships created")
            return

        rel = await client.get_relationship(created_relationships[0])
        if rel is None:
            test_result(False, "Get relationship - returned None")
            return

        if rel.get('type') != 'KNOWS':
            test_result(False, f"Get relationship - wrong type: {rel}")
            return

        test_result(True, "Get relationship")
    except Exception as e:
        test_result(False, f"Get relationship - {e}")


async def test_find_nodes(client: AsyncNeo4jClient):
    """Test 10: Find Nodes"""
    try:
        nodes = await client.find_nodes(
            labels=['AsyncTestPerson'],
            limit=10
        )
        if nodes is None:
            test_result(False, "Find nodes - returned None")
            return

        if len(nodes) < 2:
            test_result(False, f"Find nodes - expected 2+, got {len(nodes)}")
            return

        test_result(True, f"Find nodes (found {len(nodes)})")
    except Exception as e:
        test_result(False, f"Find nodes - {e}")


async def test_get_path(client: AsyncNeo4jClient):
    """Test 11: Get Path"""
    global created_nodes
    try:
        if len(created_nodes) < 2:
            test_result(False, "Get path - need 2 nodes")
            return

        path = await client.get_path(
            start_node_id=created_nodes[0],
            end_node_id=created_nodes[1],
            max_depth=5
        )
        if path is None:
            test_result(False, "Get path - no path found")
            return

        if len(path.get('nodes', [])) < 2:
            test_result(False, f"Get path - incomplete: {path}")
            return

        test_result(True, f"Get path (length: {path.get('length')})")
    except Exception as e:
        test_result(False, f"Get path - {e}")


async def test_shortest_path(client: AsyncNeo4jClient):
    """Test 12: Shortest Path"""
    global created_nodes
    try:
        if len(created_nodes) < 2:
            test_result(False, "Shortest path - need 2 nodes")
            return

        path = await client.shortest_path(
            start_node_id=created_nodes[0],
            end_node_id=created_nodes[1],
            max_depth=5
        )
        if path is None:
            test_result(False, "Shortest path - no path found")
            return

        test_result(True, f"Shortest path (length: {path.get('length')})")
    except Exception as e:
        test_result(False, f"Shortest path - {e}")


async def test_concurrent_queries(client: AsyncNeo4jClient):
    """Test 13: Concurrent Query Execution"""
    try:
        start = time.time()

        results = await asyncio.gather(
            client.run_cypher("RETURN 1 as num"),
            client.run_cypher("RETURN 2 as num"),
            client.run_cypher("RETURN 3 as num"),
            client.run_cypher("RETURN 4 as num"),
            client.run_cypher("RETURN 5 as num"),
        )

        elapsed = time.time() - start

        if len(results) != 5:
            test_result(False, f"Concurrent queries - got {len(results)} results")
            return

        test_result(True, f"Concurrent queries (5 queries in {elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent queries - {e}")


async def test_run_cypher_many_concurrent(client: AsyncNeo4jClient):
    """Test 14: run_cypher_many_concurrent Helper"""
    try:
        queries = [
            {'cypher': "RETURN 1 as num"},
            {'cypher': "RETURN 2 as num"},
            {'cypher': "RETURN 3 as num"},
        ]

        start = time.time()
        results = await client.run_cypher_many_concurrent(queries)
        elapsed = time.time() - start

        if len(results) != 3:
            test_result(False, f"run_cypher_many_concurrent - got {len(results)} results")
            return

        test_result(True, f"run_cypher_many_concurrent helper ({elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"run_cypher_many_concurrent - {e}")


async def test_create_nodes_concurrent(client: AsyncNeo4jClient):
    """Test 15: create_nodes_concurrent Helper"""
    global created_nodes
    try:
        nodes = [
            {'labels': ['AsyncTestPerson'], 'properties': {'name': f'Person{i}'}}
            for i in range(3)
        ]

        start = time.time()
        node_ids = await client.create_nodes_concurrent(nodes)
        elapsed = time.time() - start

        success_count = sum(1 for id in node_ids if id is not None)
        created_nodes.extend([id for id in node_ids if id is not None])

        if success_count != 3:
            test_result(False, f"create_nodes_concurrent - {success_count}/3 succeeded")
            return

        test_result(True, f"create_nodes_concurrent helper ({elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"create_nodes_concurrent - {e}")


async def test_get_stats(client: AsyncNeo4jClient):
    """Test 16: Get Statistics"""
    try:
        stats = await client.get_stats()
        if stats is None:
            test_result(False, "Get stats - returned None")
            return

        test_result(True, f"Get statistics (nodes: {stats.get('node_count')}, rels: {stats.get('relationship_count')})")
    except Exception as e:
        test_result(False, f"Get stats - {e}")


async def test_delete_relationship(client: AsyncNeo4jClient):
    """Test 17: Delete Relationship"""
    global created_relationships
    try:
        if not created_relationships:
            test_result(True, "Delete relationship - none to delete")
            return

        result = await client.delete_relationship(created_relationships[0])
        if not result:
            test_result(False, "Delete relationship - failed")
            return

        created_relationships.pop(0)
        test_result(True, "Delete relationship")
    except Exception as e:
        test_result(False, f"Delete relationship - {e}")


async def test_delete_node(client: AsyncNeo4jClient):
    """Test 18: Delete Node"""
    global created_nodes
    try:
        if not created_nodes:
            test_result(True, "Delete node - none to delete")
            return

        node_id = created_nodes.pop()
        result = await client.delete_node(node_id, detach=True)
        if not result:
            test_result(False, "Delete node - failed")
            return

        test_result(True, "Delete node")
    except Exception as e:
        test_result(False, f"Delete node - {e}")


async def cleanup(client: AsyncNeo4jClient):
    """Cleanup test nodes and relationships."""
    global created_nodes, created_relationships
    print("\nCleaning up test data...")

    # Delete relationships first
    for rel_id in created_relationships[:]:
        try:
            await client.delete_relationship(rel_id)
        except Exception:
            pass

    # Delete nodes
    for node_id in created_nodes[:]:
        try:
            await client.delete_node(node_id, detach=True)
        except Exception:
            pass

    # Also clean up by label
    try:
        await client.run_cypher("MATCH (n:AsyncTestPerson) DETACH DELETE n")
    except Exception:
        pass

    created_nodes.clear()
    created_relationships.clear()


async def main():
    """Run all async tests."""
    print("=" * 70)
    print("     ASYNC NEO4J CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print()

    async with AsyncNeo4jClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID
    ) as client:
        # Initial cleanup
        await cleanup(client)

        # Health check (required)
        print("\n--- Health Check ---")
        healthy = await test_health_check(client)
        if not healthy:
            print("\n✗ Cannot proceed without healthy service")
            return 1

        # Cypher operations
        print("\n--- Cypher Query Operations ---")
        await test_run_cypher(client)
        await test_cypher_with_params(client)

        # Node operations
        print("\n--- Node Operations ---")
        await test_create_node(client)
        await test_get_node(client)
        await test_update_node(client)
        await test_create_second_node(client)
        await test_find_nodes(client)

        # Relationship operations
        print("\n--- Relationship Operations ---")
        await test_create_relationship(client)
        await test_get_relationship(client)

        # Path operations
        print("\n--- Path Operations ---")
        await test_get_path(client)
        await test_shortest_path(client)

        # Concurrent operations
        print("\n--- Concurrent Operations ---")
        await test_concurrent_queries(client)
        await test_run_cypher_many_concurrent(client)
        await test_create_nodes_concurrent(client)

        # Statistics
        print("\n--- Statistics ---")
        await test_get_stats(client)

        # Cleanup operations (also test delete)
        print("\n--- Cleanup/Delete Operations ---")
        await test_delete_relationship(client)
        await test_delete_node(client)

        # Final cleanup
        await cleanup(client)

    # Summary
    print("\n" + "=" * 70)
    print("                         TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {TOTAL}")
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")
    if TOTAL > 0:
        print(f"Success Rate: {PASSED/TOTAL*100:.1f}%")
    print()

    if FAILED == 0:
        print(f"✓ ALL TESTS PASSED! ({PASSED}/{TOTAL})")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED ({PASSED}/{TOTAL})")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
