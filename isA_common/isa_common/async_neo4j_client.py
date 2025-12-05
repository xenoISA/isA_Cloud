#!/usr/bin/env python3
"""
Async Neo4j gRPC Client
High-performance async Neo4j graph database client using grpc.aio

Performance Benefits:
- True async I/O without GIL blocking
- Concurrent query execution
- Memory-efficient connection pooling
"""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
from google.protobuf.struct_pb2 import Struct, Value
from .async_base_client import AsyncBaseGRPCClient
from .proto import neo4j_service_pb2, neo4j_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class AsyncNeo4jClient(AsyncBaseGRPCClient):
    """Async Neo4j gRPC client for high-performance graph operations."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        lazy_connect: bool = True,
        enable_compression: bool = True,
        enable_retry: bool = True,
        consul_registry: Optional['ConsulRegistry'] = None,
        service_name_override: Optional[str] = None
    ):
        """
        Initialize async Neo4j client.

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional)
        """
        super().__init__(
            host=host,
            port=port,
            user_id=user_id,
            lazy_connect=lazy_connect,
            enable_compression=enable_compression,
            enable_retry=enable_retry,
            consul_registry=consul_registry,
            service_name_override=service_name_override
        )

    def _create_stub(self):
        """Create Neo4j service stub."""
        return neo4j_service_pb2_grpc.Neo4jServiceStub(self.channel)

    def service_name(self) -> str:
        return "Neo4j"

    def default_port(self) -> int:
        return 50063

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()
            request = neo4j_service_pb2.Neo4jHealthCheckRequest()
            response = await self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'version': response.version,
                'edition': response.edition
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    # ============================================
    # Cypher Query Operations
    # ============================================

    async def run_cypher(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
        database: str = 'neo4j'
    ) -> Optional[List[Dict]]:
        """Execute Cypher query.

        Args:
            cypher: Cypher query statement
            params: Query parameters
            database: Database name (default: neo4j)

        Returns:
            List of result records as dictionaries
        """
        try:
            await self._ensure_connected()

            proto_params = {}
            if params:
                for k, v in params.items():
                    val = Value()
                    if isinstance(v, str):
                        val.string_value = v
                    elif isinstance(v, int):
                        val.number_value = float(v)
                    elif isinstance(v, float):
                        val.number_value = v
                    elif isinstance(v, bool):
                        val.bool_value = v
                    proto_params[k] = val

            request = neo4j_service_pb2.RunCypherRequest(
                cypher=cypher,
                parameters=proto_params,
                database=database
            )

            response = await self.stub.RunCypher(request)

            if response.metadata.success:
                records = []
                for row in response.rows:
                    record = {}
                    for field_name, field_value in row.fields.items():
                        kind = field_value.WhichOneof('kind')
                        if kind == 'null_value':
                            record[field_name] = None
                        elif kind == 'number_value':
                            num_val = field_value.number_value
                            if num_val == int(num_val):
                                record[field_name] = int(num_val)
                            else:
                                record[field_name] = num_val
                        elif kind == 'string_value':
                            record[field_name] = field_value.string_value
                        elif kind == 'bool_value':
                            record[field_name] = field_value.bool_value
                        elif kind == 'struct_value':
                            from google.protobuf.json_format import MessageToDict
                            record[field_name] = MessageToDict(field_value.struct_value)
                        elif kind == 'list_value':
                            from google.protobuf.json_format import MessageToDict
                            record[field_name] = MessageToDict(field_value.list_value)
                        else:
                            record[field_name] = None
                    records.append(record)
                return records
            return None

        except Exception as e:
            return self.handle_error(e, "Run Cypher")

    # ============================================
    # Node Operations
    # ============================================

    async def create_node(
        self,
        labels: List[str],
        properties: Optional[Dict[str, Any]] = None,
        database: str = 'neo4j'
    ) -> Optional[int]:
        """Create graph node.

        Args:
            labels: Node labels
            properties: Node properties
            database: Database name

        Returns:
            Node ID if successful
        """
        try:
            await self._ensure_connected()

            proto_props = Struct()
            if properties:
                for k, v in properties.items():
                    proto_props[k] = v

            request = neo4j_service_pb2.CreateNodeRequest(
                labels=labels,
                properties=proto_props,
                database=database
            )

            response = await self.stub.CreateNode(request)

            if response.metadata.success:
                return response.node.id
            return None

        except Exception as e:
            return self.handle_error(e, "Create node")

    async def get_node(self, node_id: int, database: str = 'neo4j') -> Optional[Dict]:
        """Get node by ID.

        Args:
            node_id: Node ID
            database: Database name

        Returns:
            Node data with labels and properties
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.GetNodeRequest(
                node_id=node_id,
                database=database
            )

            response = await self.stub.GetNode(request)

            if response.metadata.success and response.found:
                return {
                    'id': int(response.node.id),
                    'labels': list(response.node.labels),
                    'properties': self._proto_struct_to_dict(response.node.properties)
                }
            return None

        except Exception as e:
            return self.handle_error(e, "Get node")

    async def update_node(
        self,
        node_id: int,
        properties: Dict[str, Any],
        database: str = 'neo4j'
    ) -> Optional[bool]:
        """Update node properties.

        Args:
            node_id: Node ID
            properties: Properties to update
            database: Database name

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            proto_props = Struct()
            for k, v in properties.items():
                proto_props[k] = v

            request = neo4j_service_pb2.UpdateNodeRequest(
                node_id=node_id,
                properties=proto_props,
                database=database
            )

            response = await self.stub.UpdateNode(request)

            if response.metadata.success:
                return True
            return None

        except Exception as e:
            return self.handle_error(e, "Update node")

    async def delete_node(
        self,
        node_id: int,
        detach: bool = False,
        database: str = 'neo4j'
    ) -> Optional[bool]:
        """Delete node.

        Args:
            node_id: Node ID
            detach: Detach and delete (remove relationships first)
            database: Database name

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.DeleteNodeRequest(
                node_id=node_id,
                detach=detach,
                database=database
            )

            response = await self.stub.DeleteNode(request)

            if response.metadata.success:
                return True
            return None

        except Exception as e:
            return self.handle_error(e, "Delete node")

    async def find_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        database: str = 'neo4j'
    ) -> Optional[List[Dict]]:
        """Find nodes by labels and properties.

        Args:
            labels: Node labels to match
            properties: Properties to match
            limit: Maximum number of nodes to return
            database: Database name

        Returns:
            List of matching nodes
        """
        try:
            await self._ensure_connected()

            proto_props = Struct()
            if properties:
                for k, v in properties.items():
                    proto_props[k] = v

            label = labels[0] if labels and len(labels) > 0 else None

            request = neo4j_service_pb2.FindNodesRequest(
                label=label,
                properties=proto_props,
                limit=limit,
                database=database
            )

            response = await self.stub.FindNodes(request)

            if response.metadata.success:
                return [
                    {
                        'id': node.id,
                        'labels': list(node.labels),
                        'properties': dict(node.properties)
                    }
                    for node in response.nodes
                ]
            return None

        except Exception as e:
            return self.handle_error(e, "Find nodes")

    # ============================================
    # Relationship Operations
    # ============================================

    async def create_relationship(
        self,
        start_node_id: int,
        end_node_id: int,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        database: str = 'neo4j'
    ) -> Optional[int]:
        """Create relationship between nodes.

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            rel_type: Relationship type
            properties: Relationship properties
            database: Database name

        Returns:
            Relationship ID if successful
        """
        try:
            await self._ensure_connected()

            proto_props = Struct()
            if properties:
                for k, v in properties.items():
                    proto_props[k] = v

            request = neo4j_service_pb2.CreateRelationshipRequest(
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                type=rel_type,
                properties=proto_props,
                database=database
            )

            response = await self.stub.CreateRelationship(request)

            if response.metadata.success:
                return response.relationship.id
            return None

        except Exception as e:
            return self.handle_error(e, "Create relationship")

    async def get_relationship(self, rel_id: int, database: str = 'neo4j') -> Optional[Dict]:
        """Get relationship by ID.

        Args:
            rel_id: Relationship ID
            database: Database name

        Returns:
            Relationship data
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.GetRelationshipRequest(
                relationship_id=rel_id,
                database=database
            )

            response = await self.stub.GetRelationship(request)

            if response.metadata.success and response.found:
                return {
                    'id': int(response.relationship.id),
                    'start_node_id': int(response.relationship.start_node_id),
                    'end_node_id': int(response.relationship.end_node_id),
                    'type': response.relationship.type,
                    'properties': self._proto_struct_to_dict(response.relationship.properties)
                }
            return None

        except Exception as e:
            return self.handle_error(e, "Get relationship")

    async def delete_relationship(self, rel_id: int, database: str = 'neo4j') -> Optional[bool]:
        """Delete relationship.

        Args:
            rel_id: Relationship ID
            database: Database name

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.DeleteRelationshipRequest(
                relationship_id=rel_id,
                database=database
            )

            response = await self.stub.DeleteRelationship(request)

            if response.metadata.success:
                return True
            return None

        except Exception as e:
            return self.handle_error(e, "Delete relationship")

    # ============================================
    # Path Operations
    # ============================================

    async def get_path(
        self,
        start_node_id: int,
        end_node_id: int,
        max_depth: int = 5,
        database: str = 'neo4j'
    ) -> Optional[Dict]:
        """Get path between two nodes.

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            max_depth: Maximum path depth
            database: Database name

        Returns:
            Path information with nodes and relationships
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.GetPathRequest(
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                max_depth=max_depth,
                database=database
            )

            response = await self.stub.GetPath(request)

            if response.metadata.success and response.found:
                nodes = [
                    {
                        'id': node.id,
                        'labels': list(node.labels),
                        'properties': dict(node.properties)
                    }
                    for node in response.path.nodes
                ]

                relationships = [
                    {
                        'id': rel.id,
                        'start_node_id': rel.start_node_id,
                        'end_node_id': rel.end_node_id,
                        'type': rel.type,
                        'properties': dict(rel.properties)
                    }
                    for rel in response.path.relationships
                ]

                return {
                    'length': response.path.length,
                    'nodes': nodes,
                    'relationships': relationships
                }
            return None

        except Exception as e:
            return self.handle_error(e, "Get path")

    async def shortest_path(
        self,
        start_node_id: int,
        end_node_id: int,
        max_depth: int = 5,
        database: str = 'neo4j'
    ) -> Optional[Dict]:
        """Get shortest path between two nodes.

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            max_depth: Maximum path depth
            database: Database name

        Returns:
            Shortest path information
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.GetShortestPathRequest(
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                max_depth=max_depth,
                database=database
            )

            response = await self.stub.GetShortestPath(request)

            if response.metadata.success and response.found:
                nodes = [
                    {
                        'id': node.id,
                        'labels': list(node.labels),
                        'properties': dict(node.properties)
                    }
                    for node in response.path.nodes
                ]

                relationships = [
                    {
                        'id': rel.id,
                        'start_node_id': rel.start_node_id,
                        'end_node_id': rel.end_node_id,
                        'type': rel.type,
                        'properties': dict(rel.properties)
                    }
                    for rel in response.path.relationships
                ]

                return {
                    'length': response.path.length,
                    'nodes': nodes,
                    'relationships': relationships
                }
            return None

        except Exception as e:
            return self.handle_error(e, "Shortest path")

    # ============================================
    # Graph Algorithms
    # ============================================

    async def pagerank(self, database: str = 'neo4j') -> Optional[List[Dict]]:
        """Run PageRank algorithm on the graph.

        Args:
            database: Database name

        Returns:
            List of nodes with their PageRank scores
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.PageRankRequest(database=database)
            response = await self.stub.PageRank(request)

            if response.metadata.success:
                return [
                    {'node_id': result.node_id, 'score': result.score}
                    for result in response.results
                ]
            return None

        except Exception as e:
            return self.handle_error(e, "PageRank")

    async def betweenness_centrality(self, database: str = 'neo4j') -> Optional[List[Dict]]:
        """Run Betweenness Centrality algorithm.

        Args:
            database: Database name

        Returns:
            List of nodes with their centrality scores
        """
        try:
            await self._ensure_connected()

            request = neo4j_service_pb2.BetweennessCentralityRequest(database=database)
            response = await self.stub.BetweennessCentrality(request)

            if response.metadata.success:
                return [
                    {'node_id': result.node_id, 'score': result.score}
                    for result in response.results
                ]
            return None

        except Exception as e:
            return self.handle_error(e, "Betweenness Centrality")

    # ============================================
    # Statistics
    # ============================================

    async def get_stats(self, database: str = 'neo4j') -> Optional[Dict]:
        """Get database statistics using Cypher query.

        Args:
            database: Database name

        Returns:
            Statistics dictionary
        """
        try:
            stats = {}

            # Count nodes
            node_result = await self.run_cypher("MATCH (n) RETURN count(n) as count", database=database)
            stats['node_count'] = node_result[0]['count'] if node_result else 0

            # Count relationships
            rel_result = await self.run_cypher("MATCH ()-[r]->() RETURN count(r) as count", database=database)
            stats['relationship_count'] = rel_result[0]['count'] if rel_result else 0

            return stats

        except Exception as e:
            return self.handle_error(e, "Get stats")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def run_cypher_many_concurrent(self, queries: List[Dict[str, Any]]) -> List[Optional[List[Dict]]]:
        """
        Execute multiple Cypher queries concurrently.

        Args:
            queries: List of {'cypher': str, 'params': dict, 'database': str} dicts

        Returns:
            List of results for each query
        """
        import asyncio

        async def execute_query(q: Dict) -> Optional[List[Dict]]:
            return await self.run_cypher(
                cypher=q.get('cypher', ''),
                params=q.get('params'),
                database=q.get('database', 'neo4j')
            )

        return await asyncio.gather(*[execute_query(q) for q in queries])

    async def create_nodes_concurrent(self, nodes: List[Dict[str, Any]]) -> List[Optional[int]]:
        """
        Create multiple nodes concurrently.

        Args:
            nodes: List of {'labels': list, 'properties': dict} dicts

        Returns:
            List of node IDs
        """
        import asyncio

        async def create_single(n: Dict) -> Optional[int]:
            return await self.create_node(
                labels=n.get('labels', []),
                properties=n.get('properties')
            )

        return await asyncio.gather(*[create_single(n) for n in nodes])


# Example usage
if __name__ == '__main__':
    import asyncio

    async def main():
        async with AsyncNeo4jClient(host='localhost', port=50063, user_id='test_user') as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Create nodes concurrently
            node_ids = await client.create_nodes_concurrent([
                {'labels': ['Person'], 'properties': {'name': 'Alice'}},
                {'labels': ['Person'], 'properties': {'name': 'Bob'}},
                {'labels': ['Person'], 'properties': {'name': 'Charlie'}}
            ])
            print(f"Created nodes: {node_ids}")

            # Run concurrent queries
            results = await client.run_cypher_many_concurrent([
                {'cypher': 'MATCH (n) RETURN count(n) as count'},
                {'cypher': 'MATCH ()-[r]->() RETURN count(r) as count'}
            ])
            print(f"Query results: {results}")

    asyncio.run(main())
