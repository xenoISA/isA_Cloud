#!/usr/bin/env python3
"""
Neo4j gRPC Client
Neo4j graph database client
"""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
from google.protobuf.struct_pb2 import Struct, Value
from .base_client import BaseGRPCClient
from .proto import neo4j_service_pb2, neo4j_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class Neo4jClient(BaseGRPCClient):
    """Neo4j gRPC client"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        Initialize Neo4j client

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'neo4j')
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
        """Create Neo4j service stub"""
        return neo4j_service_pb2_grpc.Neo4jServiceStub(self.channel)

    def service_name(self) -> str:
        return "Neo4j"

    def default_port(self) -> int:
        return 50063

    def health_check(self) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = neo4j_service_pb2.Neo4jHealthCheckRequest()
            response = self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'version': response.version,
                'edition': response.edition
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    def run_cypher(self, cypher: str, params: Optional[Dict[str, Any]] = None,
                   database: str = 'neo4j') -> Optional[List[Dict]]:
        """Execute Cypher query

        Args:
            cypher: Cypher query statement
            params: Query parameters
            database: Database name (default: neo4j)

        Returns:
            List of result records as dictionaries
        """
        try:
            self._ensure_connected()

            # Convert parameters to proto Value map
            proto_params = {}
            if params:
                from google.protobuf.struct_pb2 import Value
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

            response = self.stub.RunCypher(request)

            if response.metadata.success:
                # Convert rows to dictionary records
                records = []
                for row in response.rows:
                    # ResultRow.fields is a map<string, google.protobuf.Value>
                    record = {}
                    for field_name, field_value in row.fields.items():
                        # Convert proto Value to Python value
                        kind = field_value.WhichOneof('kind')
                        if kind == 'null_value':
                            record[field_name] = None
                        elif kind == 'number_value':
                            # Convert to int if it's a whole number (likely an ID)
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
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Run Cypher")

    def create_node(self, labels: List[str], properties: Optional[Dict[str, Any]] = None,
                   database: str = 'neo4j') -> Optional[int]:
        """Create graph node

        Args:
            labels: Node labels
            properties: Node properties
            database: Database name

        Returns:
            Node ID if successful
        """
        try:
            self._ensure_connected()

            proto_props = Struct()
            if properties:
                for k, v in properties.items():
                    proto_props[k] = v

            request = neo4j_service_pb2.CreateNodeRequest(
                labels=labels,
                properties=proto_props,
                database=database
            )

            response = self.stub.CreateNode(request)

            if response.metadata.success:
                node_id = response.node.id
                return node_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Create node")

    def get_node(self, node_id: int, database: str = 'neo4j') -> Optional[Dict]:
        """Get node by ID

        Args:
            node_id: Node ID
            database: Database name

        Returns:
            Node data with labels and properties
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.GetNodeRequest(
                node_id=node_id,
                database=database
            )

            response = self.stub.GetNode(request)

            if response.metadata.success and response.found:
                node = {
                    'id': int(response.node.id),
                    'labels': list(response.node.labels),
                    'properties': dict(response.node.properties)
                }
                return node
            elif not response.found:
                return None
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get node")

    def update_node(self, node_id: int, properties: Dict[str, Any],
                   database: str = 'neo4j') -> Optional[bool]:
        """Update node properties

        Args:
            node_id: Node ID
            properties: Properties to update
            database: Database name

        Returns:
            True if successful
        """
        try:
            self._ensure_connected()

            proto_props = Struct()
            for k, v in properties.items():
                proto_props[k] = v

            request = neo4j_service_pb2.UpdateNodeRequest(
                node_id=node_id,
                properties=proto_props,
                database=database
            )

            response = self.stub.UpdateNode(request)

            if response.metadata.success:
                return True
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Update node")

    def delete_node(self, node_id: int, detach: bool = False,
                   database: str = 'neo4j') -> Optional[bool]:
        """Delete node

        Args:
            node_id: Node ID
            detach: Detach and delete (remove relationships first)
            database: Database name

        Returns:
            True if successful
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.DeleteNodeRequest(
                node_id=node_id,
                detach=detach,
                database=database
            )

            response = self.stub.DeleteNode(request)

            if response.metadata.success:
                return True
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete node")

    def create_relationship(self, start_node_id: int, end_node_id: int, rel_type: str,
                          properties: Optional[Dict[str, Any]] = None,
                          database: str = 'neo4j') -> Optional[int]:
        """Create relationship between nodes

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
            self._ensure_connected()

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

            response = self.stub.CreateRelationship(request)

            if response.metadata.success:
                rel_id = response.relationship.id
                return rel_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Create relationship")

    def get_relationship(self, rel_id: int, database: str = 'neo4j') -> Optional[Dict]:
        """Get relationship by ID

        Args:
            rel_id: Relationship ID
            database: Database name

        Returns:
            Relationship data
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.GetRelationshipRequest(
                relationship_id=rel_id,
                database=database
            )

            response = self.stub.GetRelationship(request)

            if response.metadata.success and response.found:
                rel = {
                    'id': int(response.relationship.id),
                    'start_node_id': int(response.relationship.start_node_id),
                    'end_node_id': int(response.relationship.end_node_id),
                    'type': response.relationship.type,
                    'properties': dict(response.relationship.properties)
                }
                return rel
            elif not response.found:
                return None
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get relationship")

    def delete_relationship(self, rel_id: int, database: str = 'neo4j') -> Optional[bool]:
        """Delete relationship

        Args:
            rel_id: Relationship ID
            database: Database name

        Returns:
            True if successful
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.DeleteRelationshipRequest(
                relationship_id=rel_id,
                database=database
            )

            response = self.stub.DeleteRelationship(request)

            if response.metadata.success:
                return True
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete relationship")

    def find_nodes(self, labels: Optional[List[str]] = None, properties: Optional[Dict[str, Any]] = None,
                  limit: int = 100, database: str = 'neo4j') -> Optional[List[Dict]]:
        """Find nodes by labels and properties

        Args:
            labels: Node labels to match (will use first label if list provided)
            properties: Properties to match
            limit: Maximum number of nodes to return
            database: Database name

        Returns:
            List of matching nodes
        """
        try:
            self._ensure_connected()

            proto_props = Struct()
            if properties:
                for k, v in properties.items():
                    proto_props[k] = v

            # Proto accepts single label, not list
            label = labels[0] if labels and len(labels) > 0 else None

            request = neo4j_service_pb2.FindNodesRequest(
                label=label,
                properties=proto_props,
                limit=limit,
                database=database
            )

            response = self.stub.FindNodes(request)

            if response.metadata.success:
                nodes = []
                for node in response.nodes:
                    nodes.append({
                        'id': node.id,
                        'labels': list(node.labels),
                        'properties': dict(node.properties)
                    })
                return nodes
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Find nodes")

    def get_path(self, start_node_id: int, end_node_id: int, max_depth: int = 5,
                database: str = 'neo4j') -> Optional[Dict]:
        """Get path between two nodes

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            max_depth: Maximum path depth
            database: Database name

        Returns:
            Path information with nodes and relationships
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.GetPathRequest(
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                max_depth=max_depth,
                database=database
            )

            response = self.stub.GetPath(request)

            if response.metadata.success and response.found:
                nodes = []
                for node in response.path.nodes:
                    nodes.append({
                        'id': node.id,
                        'labels': list(node.labels),
                        'properties': dict(node.properties)
                    })

                relationships = []
                for rel in response.path.relationships:
                    relationships.append({
                        'id': rel.id,
                        'start_node_id': rel.start_node_id,
                        'end_node_id': rel.end_node_id,
                        'type': rel.type,
                        'properties': dict(rel.properties)
                    })

                path = {
                    'length': response.path.length,
                    'nodes': nodes,
                    'relationships': relationships
                }
                return path
            elif not response.found:
                return None
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get path")

    def shortest_path(self, start_node_id: int, end_node_id: int, max_depth: int = 5,
                     database: str = 'neo4j') -> Optional[Dict]:
        """Get shortest path between two nodes

        Args:
            start_node_id: Start node ID
            end_node_id: End node ID
            max_depth: Maximum path depth
            database: Database name

        Returns:
            Shortest path information
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.GetShortestPathRequest(
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                max_depth=max_depth,
                database=database
            )

            response = self.stub.GetShortestPath(request)

            if response.metadata.success and response.found:
                nodes = []
                for node in response.path.nodes:
                    nodes.append({
                        'id': node.id,
                        'labels': list(node.labels),
                        'properties': dict(node.properties)
                    })

                relationships = []
                for rel in response.path.relationships:
                    relationships.append({
                        'id': rel.id,
                        'start_node_id': rel.start_node_id,
                        'end_node_id': rel.end_node_id,
                        'type': rel.type,
                        'properties': dict(rel.properties)
                    })

                path = {
                    'length': response.path.length,
                    'nodes': nodes,
                    'relationships': relationships
                }
                return path
            elif not response.found:
                return None
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Shortest path")

    def pagerank(self, database: str = 'neo4j') -> Optional[List[Dict]]:
        """Run PageRank algorithm on the graph

        Args:
            database: Database name

        Returns:
            List of nodes with their PageRank scores
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.PageRankRequest(database=database)
            response = self.stub.PageRank(request)

            if response.metadata.success:
                results = []
                for result in response.results:
                    results.append({
                        'node_id': result.node_id,
                        'score': result.score
                    })
                return results
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "PageRank")

    def betweenness_centrality(self, database: str = 'neo4j') -> Optional[List[Dict]]:
        """Run Betweenness Centrality algorithm

        Args:
            database: Database name

        Returns:
            List of nodes with their centrality scores
        """
        try:
            self._ensure_connected()

            request = neo4j_service_pb2.BetweennessCentralityRequest(database=database)
            response = self.stub.BetweennessCentrality(request)

            if response.metadata.success:
                results = []
                for result in response.results:
                    results.append({
                        'node_id': result.node_id,
                        'score': result.score
                    })
                return results
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Betweenness Centrality")

    def get_stats(self, database: str = 'neo4j') -> Optional[Dict]:
        """Get database statistics using Cypher query

        Args:
            database: Database name

        Returns:
            Statistics dictionary
        """
        try:
            # Use Cypher to get basic stats since GetStats RPC doesn't exist in proto
            stats = {}

            # Count nodes
            node_result = self.run_cypher("MATCH (n) RETURN count(n) as count", database=database)
            stats['node_count'] = node_result[0]['count'] if node_result else 0

            # Count relationships
            rel_result = self.run_cypher("MATCH ()-[r]->() RETURN count(r) as count", database=database)
            stats['relationship_count'] = rel_result[0]['count'] if rel_result else 0

            return stats

        except Exception as e:
            return self.handle_error(e, "Get stats")
