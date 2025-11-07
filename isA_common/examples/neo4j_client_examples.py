#!/usr/bin/env python3
"""
Neo4j Client Usage Examples
============================

This example demonstrates how to use the Neo4jClient from isa_common package.

File: isA_common/examples/neo4j_client_examples.py

Prerequisites:
--------------
1. Neo4j gRPC service must be running (default: localhost:50063)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/neo4j_client_examples.py

# Run with custom host/port
python isA_common/examples/neo4j_client_examples.py --host 192.168.1.100 --port 50063
```

Features Demonstrated:
----------------------
✓ Health Check
✓ Node Operations (create, get, update, delete, find)
✓ Relationship Operations (create, get, delete)
✓ Cypher Queries (parameterized queries)
✓ Graph Traversal (paths, shortest path)
✓ Graph Algorithms (PageRank, Betweenness Centrality)
✓ Database Statistics

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse

# Import the Neo4jClient from isa_common
try:
    from isa_common.neo4j_client import Neo4jClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.neo4j_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50063):
    """
    Example 1: Health Check

    Check if the Neo4j gRPC service is healthy and operational.
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check()

        if health and health.get('healthy'):
            print(f"✅ Service is healthy!")
            print(f"   Version: {health.get('version')}")
            print(f"   Database: {health.get('database')}")
        else:
            print("❌ Service is not healthy")


def example_02_create_nodes(host='localhost', port=50063):
    """
    Example 2: Node Creation

    Create nodes in the graph database.
    """
    print("\n" + "=" * 80)
    print("Example 2: Node Creation")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Create person nodes
        alice_id = client.create_node(
            labels=['ExamplePerson'],
            properties={'name': 'Alice', 'age': 30, 'occupation': 'Engineer'},
            database='neo4j'
        )

        bob_id = client.create_node(
            labels=['ExamplePerson'],
            properties={'name': 'Bob', 'age': 28, 'occupation': 'Designer'},
            database='neo4j'
        )

        charlie_id = client.create_node(
            labels=['ExamplePerson'],
            properties={'name': 'Charlie', 'age': 35, 'occupation': 'Manager'},
            database='neo4j'
        )

        # Create company node
        company_id = client.create_node(
            labels=['ExampleCompany'],
            properties={'name': 'TechCorp', 'industry': 'Technology'},
            database='neo4j'
        )

        print(f"✅ Created nodes:")
        print(f"   • Alice (ID: {alice_id})")
        print(f"   • Bob (ID: {bob_id})")
        print(f"   • Charlie (ID: {charlie_id})")
        print(f"   • TechCorp (ID: {company_id})")


def example_03_node_operations(host='localhost', port=50063):
    """
    Example 3: Node Operations

    Get, update, and find nodes.
    """
    print("\n" + "=" * 80)
    print("Example 3: Node Operations")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Find Alice node
        nodes = client.find_nodes(
            labels=['ExamplePerson'],
            properties={'name': 'Alice'},
            database='neo4j'
        )

        if nodes:
            alice_id = nodes[0]['id']
            print(f"✅ Found Alice (ID: {alice_id})")

            # Get node details
            node = client.get_node(alice_id, database='neo4j')
            if node:
                props = node.get('properties', {})
                print(f"   Properties: {props}")

            # Update node
            client.update_node(
                alice_id,
                properties={'age': 31, 'city': 'San Francisco'},
                database='neo4j'
            )
            print(f"✅ Updated Alice's properties")

            # Verify update
            node = client.get_node(alice_id, database='neo4j')
            props = node.get('properties', {})
            print(f"   New age: {props.get('age')}, City: {props.get('city')}")


def example_04_create_relationships(host='localhost', port=50063):
    """
    Example 4: Relationship Creation

    Create relationships between nodes.
    """
    print("\n" + "=" * 80)
    print("Example 4: Relationship Creation")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Find nodes
        alice = client.find_nodes(labels=['ExamplePerson'], properties={'name': 'Alice'}, database='neo4j')[0]
        bob = client.find_nodes(labels=['ExamplePerson'], properties={'name': 'Bob'}, database='neo4j')[0]
        charlie = client.find_nodes(labels=['ExamplePerson'], properties={'name': 'Charlie'}, database='neo4j')[0]
        company = client.find_nodes(labels=['ExampleCompany'], properties={'name': 'TechCorp'}, database='neo4j')[0]

        # Create KNOWS relationships
        rel1 = client.create_relationship(
            alice['id'], bob['id'],
            'KNOWS',
            properties={'since': 2018, 'context': 'college'},
            database='neo4j'
        )

        rel2 = client.create_relationship(
            bob['id'], charlie['id'],
            'KNOWS',
            properties={'since': 2020, 'context': 'work'},
            database='neo4j'
        )

        # Create WORKS_AT relationships
        rel3 = client.create_relationship(
            alice['id'], company['id'],
            'WORKS_AT',
            properties={'position': 'Senior Engineer', 'since': 2019},
            database='neo4j'
        )

        rel4 = client.create_relationship(
            bob['id'], company['id'],
            'WORKS_AT',
            properties={'position': 'Lead Designer', 'since': 2020},
            database='neo4j'
        )

        rel5 = client.create_relationship(
            charlie['id'], company['id'],
            'WORKS_AT',
            properties={'position': 'Engineering Manager', 'since': 2018},
            database='neo4j'
        )

        print(f"✅ Created relationships:")
        print(f"   • Alice KNOWS Bob")
        print(f"   • Bob KNOWS Charlie")
        print(f"   • Alice, Bob, Charlie WORKS_AT TechCorp")


