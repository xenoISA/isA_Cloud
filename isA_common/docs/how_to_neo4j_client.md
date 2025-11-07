# =€ Neo4j Client - Graph Database Made Simple

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Simple Usage Pattern

```python
from isa_common.neo4j_client import Neo4jClient

# 1. Connect (auto-discovers via Consul or use direct host)
with Neo4jClient(host='localhost', port=50063, user_id='your-service') as client:

    # 2. Create nodes
    alice_id = client.create_node(['Person'], {'name': 'Alice', 'age': 30})

    # 3. Create relationships
    rel_id = client.create_relationship(alice_id, bob_id, 'KNOWS',
        {'since': 2020})

    # 4. Run Cypher queries
    results = client.run_cypher(
        "MATCH (p:Person) WHERE p.age > $age RETURN p.name",
        params={'age': 25}
    )

    # 5. Find paths
    path = client.shortest_path(alice_id, charlie_id, max_depth=5)
```

---

## Real Service Example: Social Network Service

```python
from isa_common.neo4j_client import Neo4jClient

class SocialNetworkService:
    def __init__(self):
        self.neo4j = Neo4jClient(user_id='social-network-service')

    def create_user(self, username, email, profile_data):
        # Just focus on YOUR business logic
        user_id = self.neo4j.create_node(
            labels=['User'],
            properties={
                'username': username,
                'email': email,
                **profile_data
            }
        )
        return user_id

    def add_friendship(self, user1_id, user2_id):
        # One line to create relationship - client handles all gRPC complexity
        return self.neo4j.create_relationship(
            user1_id, user2_id, 'FRIENDS',
            {'created_at': datetime.now().isoformat()}
        )

    def get_friends_of_friends(self, user_id, max_hops=2):
        # Powerful graph queries in one line
        results = self.neo4j.run_cypher(
            """
            MATCH (user:User)-[:FRIENDS*1..%s]-(friend:User)
            WHERE id(user) = $user_id AND id(user) <> id(friend)
            RETURN DISTINCT friend.username as username, friend.email as email
            """ % max_hops,
            params={'user_id': user_id}
        )
        return [{'username': r['username'], 'email': r['email']} for r in results]

    def find_connection_path(self, user1_id, user2_id):
        # Graph traversal - ONE LINE
        path = self.neo4j.shortest_path(user1_id, user2_id, max_depth=6)

        if path:
            # Extract the connection chain
            names = [n['properties']['username'] for n in path['nodes']]
            return {
                'connected': True,
                'degrees': path['length'],
                'path': ' ’ '.join(names)
            }
        return {'connected': False}

    def recommend_connections(self, user_id):
        # Recommendation engine using Cypher
        results = self.neo4j.run_cypher(
            """
            MATCH (user:User)-[:FRIENDS]->(friend)-[:FRIENDS]->(fof:User)
            WHERE id(user) = $user_id
              AND NOT (user)-[:FRIENDS]-(fof)
              AND id(user) <> id(fof)
            RETURN fof.username as username,
                   fof.email as email,
                   count(*) as mutual_friends
            ORDER BY mutual_friends DESC
            LIMIT 10
            """,
            params={'user_id': user_id}
        )
        return results
```

---

## Quick Patterns for Common Use Cases

### Create Social Graph
```python
# Create users
alice = client.create_node(['User'], {'name': 'Alice', 'age': 30})
bob = client.create_node(['User'], {'name': 'Bob', 'age': 28})
charlie = client.create_node(['User'], {'name': 'Charlie', 'age': 35})

# Create friendships
client.create_relationship(alice, bob, 'FRIENDS', {'since': 2018})
client.create_relationship(bob, charlie, 'FRIENDS', {'since': 2020})
```

### Find Users by Property
```python
# Find all engineers
engineers = client.find_nodes(
    labels=['User'],
    properties={'occupation': 'Engineer'}
)

# Find with Cypher (more flexible)
results = client.run_cypher(
    "MATCH (u:User) WHERE u.age > $min_age RETURN u",
    params={'min_age': 25}
)
```

