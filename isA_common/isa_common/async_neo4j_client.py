#!/usr/bin/env python3
"""
Async Neo4j Native Client
High-performance async Neo4j graph database client using the native Neo4j Python driver.

This client connects directly to Neo4j using the official neo4j Python driver,
providing full support for all Neo4j features including:
- Vector similarity search
- Full Cypher query support (read and write)
- Transaction management
- Connection pooling
"""

import os
from typing import List, Dict, Optional, Any
from contextlib import asynccontextmanager

# Neo4j native async driver
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

from .async_base_client import AsyncBaseClient


class AsyncNeo4jClient(AsyncBaseClient):
    """
    Async Neo4j client using the native Neo4j Python driver.

    Provides direct connection to Neo4j with full feature support including
    vector similarity search, write operations, and graph algorithms.
    """

    # Class-level configuration
    SERVICE_NAME = "Neo4j"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 7687
    ENV_PREFIX = "NEO4J"
    # No TENANT_SEPARATOR - Neo4j uses node properties for multi-tenancy

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = 'neo4j',
        **kwargs
    ):
        """
        Initialize async Neo4j client with native driver.

        Args:
            uri: Full Neo4j URI (overrides host/port if provided)
            username: Neo4j username (default: from NEO4J_USER env or 'neo4j')
            password: Neo4j password (default: from NEO4J_PASSWORD env)
            database: Default database name (default: 'neo4j')
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        # Build URI from host/port or use provided URI
        if uri:
            self._uri = uri
        else:
            self._uri = f"bolt://{self._host}:{self._port}"

        # Get credentials from env or parameters
        self._username = username or os.getenv('NEO4J_USER', 'neo4j')
        self._password = password or os.getenv('NEO4J_PASSWORD', 'neo4j')
        self._database = database

        # Driver state
        self._driver = None

    async def _connect(self) -> None:
        """Establish Neo4j driver connection."""
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._username, self._password),
                max_connection_pool_size=50,
                connection_acquisition_timeout=30.0
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            self._logger.info(f"Connected to Neo4j at {self._uri}")
        except AuthError as e:
            self._logger.error(f"Neo4j authentication failed: {e}")
            raise
        except ServiceUnavailable as e:
            self._logger.error(f"Neo4j service unavailable: {e}")
            raise

    async def _disconnect(self) -> None:
        """Close Neo4j driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None

    @asynccontextmanager
    async def session(self, database: Optional[str] = None):
        """Get an async session context manager."""
        await self._ensure_connected()
        db = database or self._database
        session = self._driver.session(database=db)
        try:
            yield session
        finally:
            await session.close()

    def handle_error(self, error: Exception, operation: str) -> None:
        """Handle and log errors."""
        logger.error(f"Neo4j {operation} failed: {error}")
        return None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()

            async with self.session() as session:
                result = await session.run("CALL dbms.components() YIELD name, versions, edition")
                record = await result.single()

                if record:
                    return {
                        'healthy': True,
                        'version': record['versions'][0] if record['versions'] else 'unknown',
                        'edition': record['edition'],
                        'name': record['name']
                    }
            return {'healthy': False}

        except Exception as e:
            return self.handle_error(e, "Health check")

    # ============================================
    # Cypher Query Operations
    # ============================================

    async def run_cypher(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
        database: str = None
    ) -> Optional[List[Dict]]:
        """Execute Cypher query.

        Args:
            cypher: Cypher query statement
            params: Query parameters
            database: Database name (default: instance default)

        Returns:
            List of result records as dictionaries
        """
        try:
            await self._ensure_connected()

            async with self.session(database) as session:
                result = await session.run(cypher, params or {})
                records = []
                async for record in result:
                    records.append(dict(record))
                return records

        except Exception as e:
            return self.handle_error(e, "Run Cypher")

    # ============================================
    # Node Operations
    # ============================================

    async def create_node(
        self,
        labels: List[str],
        properties: Optional[Dict[str, Any]] = None,
        database: str = None
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

            labels_str = ':'.join(labels) if labels else ''
            cypher = f"CREATE (n:{labels_str} $props) RETURN elementId(n) as id, id(n) as node_id"

            async with self.session(database) as session:
                result = await session.run(cypher, props=properties or {})
                record = await result.single()
                if record:
                    return record['node_id']
            return None

        except Exception as e:
            return self.handle_error(e, "Create node")

    async def get_node(self, node_id: int, database: str = None) -> Optional[Dict]:
        """Get node by ID.

        Args:
            node_id: Node ID
            database: Database name

        Returns:
            Node data with labels and properties
        """
        try:
            await self._ensure_connected()

            cypher = "MATCH (n) WHERE id(n) = $node_id RETURN n, labels(n) as labels, id(n) as id"

            async with self.session(database) as session:
                result = await session.run(cypher, node_id=node_id)
                record = await result.single()

                if record:
                    node = record['n']
                    return {
                        'id': record['id'],
                        'labels': record['labels'],
                        'properties': dict(node)
                    }
            return None

        except Exception as e:
            return self.handle_error(e, "Get node")

    async def update_node(
        self,
        node_id: int,
        properties: Dict[str, Any],
        database: str = None
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

            cypher = "MATCH (n) WHERE id(n) = $node_id SET n += $props RETURN n"

            async with self.session(database) as session:
                result = await session.run(cypher, node_id=node_id, props=properties)
                record = await result.single()
                return record is not None

        except Exception as e:
            return self.handle_error(e, "Update node")

    async def delete_node(
        self,
        node_id: int,
        detach: bool = False,
        database: str = None
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

            if detach:
                cypher = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n"
            else:
                cypher = "MATCH (n) WHERE id(n) = $node_id DELETE n"

            async with self.session(database) as session:
                await session.run(cypher, node_id=node_id)
                return True

        except Exception as e:
            return self.handle_error(e, "Delete node")

    async def find_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        database: str = None
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

            # Build label match
            label_str = ':'.join(labels) if labels else ''
            label_match = f":{label_str}" if label_str else ''

            # Build property conditions
            prop_conditions = []
            params = {'limit': limit}

            if properties:
                for i, (key, value) in enumerate(properties.items()):
                    param_name = f"prop_{i}"
                    prop_conditions.append(f"n.{key} = ${param_name}")
                    params[param_name] = value

            where_clause = f"WHERE {' AND '.join(prop_conditions)}" if prop_conditions else ""

            cypher = f"""
                MATCH (n{label_match})
                {where_clause}
                RETURN n, labels(n) as labels, id(n) as id
                LIMIT $limit
            """

            async with self.session(database) as session:
                result = await session.run(cypher, **params)
                nodes = []
                async for record in result:
                    node = record['n']
                    nodes.append({
                        'id': record['id'],
                        'labels': record['labels'],
                        'properties': dict(node)
                    })
                return nodes

        except Exception as e:
            return self.handle_error(e, "Find nodes")

    async def merge_node(
        self,
        labels: List[str],
        match_properties: Dict[str, Any],
        set_properties: Optional[Dict[str, Any]] = None,
        database: str = None
    ) -> Optional[Dict]:
        """Merge (create or match) a node.

        Args:
            labels: Node labels
            match_properties: Properties to match on
            set_properties: Additional properties to set
            database: Database name

        Returns:
            Node data with created flag
        """
        try:
            await self._ensure_connected()

            labels_str = ':'.join(labels) if labels else ''

            # Build merge properties
            merge_props = ', '.join([f"{k}: ${k}" for k in match_properties.keys()])

            cypher = f"""
                MERGE (n:{labels_str} {{{merge_props}}})
                ON CREATE SET n += $set_props, n._created = true
                ON MATCH SET n += $set_props, n._created = false
                RETURN n, id(n) as id, labels(n) as labels, n._created as created
            """

            params = {**match_properties, 'set_props': set_properties or {}}

            async with self.session(database) as session:
                result = await session.run(cypher, **params)
                record = await result.single()

                if record:
                    node = record['n']
                    node_dict = dict(node)
                    created = node_dict.pop('_created', False)
                    return {
                        'id': record['id'],
                        'labels': record['labels'],
                        'properties': node_dict,
                        'created': created
                    }
            return None

        except Exception as e:
            return self.handle_error(e, "Merge node")

    # ============================================
    # Relationship Operations
    # ============================================

    async def create_relationship(
        self,
        start_node_id: int,
        end_node_id: int,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        database: str = None
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

            cypher = f"""
                MATCH (a), (b)
                WHERE id(a) = $start_id AND id(b) = $end_id
                CREATE (a)-[r:{rel_type} $props]->(b)
                RETURN id(r) as rel_id
            """

            async with self.session(database) as session:
                result = await session.run(
                    cypher,
                    start_id=start_node_id,
                    end_id=end_node_id,
                    props=properties or {}
                )
                record = await result.single()
                if record:
                    return record['rel_id']
            return None

        except Exception as e:
            return self.handle_error(e, "Create relationship")

    async def get_relationship(self, rel_id: int, database: str = None) -> Optional[Dict]:
        """Get relationship by ID.

        Args:
            rel_id: Relationship ID
            database: Database name

        Returns:
            Relationship data
        """
        try:
            await self._ensure_connected()

            cypher = """
                MATCH ()-[r]->()
                WHERE id(r) = $rel_id
                RETURN r, type(r) as type, id(r) as id,
                       id(startNode(r)) as start_node_id,
                       id(endNode(r)) as end_node_id
            """

            async with self.session(database) as session:
                result = await session.run(cypher, rel_id=rel_id)
                record = await result.single()

                if record:
                    return {
                        'id': record['id'],
                        'start_node_id': record['start_node_id'],
                        'end_node_id': record['end_node_id'],
                        'type': record['type'],
                        'properties': dict(record['r'])
                    }
            return None

        except Exception as e:
            return self.handle_error(e, "Get relationship")

    async def delete_relationship(self, rel_id: int, database: str = None) -> Optional[bool]:
        """Delete relationship.

        Args:
            rel_id: Relationship ID
            database: Database name

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            cypher = "MATCH ()-[r]->() WHERE id(r) = $rel_id DELETE r"

            async with self.session(database) as session:
                await session.run(cypher, rel_id=rel_id)
                return True

        except Exception as e:
            return self.handle_error(e, "Delete relationship")

    async def find_relationships(
        self,
        start_node_id: Optional[int] = None,
        end_node_id: Optional[int] = None,
        rel_type: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        database: str = None
    ) -> Optional[List[Dict]]:
        """Find relationships by criteria.

        Args:
            start_node_id: Filter by start node
            end_node_id: Filter by end node
            rel_type: Filter by relationship type
            properties: Filter by properties
            limit: Maximum results
            database: Database name

        Returns:
            List of matching relationships
        """
        try:
            await self._ensure_connected()

            # Build relationship type
            type_str = f":{rel_type}" if rel_type else ""

            # Build conditions
            conditions = []
            params = {'limit': limit}

            if start_node_id is not None:
                conditions.append("id(a) = $start_id")
                params['start_id'] = start_node_id
            if end_node_id is not None:
                conditions.append("id(b) = $end_id")
                params['end_id'] = end_node_id
            if properties:
                for i, (key, value) in enumerate(properties.items()):
                    param_name = f"prop_{i}"
                    conditions.append(f"r.{key} = ${param_name}")
                    params[param_name] = value

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            cypher = f"""
                MATCH (a)-[r{type_str}]->(b)
                {where_clause}
                RETURN r, type(r) as type, id(r) as id,
                       id(a) as start_node_id, id(b) as end_node_id
                LIMIT $limit
            """

            async with self.session(database) as session:
                result = await session.run(cypher, **params)
                relationships = []
                async for record in result:
                    relationships.append({
                        'id': record['id'],
                        'start_node_id': record['start_node_id'],
                        'end_node_id': record['end_node_id'],
                        'type': record['type'],
                        'properties': dict(record['r'])
                    })
                return relationships

        except Exception as e:
            return self.handle_error(e, "Find relationships")

    # ============================================
    # Vector Search Operations (NEW!)
    # ============================================

    async def vector_search(
        self,
        index_name: str,
        embedding: List[float],
        top_k: int = 10,
        similarity_threshold: float = 0.0,
        database: str = None
    ) -> Optional[List[Dict]]:
        """Perform vector similarity search using Neo4j vector index.

        Args:
            index_name: Name of the vector index (e.g., 'entity_embeddings')
            embedding: Query embedding vector
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0.0 to 1.0)
            database: Database name

        Returns:
            List of similar nodes with scores
        """
        try:
            await self._ensure_connected()

            cypher = """
                CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
                YIELD node, score
                WHERE score >= $threshold
                RETURN node, score, labels(node) as labels, id(node) as id
                ORDER BY score DESC
            """

            async with self.session(database) as session:
                result = await session.run(
                    cypher,
                    index_name=index_name,
                    top_k=top_k,
                    embedding=embedding,
                    threshold=similarity_threshold
                )
                results = []
                async for record in result:
                    node = record['node']
                    results.append({
                        'id': record['id'],
                        'labels': record['labels'],
                        'score': record['score'],
                        'properties': dict(node)
                    })
                return results

        except Exception as e:
            return self.handle_error(e, "Vector search")

    async def create_vector_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimensions: int = 1536,
        similarity_function: str = 'cosine',
        database: str = None
    ) -> Optional[bool]:
        """Create a vector index for similarity search.

        Args:
            index_name: Name for the new index
            label: Node label to index
            property_name: Property containing embeddings
            dimensions: Embedding dimensions (default: 1536 for OpenAI)
            similarity_function: 'cosine', 'euclidean', or 'dot_product'
            database: Database name

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            cypher = f"""
                CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                FOR (n:{label}) ON (n.{property_name})
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: $dimensions,
                    `vector.similarity_function`: $similarity_function
                }}}}
            """

            async with self.session(database) as session:
                await session.run(
                    cypher,
                    dimensions=dimensions,
                    similarity_function=similarity_function
                )
                return True

        except Exception as e:
            return self.handle_error(e, "Create vector index")

    async def list_vector_indexes(self, database: str = None) -> Optional[List[Dict]]:
        """List all vector indexes.

        Args:
            database: Database name

        Returns:
            List of vector index information
        """
        try:
            await self._ensure_connected()

            cypher = 'SHOW INDEXES WHERE type = "VECTOR"'

            async with self.session(database) as session:
                result = await session.run(cypher)
                indexes = []
                async for record in result:
                    indexes.append({
                        'name': record.get('name'),
                        'state': record.get('state'),
                        'labels': record.get('labelsOrTypes'),
                        'properties': record.get('properties'),
                        'population_percent': record.get('populationPercent')
                    })
                return indexes

        except Exception as e:
            return self.handle_error(e, "List vector indexes")

    # ============================================
    # Path Operations
    # ============================================

    async def get_path(
        self,
        start_node_id: int,
        end_node_id: int,
        max_depth: int = 5,
        database: str = None
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

            cypher = f"""
                MATCH path = (a)-[*1..{max_depth}]-(b)
                WHERE id(a) = $start_id AND id(b) = $end_id
                RETURN path, length(path) as length
                LIMIT 1
            """

            async with self.session(database) as session:
                result = await session.run(
                    cypher,
                    start_id=start_node_id,
                    end_id=end_node_id
                )
                record = await result.single()

                if record:
                    path = record['path']
                    return {
                        'length': record['length'],
                        'nodes': [
                            {
                                'id': node.id,
                                'labels': list(node.labels),
                                'properties': dict(node)
                            }
                            for node in path.nodes
                        ],
                        'relationships': [
                            {
                                'id': rel.id,
                                'type': rel.type,
                                'properties': dict(rel)
                            }
                            for rel in path.relationships
                        ]
                    }
            return None

        except Exception as e:
            return self.handle_error(e, "Get path")

    async def shortest_path(
        self,
        start_node_id: int,
        end_node_id: int,
        max_depth: int = 5,
        database: str = None
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

            cypher = f"""
                MATCH path = shortestPath((a)-[*1..{max_depth}]-(b))
                WHERE id(a) = $start_id AND id(b) = $end_id
                RETURN path, length(path) as length
            """

            async with self.session(database) as session:
                result = await session.run(
                    cypher,
                    start_id=start_node_id,
                    end_id=end_node_id
                )
                record = await result.single()

                if record:
                    path = record['path']
                    return {
                        'length': record['length'],
                        'nodes': [
                            {
                                'id': node.id,
                                'labels': list(node.labels),
                                'properties': dict(node)
                            }
                            for node in path.nodes
                        ],
                        'relationships': [
                            {
                                'id': rel.id,
                                'type': rel.type,
                                'properties': dict(rel)
                            }
                            for rel in path.relationships
                        ]
                    }
            return None

        except Exception as e:
            return self.handle_error(e, "Shortest path")

    # ============================================
    # Graph Algorithms
    # ============================================

    async def pagerank(
        self,
        label: Optional[str] = None,
        relationship_type: Optional[str] = None,
        max_iterations: int = 20,
        damping_factor: float = 0.85,
        database: str = None
    ) -> Optional[Dict[int, float]]:
        """Run PageRank algorithm on the graph.

        Note: Requires Neo4j Graph Data Science library.

        Args:
            label: Node label to run on
            relationship_type: Relationship type to consider
            max_iterations: Maximum iterations
            damping_factor: Damping factor
            database: Database name

        Returns:
            Dictionary of node_id -> PageRank score
        """
        try:
            await self._ensure_connected()

            # Build node and relationship projections
            node_proj = f'"{label}"' if label else '"*"'
            rel_proj = f'"{relationship_type}"' if relationship_type else '"*"'

            cypher = f"""
                CALL gds.pageRank.stream({{
                    nodeProjection: {node_proj},
                    relationshipProjection: {rel_proj},
                    maxIterations: $max_iter,
                    dampingFactor: $damping
                }})
                YIELD nodeId, score
                RETURN nodeId, score
            """

            async with self.session(database) as session:
                result = await session.run(
                    cypher,
                    max_iter=max_iterations,
                    damping=damping_factor
                )
                scores = {}
                async for record in result:
                    scores[record['nodeId']] = record['score']
                return scores

        except Exception as e:
            return self.handle_error(e, "PageRank")

    async def betweenness_centrality(
        self,
        label: Optional[str] = None,
        relationship_type: Optional[str] = None,
        database: str = None
    ) -> Optional[Dict[int, float]]:
        """Run Betweenness Centrality algorithm.

        Note: Requires Neo4j Graph Data Science library.

        Args:
            label: Node label
            relationship_type: Relationship type
            database: Database name

        Returns:
            Dictionary of node_id -> centrality score
        """
        try:
            await self._ensure_connected()

            node_proj = f'"{label}"' if label else '"*"'
            rel_proj = f'"{relationship_type}"' if relationship_type else '"*"'

            cypher = f"""
                CALL gds.betweenness.stream({{
                    nodeProjection: {node_proj},
                    relationshipProjection: {rel_proj}
                }})
                YIELD nodeId, score
                RETURN nodeId, score
            """

            async with self.session(database) as session:
                result = await session.run(cypher)
                scores = {}
                async for record in result:
                    scores[record['nodeId']] = record['score']
                return scores

        except Exception as e:
            return self.handle_error(e, "Betweenness Centrality")

    # ============================================
    # Statistics
    # ============================================

    async def get_stats(self, database: str = None) -> Optional[Dict]:
        """Get database statistics.

        Args:
            database: Database name

        Returns:
            Statistics dictionary
        """
        try:
            await self._ensure_connected()

            async with self.session(database) as session:
                # Count nodes
                result = await session.run("MATCH (n) RETURN count(n) as count")
                record = await result.single()
                node_count = record['count'] if record else 0

                # Count relationships
                result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
                record = await result.single()
                rel_count = record['count'] if record else 0

                # Count labels
                result = await session.run("CALL db.labels() YIELD label RETURN count(label) as count")
                record = await result.single()
                label_count = record['count'] if record else 0

                # Count relationship types
                result = await session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN count(relationshipType) as count")
                record = await result.single()
                rel_type_count = record['count'] if record else 0

                return {
                    'node_count': node_count,
                    'relationship_count': rel_count,
                    'label_count': label_count,
                    'relationship_type_count': rel_type_count
                }

        except Exception as e:
            return self.handle_error(e, "Get stats")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def run_cypher_many_concurrent(
        self,
        queries: List[Dict[str, Any]]
    ) -> List[Optional[List[Dict]]]:
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
                database=q.get('database')
            )

        return await asyncio.gather(*[execute_query(q) for q in queries])

    async def create_nodes_concurrent(
        self,
        nodes: List[Dict[str, Any]]
    ) -> List[Optional[int]]:
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

    # ============================================
    # Graph RAG Convenience Methods
    # ============================================

    async def ensure_graph_rag_indexes(
        self,
        dimensions: int = 1536,
        database: str = None
    ) -> bool:
        """Ensure Graph RAG vector indexes exist.

        Creates vector indexes for Entity, DocumentChunk, and Relationship
        nodes if they don't already exist.

        Args:
            dimensions: Embedding dimensions (default: 1536 for OpenAI)
            database: Database name

        Returns:
            True if indexes are ready
        """
        try:
            # Entity embeddings index
            await self.create_vector_index(
                index_name='entity_embeddings',
                label='Entity',
                property_name='embedding',
                dimensions=dimensions,
                database=database
            )

            # Document chunk embeddings index
            await self.create_vector_index(
                index_name='document_embeddings',
                label='DocumentChunk',
                property_name='embedding',
                dimensions=dimensions,
                database=database
            )

            # Attribute embeddings index
            await self.create_vector_index(
                index_name='attribute_embeddings',
                label='Attribute',
                property_name='embedding',
                dimensions=dimensions,
                database=database
            )

            logger.info("Graph RAG indexes ensured")
            return True

        except Exception as e:
            logger.warning(f"Could not ensure Graph RAG indexes: {e}")
            return False

    async def store_entity(
        self,
        name: str,
        entity_type: str,
        properties: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        user_id: Optional[str] = None,
        database: str = None
    ) -> Optional[Dict[str, Any]]:
        """Store an entity node for Graph RAG.

        Args:
            name: Entity name/text
            entity_type: Type of entity (e.g., 'PERSON', 'ORGANIZATION')
            properties: Additional properties
            embedding: Optional embedding vector
            user_id: Optional user ID for multi-tenancy
            database: Database name

        Returns:
            Dict with success status and node_id
        """
        try:
            from datetime import datetime

            entity_props = {
                'name': name,
                'entity_type': entity_type,
                'created_at': datetime.now().isoformat(),
                **(properties or {})
            }

            if user_id:
                entity_props['user_id'] = user_id
            if embedding:
                entity_props['embedding'] = embedding

            # Use merge to upsert by name
            result = await self.merge_node(
                labels=['Entity'],
                match_properties={'name': name},
                set_properties=entity_props,
                database=database
            )

            if result:
                return {
                    'success': True,
                    'node_id': result['id'],
                    'created': result.get('created', False),
                    'entity': entity_props
                }
            return {'success': False, 'error': 'Failed to store entity'}

        except Exception as e:
            logger.error(f"Failed to store entity {name}: {e}")
            return {'success': False, 'error': str(e)}

    async def store_relationship(
        self,
        source_entity: str,
        target_entity: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        user_id: Optional[str] = None,
        database: str = None
    ) -> Optional[Dict[str, Any]]:
        """Store a relationship between entities for Graph RAG.

        Args:
            source_entity: Source entity name
            target_entity: Target entity name
            relationship_type: Type of relationship
            properties: Additional properties
            embedding: Optional embedding vector
            user_id: Optional user ID for multi-tenancy
            database: Database name

        Returns:
            Dict with success status and relationship_id
        """
        try:
            from datetime import datetime

            # Find source and target entities
            source_nodes = await self.find_nodes(
                labels=['Entity'],
                properties={'name': source_entity},
                database=database
            )
            if not source_nodes:
                return {'success': False, 'error': f'Source entity not found: {source_entity}'}

            target_nodes = await self.find_nodes(
                labels=['Entity'],
                properties={'name': target_entity},
                database=database
            )
            if not target_nodes:
                return {'success': False, 'error': f'Target entity not found: {target_entity}'}

            rel_props = {
                'relationship_type': relationship_type,
                'created_at': datetime.now().isoformat(),
                **(properties or {})
            }

            if user_id:
                rel_props['user_id'] = user_id
            if embedding:
                rel_props['embedding'] = embedding

            # Create relationship
            rel_id = await self.create_relationship(
                start_node_id=source_nodes[0]['id'],
                end_node_id=target_nodes[0]['id'],
                rel_type='RELATES_TO',
                properties=rel_props,
                database=database
            )

            if rel_id is not None:
                return {
                    'success': True,
                    'relationship_id': rel_id,
                    'relationship': rel_props
                }
            return {'success': False, 'error': 'Failed to create relationship'}

        except Exception as e:
            logger.error(f"Failed to store relationship {source_entity} -> {target_entity}: {e}")
            return {'success': False, 'error': str(e)}

    async def store_document_chunk(
        self,
        chunk_id: str,
        text: str,
        properties: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        user_id: Optional[str] = None,
        database: str = None
    ) -> Optional[Dict[str, Any]]:
        """Store a document chunk node for Graph RAG.

        Args:
            chunk_id: Unique chunk identifier
            text: Document text content
            properties: Additional properties (source, page, etc.)
            embedding: Vector embedding of the text
            user_id: Optional user ID for multi-tenancy
            database: Database name

        Returns:
            Dict with success status
        """
        try:
            from datetime import datetime

            chunk_props = {
                'chunk_id': chunk_id,
                'text': text,
                'created_at': datetime.now().isoformat(),
                **(properties or {})
            }

            if user_id:
                chunk_props['user_id'] = user_id
            if embedding:
                chunk_props['embedding'] = embedding

            # Use merge to upsert by chunk_id
            result = await self.merge_node(
                labels=['DocumentChunk'],
                match_properties={'chunk_id': chunk_id},
                set_properties=chunk_props,
                database=database
            )

            if result:
                return {
                    'success': True,
                    'node_id': result['id'],
                    'chunk': chunk_props
                }
            return {'success': False, 'error': 'Failed to store document chunk'}

        except Exception as e:
            logger.error(f"Failed to store document chunk {chunk_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def store_attribute(
        self,
        entity_name: str,
        attribute_name: str,
        attribute_value: Any,
        attribute_type: str = 'TEXT',
        properties: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        database: str = None
    ) -> Optional[Dict[str, Any]]:
        """Store an attribute node linked to an entity.

        Args:
            entity_name: Name of the parent entity
            attribute_name: Attribute name
            attribute_value: Attribute value
            attribute_type: Type of attribute (TEXT, NUMBER, DATE, etc.)
            properties: Additional properties
            embedding: Optional embedding vector
            database: Database name

        Returns:
            Dict with success status
        """
        try:
            from datetime import datetime

            # Find parent entity
            entity_nodes = await self.find_nodes(
                labels=['Entity'],
                properties={'name': entity_name},
                database=database
            )
            if not entity_nodes:
                return {'success': False, 'error': f'Entity not found: {entity_name}'}

            entity_id = entity_nodes[0]['id']
            attr_id = f"{entity_name}_{attribute_name}"

            attr_props = {
                'attr_id': attr_id,
                'name': attribute_name,
                'value': str(attribute_value),
                'attribute_type': attribute_type,
                'created_at': datetime.now().isoformat(),
                **(properties or {})
            }

            if embedding:
                attr_props['embedding'] = embedding

            # Create or update attribute node
            result = await self.merge_node(
                labels=['Attribute'],
                match_properties={'attr_id': attr_id},
                set_properties=attr_props,
                database=database
            )

            if not result:
                return {'success': False, 'error': 'Failed to create attribute node'}

            attr_node_id = result['id']

            # Create HAS_ATTRIBUTE relationship if new
            if result.get('created', False):
                await self.create_relationship(
                    start_node_id=entity_id,
                    end_node_id=attr_node_id,
                    rel_type='HAS_ATTRIBUTE',
                    database=database
                )

            return {
                'success': True,
                'node_id': attr_node_id,
                'attribute': attr_props
            }

        except Exception as e:
            logger.error(f"Failed to store attribute {attribute_name}: {e}")
            return {'success': False, 'error': str(e)}

    async def search_entities(
        self,
        embedding: List[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        user_id: Optional[str] = None,
        database: str = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Search entities by vector similarity.

        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            user_id: Optional user ID filter
            database: Database name

        Returns:
            List of similar entities with scores
        """
        try:
            user_filter = "AND node.user_id = $user_id" if user_id else ""

            cypher = f"""
                CALL db.index.vector.queryNodes('entity_embeddings', $top_k, $embedding)
                YIELD node, score
                WHERE score >= $threshold {user_filter}
                RETURN node, score, labels(node) as labels, id(node) as id
                ORDER BY score DESC
            """

            params = {
                'embedding': embedding,
                'top_k': top_k,
                'threshold': similarity_threshold
            }
            if user_id:
                params['user_id'] = user_id

            async with self.session(database) as session:
                result = await session.run(cypher, **params)
                results = []
                async for record in result:
                    node = record['node']
                    results.append({
                        'id': record['id'],
                        'name': node.get('name'),
                        'entity_type': node.get('entity_type'),
                        'score': record['score'],
                        'properties': dict(node)
                    })
                return results

        except Exception as e:
            logger.error(f"Entity search failed: {e}")
            return []

    async def search_documents(
        self,
        embedding: List[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        user_id: Optional[str] = None,
        database: str = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Search document chunks by vector similarity.

        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            user_id: Optional user ID filter
            database: Database name

        Returns:
            List of similar document chunks with scores
        """
        try:
            user_filter = "AND node.user_id = $user_id" if user_id else ""

            cypher = f"""
                CALL db.index.vector.queryNodes('document_embeddings', $top_k, $embedding)
                YIELD node, score
                WHERE score >= $threshold {user_filter}
                RETURN node, score, id(node) as id
                ORDER BY score DESC
            """

            params = {
                'embedding': embedding,
                'top_k': top_k,
                'threshold': similarity_threshold
            }
            if user_id:
                params['user_id'] = user_id

            async with self.session(database) as session:
                result = await session.run(cypher, **params)
                results = []
                async for record in result:
                    node = record['node']
                    results.append({
                        'id': record['id'],
                        'chunk_id': node.get('chunk_id'),
                        'text': node.get('text'),
                        'score': record['score'],
                        'properties': dict(node)
                    })
                return results

        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []

    async def get_entity_neighbors(
        self,
        entity_name: str,
        max_depth: int = 2,
        limit: int = 50,
        database: str = None
    ) -> Optional[Dict[str, Any]]:
        """Get neighboring entities via graph traversal.

        Args:
            entity_name: Name of the starting entity
            max_depth: Maximum traversal depth
            limit: Maximum number of neighbors
            database: Database name

        Returns:
            Dict with entity and its neighbors
        """
        try:
            cypher = f"""
                MATCH (e:Entity {{name: $entity_name}})
                OPTIONAL MATCH path = (e)-[*1..{max_depth}]-(neighbor:Entity)
                WHERE neighbor <> e
                RETURN DISTINCT neighbor, length(path) as distance
                ORDER BY distance
                LIMIT $limit
            """

            async with self.session(database) as session:
                result = await session.run(
                    cypher,
                    entity_name=entity_name,
                    limit=limit
                )
                neighbors = []
                async for record in result:
                    if record['neighbor']:
                        neighbor = record['neighbor']
                        neighbors.append({
                            'name': neighbor.get('name'),
                            'entity_type': neighbor.get('entity_type'),
                            'distance': record['distance'],
                            'properties': dict(neighbor)
                        })

                return {
                    'entity': entity_name,
                    'neighbors': neighbors,
                    'count': len(neighbors)
                }

        except Exception as e:
            logger.error(f"Failed to get neighbors for {entity_name}: {e}")
            return {'entity': entity_name, 'neighbors': [], 'error': str(e)}

    async def get_entity_context(
        self,
        entity_name: str,
        include_attributes: bool = True,
        include_relationships: bool = True,
        include_documents: bool = True,
        database: str = None
    ) -> Optional[Dict[str, Any]]:
        """Get full context for an entity including attributes, relationships, and linked documents.

        Args:
            entity_name: Name of the entity
            include_attributes: Include entity attributes
            include_relationships: Include related entities
            include_documents: Include linked document chunks
            database: Database name

        Returns:
            Dict with entity context
        """
        try:
            context = {'entity': entity_name}

            # Get entity
            entities = await self.find_nodes(
                labels=['Entity'],
                properties={'name': entity_name},
                database=database
            )
            if not entities:
                return {'entity': entity_name, 'error': 'Entity not found'}

            entity = entities[0]
            context['properties'] = entity.get('properties', {})
            context['id'] = entity['id']

            # Get attributes
            if include_attributes:
                cypher = """
                    MATCH (e:Entity {name: $name})-[:HAS_ATTRIBUTE]->(a:Attribute)
                    RETURN a
                """
                async with self.session(database) as session:
                    result = await session.run(cypher, name=entity_name)
                    attrs = []
                    async for record in result:
                        attr = record['a']
                        attrs.append({
                            'name': attr.get('name'),
                            'value': attr.get('value'),
                            'type': attr.get('attribute_type')
                        })
                    context['attributes'] = attrs

            # Get relationships
            if include_relationships:
                cypher = """
                    MATCH (e:Entity {name: $name})-[r]-(other:Entity)
                    RETURN type(r) as rel_type, r, other.name as other_name,
                           CASE WHEN startNode(r) = e THEN 'outgoing' ELSE 'incoming' END as direction
                """
                async with self.session(database) as session:
                    result = await session.run(cypher, name=entity_name)
                    rels = []
                    async for record in result:
                        rels.append({
                            'type': record['rel_type'],
                            'other_entity': record['other_name'],
                            'direction': record['direction'],
                            'properties': dict(record['r'])
                        })
                    context['relationships'] = rels

            # Get linked documents
            if include_documents:
                cypher = """
                    MATCH (e:Entity {name: $name})-[:MENTIONED_IN]->(d:DocumentChunk)
                    RETURN d
                    LIMIT 10
                """
                async with self.session(database) as session:
                    result = await session.run(cypher, name=entity_name)
                    docs = []
                    async for record in result:
                        doc = record['d']
                        docs.append({
                            'chunk_id': doc.get('chunk_id'),
                            'text': doc.get('text', '')[:200],  # First 200 chars
                            'source': doc.get('source')
                        })
                    context['documents'] = docs

            return context

        except Exception as e:
            logger.error(f"Failed to get context for {entity_name}: {e}")
            return {'entity': entity_name, 'error': str(e)}


# Example usage
if __name__ == '__main__':
    import asyncio

    async def main():
        # Using environment variables for credentials
        async with AsyncNeo4jClient(host='localhost', port=7687) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Get stats
            stats = await client.get_stats()
            print(f"Stats: {stats}")

            # List vector indexes
            indexes = await client.list_vector_indexes()
            print(f"Vector indexes: {indexes}")

            # Create test node with embedding
            node_id = await client.create_node(
                labels=['TestEntity'],
                properties={
                    'name': 'test_native',
                    'embedding': [0.1] * 1536
                }
            )
            print(f"Created node: {node_id}")

            # Vector search (if index exists)
            if indexes:
                results = await client.vector_search(
                    index_name='entity_embeddings',
                    embedding=[0.1] * 1536,
                    top_k=5
                )
                print(f"Vector search results: {results}")

    asyncio.run(main())