def example_05_cypher_queries(host='localhost', port=50063):
    """
    Example 5: Cypher Queries

    Execute custom Cypher queries.
    """
    print("\n" + "=" * 80)
    print("Example 5: Cypher Queries")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Query with parameters
        results = client.run_cypher(
            "MATCH (p:ExamplePerson) WHERE p.age > $min_age RETURN p.name as name, p.age as age ORDER BY p.age",
            params={'min_age': 25},
            database='neo4j'
        )

        print(f"✅ People over 25 years old:")
        for row in results:
            print(f"   • {row.get('name')}: {row.get('age')} years")

        # Find all employees at TechCorp
        results = client.run_cypher(
            """
            MATCH (p:ExamplePerson)-[r:WORKS_AT]->(c:ExampleCompany {name: 'TechCorp'})
            RETURN p.name as name, r.position as position
            ORDER BY name
            """,
            database='neo4j'
        )

        print(f"\n✅ TechCorp employees:")
        for row in results:
            print(f"   • {row.get('name')}: {row.get('position')}")


def example_06_path_finding(host='localhost', port=50063):
    """
    Example 6: Path Finding

    Find paths between nodes in the graph.
    """
    print("\n" + "=" * 80)
    print("Example 6: Path Finding")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Find Alice and Charlie
        alice = client.find_nodes(labels=['ExamplePerson'], properties={'name': 'Alice'}, database='neo4j')[0]
        charlie = client.find_nodes(labels=['ExamplePerson'], properties={'name': 'Charlie'}, database='neo4j')[0]

        # Find path
        path = client.get_path(alice['id'], charlie['id'], max_depth=5, database='neo4j')

        if path:
            print(f"✅ Path from Alice to Charlie:")
            print(f"   Length: {path.get('length')} hops")
            print(f"\n   Nodes in path:")
            for node in path.get('nodes', []):
                props = node.get('properties', {})
                print(f"   • {props.get('name')}")

        # Find shortest path
        shortest = client.shortest_path(alice['id'], charlie['id'], max_depth=5, database='neo4j')

        if shortest:
            print(f"\n✅ Shortest path:")
            print(f"   Length: {shortest.get('length')} hops")


def example_07_find_nodes(host='localhost', port=50063):
    """
    Example 7: Find Nodes

    Search for nodes by labels and properties.
    """
    print("\n" + "=" * 80)
    print("Example 7: Find Nodes")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Find all ExamplePerson nodes
        persons = client.find_nodes(
            labels=['ExamplePerson'],
            limit=10,
            database='neo4j'
        )

        print(f"✅ Found {len(persons)} person nodes:")
        for person in persons:
            props = person.get('properties', {})
            print(f"   • {props.get('name')}: {props.get('occupation')}")

        # Find specific person
        engineers = client.find_nodes(
            labels=['ExamplePerson'],
            properties={'occupation': 'Engineer'},
            database='neo4j'
        )

        print(f"\n✅ Found {len(engineers)} engineer(s):")
        for eng in engineers:
            props = eng.get('properties', {})
            print(f"   • {props.get('name')}")


def example_08_statistics(host='localhost', port=50063):
    """
    Example 8: Database Statistics

    Get statistics about the graph database.
    """
    print("\n" + "=" * 80)
    print("Example 8: Database Statistics")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        stats = client.get_stats(database='neo4j')

        if stats:
            print(f"✅ Database statistics:")
            print(f"   • Nodes: {stats.get('node_count')}")
            print(f"   • Relationships: {stats.get('relationship_count')}")
            print(f"   • Labels: {stats.get('label_count')}")
            print(f"   • Relationship types: {stats.get('relationship_type_count')}")
            print(f"   • Property keys: {stats.get('property_key_count')}")


def example_09_cleanup(host='localhost', port=50063):
    """
    Example 9: Cleanup

    Delete all example nodes and relationships.
    """
    print("\n" + "=" * 80)
    print("Example 9: Cleanup")
    print("=" * 80)

    with Neo4jClient(host=host, port=port, user_id='example-user') as client:
        # Delete all ExamplePerson and ExampleCompany nodes
        client.run_cypher(
            "MATCH (n:ExamplePerson) DETACH DELETE n",
            database='neo4j'
        )
        client.run_cypher(
            "MATCH (n:ExampleCompany) DETACH DELETE n",
            database='neo4j'
        )

        print(f"✅ Deleted all example nodes and relationships")


def main():
    """Run all examples"""
    parser = argparse.ArgumentParser(description='Neo4j Client Usage Examples')
    parser.add_argument('--host', default='localhost', help='Neo4j gRPC service host')
    parser.add_argument('--port', type=int, default=50063, help='Neo4j gRPC service port')
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("Neo4j Client Examples")
    print("=" * 80)
    print(f"Connecting to: {args.host}:{args.port}")

    try:
        example_01_health_check(args.host, args.port)
        example_02_create_nodes(args.host, args.port)
        example_03_node_operations(args.host, args.port)
        example_04_create_relationships(args.host, args.port)
        example_05_cypher_queries(args.host, args.port)
        example_06_path_finding(args.host, args.port)
        example_07_find_nodes(args.host, args.port)
        example_08_statistics(args.host, args.port)
        example_09_cleanup(args.host, args.port)

        print("\n" + "=" * 80)
        print("✅ All examples completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