### Update Node Properties
```python
# Update user profile
client.update_node(user_id, properties={
    'city': 'San Francisco',
    'updated_at': datetime.now().isoformat()
})
```

### Get Node Details
```python
# Retrieve node by ID
node = client.get_node(user_id)
if node:
    print(f"User: {node['properties']['name']}")
    print(f"Labels: {node['labels']}")
```

### Delete Node and Relationships
```python
# Delete node and all its relationships
client.delete_node(user_id, detach=True)

# Or just delete the node (fails if relationships exist)
client.delete_node(user_id, detach=False)
```

### Path Finding
```python
# Find any path between two users
path = client.get_path(alice_id, charlie_id, max_depth=5)

if path:
    print(f"Path length: {path['length']} hops")
    for node in path['nodes']:
        print(f"  ’ {node['properties']['name']}")

# Find shortest path
shortest = client.shortest_path(alice_id, charlie_id, max_depth=10)
```

### Relationship Operations
```python
# Get relationship by ID
rel = client.get_relationship(rel_id)
if rel:
    print(f"Type: {rel['type']}")
    print(f"Properties: {rel['properties']}")

# Delete relationship
client.delete_relationship(rel_id)
```

### Batch Cypher Queries
```python
# Execute multiple queries in one call
queries = [
    {'cypher': 'CREATE (n:User {name: $name}) RETURN n', 'params': {'name': 'Alice'}},
    {'cypher': 'CREATE (n:User {name: $name}) RETURN n', 'params': {'name': 'Bob'}},
    {'cypher': 'CREATE (n:User {name: $name}) RETURN n', 'params': {'name': 'Charlie'}},
]

results = client.run_cypher_batch(queries)
for i, result in enumerate(results):
    print(f"Query {i+1}: {len(result)} rows returned")
```

### Health Check
```python
# Check service health
health = client.health_check()
if health and health['healthy']:
    print(f"Service version: {health['version']}")
    print(f"Database: {health['database']}")
```

### Database Statistics
```python
# Get graph statistics
stats = client.get_stats()
print(f"Total nodes: {stats['node_count']}")
print(f"Total relationships: {stats['relationship_count']}")
print(f"Labels: {stats['label_count']}")
```

---

## Benefits = MASSIVE Time Saver

### What you DON'T need to worry about:
- L gRPC connection management
- L Proto message serialization
- L Error handling and retries
- L Connection pooling
- L Type conversions (nodes, relationships, paths)
- L Context managers and cleanup
- L Service discovery (Consul integration built-in)
- L Graph type handling (dbtype.Node, dbtype.Path, etc.)

### What you CAN focus on:
-  Your graph data model
-  Your business logic
-  Your relationship patterns
-  Your user experience
-  Your graph algorithms
-  Your query optimization

---

## Comparison: Without vs With Client

### Without (Raw gRPC):
```python
# 100+ lines of gRPC setup, connection handling, message building...
import grpc
from isa_common.proto import neo4j_service_pb2, neo4j_service_pb2_grpc
from google.protobuf.struct_pb2 import Struct

channel = grpc.insecure_channel('localhost:50063')
stub = neo4j_service_pb2_grpc.Neo4jServiceStub(channel)

try:
    # Build properties struct manually
    props = Struct()
    props.update({'name': 'Alice', 'age': 30})

    # Build request
    request = neo4j_service_pb2.CreateNodeRequest(
        metadata=neo4j_service_pb2.RequestMetadata(
            user_id='my-service',
            request_id=str(uuid.uuid4()),
            timestamp=timestamp_pb2.Timestamp()
        ),
        labels=['User'],
        properties=props,
        database='neo4j'
    )

    # Execute call
    response = stub.CreateNode(request)

    # Check response
    if response.metadata.success:
        node_id = response.node.id
        # Process node...
    else:
        # Handle error...

finally:
    channel.close()
```

### With isa_common:
```python
# 3 lines
with Neo4jClient() as client:
    node_id = client.create_node(['User'], {'name': 'Alice', 'age': 30})
```

