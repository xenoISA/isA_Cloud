#!/usr/bin/env python3
"""
Async ChromaDB Native Client
Local alternative to AsyncQdrantClient for ICP (Intelligent Personal Context) mode.

This client provides the same interface as AsyncQdrantClient but uses ChromaDB,
making it suitable for local desktop usage without requiring Qdrant server.

ChromaDB is an embedded vector database that stores data locally.
"""

import os
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor

from .async_base_client import AsyncBaseClient

# ChromaDB import with lazy loading
_chromadb = None
_chromadb_settings = None


def _get_chromadb():
    """Lazy load chromadb to avoid import overhead."""
    global _chromadb, _chromadb_settings
    if _chromadb is None:
        import chromadb
        from chromadb.config import Settings
        _chromadb = chromadb
        _chromadb_settings = Settings
    return _chromadb, _chromadb_settings


class AsyncChromaClient(AsyncBaseClient):
    """
    Async ChromaDB client - drop-in replacement for AsyncQdrantClient.

    Provides the same interface as AsyncQdrantClient for local ICP mode.
    All vectors are stored in a local ChromaDB persistent directory.

    Note: ChromaDB doesn't have native async support, so we wrap sync calls
    in a thread pool executor.
    """

    # Class-level configuration
    SERVICE_NAME = "ChromaDB"
    DEFAULT_HOST = "localhost"  # Not used for embedded mode
    DEFAULT_PORT = 0  # Embedded, no port
    ENV_PREFIX = "CHROMA"

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize async ChromaDB client.

        Args:
            persist_directory: Directory for persistent storage
                              (default: ~/.isa_mcp/chroma)
            **kwargs: Base client args (user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        # Determine persistence directory
        if persist_directory:
            self._persist_dir = Path(persist_directory)
        else:
            default_path = os.getenv('CHROMA_PATH', '~/.isa_mcp/chroma')
            self._persist_dir = Path(default_path).expanduser()

        # Ensure directory exists
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = None
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def _connect(self) -> None:
        """Initialize ChromaDB persistent client."""
        chromadb, Settings = _get_chromadb()

        # Create persistent client
        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        self._logger.info(f"Connected to ChromaDB at {self._persist_dir}")

    async def _disconnect(self) -> None:
        """Close ChromaDB client."""
        if self._client:
            # ChromaDB persistent client doesn't need explicit close
            self._client = None

        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

    def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous function in the thread pool."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs)
        )

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Check ChromaDB health."""
        try:
            await self._ensure_connected()

            # Get list of collections as health check
            collections = await self._run_sync(self._client.list_collections)

            return {
                'healthy': True,
                'version': 'chromadb-embedded',
                'collections_count': len(collections),
                'persist_directory': str(self._persist_dir)
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Collection Management
    # ============================================

    async def create_collection(self, collection_name: str, vector_size: int,
                               distance: str = 'Cosine') -> Optional[bool]:
        """
        Create vector collection.

        Args:
            collection_name: Collection name
            vector_size: Vector dimension size (stored as metadata)
            distance: Distance metric (Cosine, Euclid, Dot)

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            # Map distance metrics
            distance_map = {
                'Cosine': 'cosine',
                'cosine': 'cosine',
                'Euclid': 'l2',
                'euclid': 'l2',
                'l2': 'l2',
                'Dot': 'ip',
                'dot': 'ip',
                'ip': 'ip'
            }

            metadata = {
                "hnsw:space": distance_map.get(distance, 'cosine'),
                "vector_size": vector_size
            }

            await self._run_sync(
                self._client.get_or_create_collection,
                name=collection_name,
                metadata=metadata
            )

            return True

        except Exception as e:
            return self.handle_error(e, "create collection")

    async def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            await self._ensure_connected()

            collections = await self._run_sync(self._client.list_collections)
            return [c.name for c in collections]

        except Exception as e:
            self.handle_error(e, "list collections")
            return []

    async def delete_collection(self, collection_name: str) -> Optional[bool]:
        """Delete collection."""
        try:
            await self._ensure_connected()

            await self._run_sync(self._client.delete_collection, collection_name)
            return True

        except Exception as e:
            return self.handle_error(e, "delete collection")

    async def get_collection_info(self, collection_name: str) -> Optional[Dict]:
        """Get collection information."""
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )
            count = await self._run_sync(collection.count)

            return {
                'status': 'ready',
                'points_count': count,
                'segments_count': 1,  # ChromaDB doesn't expose segments
                'metadata': collection.metadata
            }

        except Exception as e:
            return self.handle_error(e, "get collection info")

    # ============================================
    # Point Operations
    # ============================================

    async def upsert_points(self, collection_name: str,
                           points: List[Dict[str, Any]]) -> Optional[str]:
        """
        Insert or update vector points.

        Args:
            collection_name: Collection name
            points: List of point dictionaries with 'id', 'vector', 'payload'

        Returns:
            'success' if successful
        """
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_or_create_collection, collection_name
            )

            # Prepare data for ChromaDB format
            ids = []
            embeddings = []
            metadatas = []

            for p in points:
                # Convert ID to string (ChromaDB requires string IDs)
                point_id = str(p.get('id'))
                ids.append(point_id)
                embeddings.append(p.get('vector', []))

                # Store payload as metadata
                payload = p.get('payload', {})
                # ChromaDB metadata values must be str, int, float, or bool
                metadata = self._flatten_payload(payload)
                metadatas.append(metadata)

            await self._run_sync(
                collection.upsert,
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas
            )

            return 'success'

        except Exception as e:
            return self.handle_error(e, "upsert points")

    async def delete_points(self, collection_name: str,
                           ids: List[Any]) -> Optional[str]:
        """Delete vector points."""
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )

            # Convert IDs to strings
            string_ids = [str(id_) for id_ in ids]

            await self._run_sync(collection.delete, ids=string_ids)

            return 'success'

        except Exception as e:
            return self.handle_error(e, "delete points")

    async def count_points(self, collection_name: str) -> Optional[int]:
        """Count points in collection."""
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )
            count = await self._run_sync(collection.count)

            return count

        except Exception as e:
            return self.handle_error(e, "count points")

    # ============================================
    # Search Operations
    # ============================================

    async def search(self, collection_name: str, vector: List[float],
                    limit: int = 10, score_threshold: Optional[float] = None,
                    with_payload: bool = True,
                    with_vectors: bool = False) -> Optional[List[Dict]]:
        """
        Vector similarity search.

        Args:
            collection_name: Collection name
            vector: Query vector
            limit: Maximum number of results
            score_threshold: Minimum score threshold (converted from distance)
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            List of search results
        """
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )

            include = ["metadatas", "distances"]
            if with_vectors:
                include.append("embeddings")

            results = await self._run_sync(
                collection.query,
                query_embeddings=[vector],
                n_results=limit,
                include=include
            )

            return self._parse_search_results(results, score_threshold, with_payload, with_vectors)

        except Exception as e:
            return self.handle_error(e, "search")

    async def search_with_filter(
        self,
        collection_name: str,
        vector: List[float],
        filter_conditions: Optional[Dict] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        offset: Optional[int] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        params: Optional[Dict] = None
    ) -> Optional[List[Dict]]:
        """
        Vector search with filtering.

        Args:
            collection_name: Collection name
            vector: Query vector
            filter_conditions: Filter with 'must', 'should', 'must_not' keys
            limit: Maximum number of results
            score_threshold: Minimum score threshold
            offset: Pagination offset (limited support in ChromaDB)
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            List of search results
        """
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )

            # Convert filter to ChromaDB where clause
            where_clause = None
            if filter_conditions:
                where_clause = self._build_where_clause(filter_conditions)

            include = ["metadatas", "distances"]
            if with_vectors:
                include.append("embeddings")

            # ChromaDB doesn't support offset directly, so we fetch more and slice
            fetch_limit = limit + (offset or 0)

            results = await self._run_sync(
                collection.query,
                query_embeddings=[vector],
                n_results=fetch_limit,
                where=where_clause,
                include=include
            )

            parsed = self._parse_search_results(results, score_threshold, with_payload, with_vectors)

            # Apply offset manually
            if offset and parsed:
                parsed = parsed[offset:]

            return parsed[:limit] if parsed else []

        except Exception as e:
            return self.handle_error(e, "search with filter")

    async def scroll(
        self,
        collection_name: str,
        filter_conditions: Optional[Dict] = None,
        limit: int = 100,
        offset_id: Optional[Any] = None,
        with_payload: bool = True,
        with_vectors: bool = False
    ) -> Optional[Dict]:
        """
        Scroll through all points in collection.

        Returns:
            Dictionary with 'points' and 'next_offset' keys
        """
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )

            # Build where clause
            where_clause = None
            if filter_conditions:
                where_clause = self._build_where_clause(filter_conditions)

            include = ["metadatas"]
            if with_vectors:
                include.append("embeddings")

            # Get all matching points
            results = await self._run_sync(
                collection.get,
                where=where_clause,
                limit=limit,
                offset=int(offset_id) if offset_id else 0,
                include=include
            )

            points = []
            ids = results.get('ids', [])
            metadatas = results.get('metadatas', [])
            embeddings = results.get('embeddings', []) if with_vectors else []

            for i, id_ in enumerate(ids):
                point_data = {
                    'id': id_,
                    'payload': self._unflatten_payload(metadatas[i]) if with_payload and i < len(metadatas) else None,
                    'vector': embeddings[i] if with_vectors and i < len(embeddings) else None
                }
                points.append(point_data)

            # Calculate next offset
            next_offset = None
            if len(points) == limit:
                next_offset = (int(offset_id) if offset_id else 0) + limit

            return {'points': points, 'next_offset': next_offset}

        except Exception as e:
            return self.handle_error(e, "scroll")

    # ============================================
    # Payload Operations
    # ============================================

    async def update_payload(self, collection_name: str, ids: List[Any],
                            payload: Dict[str, Any]) -> Optional[str]:
        """Update payload for specific points."""
        try:
            await self._ensure_connected()

            collection = await self._run_sync(
                self._client.get_collection, collection_name
            )

            # Convert IDs to strings
            string_ids = [str(id_) for id_ in ids]

            # Flatten payload
            metadata = self._flatten_payload(payload)

            await self._run_sync(
                collection.update,
                ids=string_ids,
                metadatas=[metadata] * len(string_ids)
            )

            return 'success'

        except Exception as e:
            return self.handle_error(e, "update payload")

    # ============================================
    # Index Management (ChromaDB handles automatically)
    # ============================================

    async def create_field_index(self, collection_name: str, field_name: str,
                                field_type: str = 'keyword') -> Optional[str]:
        """Create index on payload field (no-op for ChromaDB)."""
        # ChromaDB creates indexes automatically
        return 'success'

    async def delete_field_index(self, collection_name: str,
                                field_name: str) -> Optional[str]:
        """Delete payload field index (no-op for ChromaDB)."""
        # ChromaDB manages indexes automatically
        return 'success'

    # ============================================
    # Concurrent Operations
    # ============================================

    async def search_many_concurrent(
        self,
        collection_name: str,
        vectors: List[List[float]],
        limit: int = 10,
        with_payload: bool = True
    ) -> List[Optional[List[Dict]]]:
        """Execute multiple searches."""
        tasks = [
            self.search(collection_name, v, limit=limit, with_payload=with_payload)
            for v in vectors
        ]
        return await asyncio.gather(*tasks)

    async def upsert_points_concurrent(
        self,
        collection_name: str,
        point_batches: List[List[Dict]]
    ) -> List[Optional[str]]:
        """Upsert multiple batches of points."""
        tasks = [
            self.upsert_points(collection_name, batch)
            for batch in point_batches
        ]
        return await asyncio.gather(*tasks)

    # ============================================
    # Helper Methods
    # ============================================

    def _flatten_payload(self, payload: Dict) -> Dict:
        """Flatten nested payload for ChromaDB metadata storage."""
        flat = {}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)):
                flat[key] = value
            elif isinstance(value, list):
                # Store lists as JSON strings
                import json
                flat[key] = json.dumps(value)
            elif isinstance(value, dict):
                # Store dicts as JSON strings
                import json
                flat[key] = json.dumps(value)
            elif value is None:
                flat[key] = ""
            else:
                flat[key] = str(value)
        return flat

    def _unflatten_payload(self, metadata: Dict) -> Dict:
        """Unflatten metadata back to nested payload."""
        import json
        result = {}
        for key, value in metadata.items():
            if isinstance(value, str):
                # Try to parse as JSON
                try:
                    if value.startswith('{') or value.startswith('['):
                        result[key] = json.loads(value)
                    else:
                        result[key] = value
                except (json.JSONDecodeError, ValueError):
                    result[key] = value
            else:
                result[key] = value
        return result

    def _build_where_clause(self, filter_conditions: Dict) -> Optional[Dict]:
        """Build ChromaDB where clause from Qdrant-style filter."""
        clauses = []

        if 'must' in filter_conditions:
            for cond in filter_conditions['must']:
                clause = self._build_single_condition(cond)
                if clause:
                    clauses.append(clause)

        if not clauses:
            return None

        if len(clauses) == 1:
            return clauses[0]

        return {"$and": clauses}

    def _build_single_condition(self, condition: Dict) -> Optional[Dict]:
        """Build single where condition."""
        field = condition.get('field')

        if 'match' in condition:
            match_val = condition['match']
            if 'keyword' in match_val:
                return {field: {"$eq": match_val['keyword']}}
            elif 'integer' in match_val:
                return {field: {"$eq": match_val['integer']}}
            elif 'boolean' in match_val:
                return {field: {"$eq": match_val['boolean']}}
            elif 'value' in match_val:
                return {field: {"$eq": match_val['value']}}

        elif 'range' in condition:
            range_val = condition['range']
            range_clause = {}
            if 'gt' in range_val:
                range_clause["$gt"] = range_val['gt']
            if 'gte' in range_val:
                range_clause["$gte"] = range_val['gte']
            if 'lt' in range_val:
                range_clause["$lt"] = range_val['lt']
            if 'lte' in range_val:
                range_clause["$lte"] = range_val['lte']
            return {field: range_clause} if range_clause else None

        return None

    def _parse_search_results(self, results: Dict, score_threshold: Optional[float],
                             with_payload: bool, with_vectors: bool) -> List[Dict]:
        """Parse ChromaDB query results to Qdrant-compatible format."""
        parsed = []

        ids = results.get('ids', [[]])[0]
        distances = results.get('distances', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        embeddings = results.get('embeddings', [[]])[0] if with_vectors else []

        for i, id_ in enumerate(ids):
            # Convert distance to score (ChromaDB returns distance, not similarity)
            distance = distances[i] if i < len(distances) else 0
            # For cosine distance, score = 1 - distance
            score = 1.0 - distance

            # Apply threshold
            if score_threshold and score < score_threshold:
                continue

            result = {
                'id': id_,
                'score': score,
                'payload': self._unflatten_payload(metadatas[i]) if with_payload and i < len(metadatas) else None,
                'vector': embeddings[i] if with_vectors and i < len(embeddings) else None
            }
            parsed.append(result)

        return parsed


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncChromaClient(
            persist_directory='/tmp/isa_chroma_test',
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Create collection
            await client.create_collection('test_collection', vector_size=128)

            # List collections
            collections = await client.list_collections()
            print(f"Collections: {collections}")

            # Upsert points
            points = [
                {'id': 1, 'vector': [0.1] * 128, 'payload': {'name': 'test1', 'type': 'tool'}},
                {'id': 2, 'vector': [0.2] * 128, 'payload': {'name': 'test2', 'type': 'tool'}},
                {'id': 3, 'vector': [0.15] * 128, 'payload': {'name': 'test3', 'type': 'prompt'}},
            ]
            await client.upsert_points('test_collection', points)

            # Count
            count = await client.count_points('test_collection')
            print(f"Points count: {count}")

            # Search
            results = await client.search('test_collection', [0.1] * 128, limit=5)
            print(f"Search results: {results}")

            # Search with filter
            results = await client.search_with_filter(
                'test_collection',
                [0.1] * 128,
                filter_conditions={'must': [{'field': 'type', 'match': {'keyword': 'tool'}}]},
                limit=5
            )
            print(f"Filtered search results: {results}")

            # Scroll
            scroll_result = await client.scroll('test_collection', limit=2)
            print(f"Scroll result: {scroll_result}")

            # Cleanup
            await client.delete_collection('test_collection')

    asyncio.run(main())