---

## Complete Feature List

 **Node Operations**: create, get, update, delete, find, merge
 **Relationship Operations**: create, get, delete, find
 **Cypher Queries**: run, run_read, run_write, run_batch
 **Graph Traversal**: get_path, shortest_path, get_neighbors
 **Path Finding**: any path, shortest path, all paths
 **Database Operations**: statistics, info, health check
 **Batch Operations**: execute multiple queries in one call
 **Auto-discovery**: Consul service discovery built-in
 **Context Managers**: automatic resource cleanup
 **Error Handling**: graceful error propagation
 **Type Conversion**: automatic handling of graph types

---

## Advanced Patterns

### Multi-Database Support
```python
# Work with different Neo4j databases
with Neo4jClient() as client:
    # Default database
    client.create_node(['User'], {'name': 'Alice'})

    # Specific database
    client.create_node(['Product'], {'sku': 'ABC123'}, database='catalog')
```

### Complex Graph Queries
```python
# Recommendation engine
results = client.run_cypher(
    """
    MATCH (user:User {id: $user_id})
    MATCH (user)-[:PURCHASED]->(p1:Product)<-[:PURCHASED]-(other:User)
    MATCH (other)-[:PURCHASED]->(p2:Product)
    WHERE NOT (user)-[:PURCHASED]->(p2)
    RETURN p2.name as product,
           p2.price as price,
           count(DISTINCT other) as common_buyers
    ORDER BY common_buyers DESC
    LIMIT 10
    """,
    params={'user_id': 'user123'}
)
```

### Transaction Pattern (via Cypher)
```python
# Multi-step operations in single transaction
result = client.run_cypher_write(
    """
    // Create user
    CREATE (u:User {username: $username, email: $email})

    // Create initial settings
    CREATE (s:Settings {theme: 'dark', notifications: true})
    CREATE (u)-[:HAS_SETTINGS]->(s)

    // Link to default groups
    MATCH (g:Group) WHERE g.name IN ['Users', 'NewMembers']
    CREATE (u)-[:MEMBER_OF]->(g)

    RETURN u
    """,
    params={'username': 'newuser', 'email': 'user@example.com'}
)
```

### Graph Analytics
```python
# Find influential users (high degree centrality)
results = client.run_cypher(
    """
    MATCH (u:User)
    RETURN u.username as username,
           size((u)-[:FRIENDS]-()) as friend_count
    ORDER BY friend_count DESC
    LIMIT 10
    """
)

# Community detection (via Cypher)
results = client.run_cypher(
    """
    CALL gds.louvain.stream('socialNetwork')
    YIELD nodeId, communityId
    RETURN gds.util.asNode(nodeId).username as username,
           communityId
    ORDER BY communityId
    """
)
```

### Relationship Filtering
```python
# Find relationships of specific type
results = client.run_cypher(
    """
    MATCH (user:User)-[r:FRIENDS]->()
    WHERE id(user) = $user_id
    RETURN r
    """,
    params={'user_id': user_id}
)
```

---

## Error Handling Best Practices

```python
from isa_common.neo4j_client import Neo4jClient

try:
    with Neo4jClient() as client:
        # Your operations
        node_id = client.create_node(['User'], {'name': 'Alice'})

except ConnectionError as e:
    # Service unavailable
    print(f"Cannot connect to Neo4j service: {e}")

except ValueError as e:
    # Invalid parameters or response
    print(f"Invalid operation: {e}")

except Exception as e:
    # Other errors
    print(f"Error: {e}")
```

---

## Performance Tips

1. **Use Batch Operations**: Group multiple queries together
```python
# Instead of 3 separate calls:
client.create_node(['User'], {'name': 'Alice'})
client.create_node(['User'], {'name': 'Bob'})
client.create_node(['User'], {'name': 'Charlie'})

# Use batch:
queries = [
    {'cypher': 'CREATE (n:User {name: $name}) RETURN n', 'params': {'name': name}}
    for name in ['Alice', 'Bob', 'Charlie']
]
client.run_cypher_batch(queries)
```

2. **Use Indexes**: Create indexes for frequently queried properties
```python
# Create index on username for fast lookups
client.run_cypher("CREATE INDEX user_username IF NOT EXISTS FOR (u:User) ON (u.username)")
```

3. **Limit Result Sets**: Always use LIMIT in production queries
```python
# Good
results = client.run_cypher(
    "MATCH (u:User) WHERE u.age > $age RETURN u LIMIT 100",
    params={'age': 25}
)

# Bad (can return millions of rows)
results = client.run_cypher("MATCH (u:User) WHERE u.age > $age RETURN u", params={'age': 25})
```

4. **Use Parameterized Queries**: Avoid string concatenation
```python
# Good (safe and fast)
client.run_cypher("MATCH (u:User {username: $user}) RETURN u", params={'user': username})

# Bad (SQL injection risk, no query plan caching)
client.run_cypher(f"MATCH (u:User {{username: '{username}'}}) RETURN u")
```

---

## Real-World Use Cases

### Knowledge Graph
```python
class KnowledgeGraphService:
    def __init__(self):
        self.client = Neo4jClient(user_id='knowledge-graph')

    def add_concept(self, name, category, description):
        return self.client.create_node(['Concept'], {
            'name': name,
            'category': category,
            'description': description
        })

    def link_concepts(self, concept1_id, concept2_id, relationship_type):
        return self.client.create_relationship(
            concept1_id, concept2_id, relationship_type,
            {'created_at': datetime.now().isoformat()}
        )

    def find_related_concepts(self, concept_id, max_depth=2):
        return self.client.run_cypher(
            """
            MATCH (c:Concept)-[*1..%s]-(related:Concept)
            WHERE id(c) = $concept_id
            RETURN DISTINCT related.name as name,
                   related.category as category
            LIMIT 20
            """ % max_depth,
            params={'concept_id': concept_id}
        )
```

### Recommendation Engine
```python
class RecommendationService:
    def __init__(self):
        self.client = Neo4jClient(user_id='recommendations')

    def collaborative_filtering(self, user_id):
        # Find items liked by similar users
        return self.client.run_cypher(
            """
            MATCH (user:User)-[:LIKED]->(item:Item)<-[:LIKED]-(similar:User)
            WHERE id(user) = $user_id
            MATCH (similar)-[:LIKED]->(rec:Item)
            WHERE NOT (user)-[:LIKED]->(rec)
            RETURN rec.name as name,
                   rec.category as category,
                   count(DISTINCT similar) as score
            ORDER BY score DESC
            LIMIT 10
            """,
            params={'user_id': user_id}
        )
```

### Organization Hierarchy
```python
class OrgChartService:
    def __init__(self):
        self.client = Neo4jClient(user_id='org-chart')

    def add_employee(self, name, title, department):
        return self.client.create_node(['Employee'], {
            'name': name,
            'title': title,
            'department': department
        })

    def set_manager(self, employee_id, manager_id):
        return self.client.create_relationship(
            employee_id, manager_id, 'REPORTS_TO', {}
        )

    def get_org_hierarchy(self, root_id):
        return self.client.run_cypher(
            """
            MATCH path = (root:Employee)<-[:REPORTS_TO*]-(subordinate:Employee)
            WHERE id(root) = $root_id
            RETURN subordinate.name as name,
                   subordinate.title as title,
                   length(path) as level
            ORDER BY level, name
            """,
            params={'root_id': root_id}
        )
```

---

## Bottom Line

Instead of writing 500+ lines of gRPC boilerplate, connection handling, and error management...

**You write 5 lines and ship features.** <¯

The Neo4j client gives you:
- **Production-ready** graph database operations out of the box
- **Cypher query** execution with parameterization
- **Graph traversal** for path finding and relationship queries
- **Node and relationship** CRUD operations
- **Batch operations** for performance
- **Auto-cleanup** via context managers
- **Type-safe** results with proper graph type handling
- **Service discovery** via Consul integration

Just pip install and focus on your graph data models and business logic!
