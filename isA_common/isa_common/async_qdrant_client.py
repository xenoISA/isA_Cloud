#!/usr/bin/env python3
"""
Async Qdrant Native Client
High-performance async Qdrant vector database client using qdrant-client.

This client connects directly to Qdrant using the official qdrant-client library,
providing full support for all Qdrant operations including:
- Collection management
- Point CRUD operations
- Vector similarity search
- Payload filtering
- Recommendation search
"""

import os
import asyncio
from typing import List, Dict, Optional, Any, Union

from qdrant_client import AsyncQdrantClient as QdrantAsyncClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PointIdsList,
    Filter, FieldCondition, MatchValue, Range,
    CollectionInfo, ScoredPoint, Record,
    PayloadSchemaType, TextIndexParams, TokenizerType,
    GeoBoundingBox, GeoPoint, GeoRadius,
    RecommendQuery, RecommendInput
)

from .async_base_client import AsyncBaseClient


class AsyncQdrantClient(AsyncBaseClient):
    """
    Async Qdrant client using native qdrant-client driver.

    Provides direct connection to Qdrant with full feature support including
    collection management, vector search, and recommendation.
    """

    # Class-level configuration
    SERVICE_NAME = "Qdrant"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 6333
    ENV_PREFIX = "QDRANT"
    # No TENANT_SEPARATOR - Qdrant uses payload filtering for multi-tenancy

    def __init__(
        self,
        api_key: Optional[str] = None,
        https: bool = False,
        **kwargs
    ):
        """
        Initialize async Qdrant client with native driver.

        Args:
            api_key: Qdrant API key (default: from QDRANT_API_KEY env)
            https: Use HTTPS connection (default: False)
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._api_key = api_key or os.getenv('QDRANT_API_KEY')
        self._https = https

        self._client: Optional[QdrantAsyncClient] = None

    async def _connect(self) -> None:
        """Establish Qdrant connection."""
        url = f"{'https' if self._https else 'http'}://{self._host}:{self._port}"
        self._client = QdrantAsyncClient(
            url=url,
            api_key=self._api_key,
            timeout=60
        )
        self._logger.info(f"Connected to Qdrant at {self._host}:{self._port}")

    async def _disconnect(self) -> None:
        """Close Qdrant connection."""
        if self._client:
            await self._client.close()
            self._client = None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()

            # Check if Qdrant is reachable by getting collections
            collections = await self._client.get_collections()

            return {
                'healthy': True,
                'version': 'native-client'
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
            vector_size: Vector dimension size
            distance: Distance metric (Cosine, Euclid, Dot, Manhattan)

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            distance_map = {
                'Cosine': Distance.COSINE,
                'Euclid': Distance.EUCLID,
                'Dot': Distance.DOT,
                'Manhattan': Distance.MANHATTAN
            }

            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_map.get(distance, Distance.COSINE)
                )
            )

            return True

        except Exception as e:
            return self.handle_error(e, "create collection")

    async def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            await self._ensure_connected()
            result = await self._client.get_collections()
            return [c.name for c in result.collections]

        except Exception as e:
            self.handle_error(e, "list collections")
            return []

    async def delete_collection(self, collection_name: str) -> Optional[bool]:
        """Delete collection."""
        try:
            await self._ensure_connected()
            await self._client.delete_collection(collection_name)
            return True

        except Exception as e:
            return self.handle_error(e, "delete collection")

    async def get_collection_info(self, collection_name: str) -> Optional[Dict]:
        """Get collection information."""
        try:
            await self._ensure_connected()
            info = await self._client.get_collection(collection_name)

            return {
                'status': str(info.status),
                'points_count': info.points_count,
                'segments_count': info.segments_count
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
            Operation ID if successful
        """
        try:
            await self._ensure_connected()

            point_structs = []
            for p in points:
                point_structs.append(PointStruct(
                    id=p.get('id'),
                    vector=p.get('vector', []),
                    payload=p.get('payload', {})
                ))

            result = await self._client.upsert(
                collection_name=collection_name,
                points=point_structs,
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "upsert points")

    async def delete_points(self, collection_name: str,
                           ids: List[Any]) -> Optional[str]:
        """Delete vector points."""
        try:
            await self._ensure_connected()

            result = await self._client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=ids),
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "delete points")

    async def count_points(self, collection_name: str) -> Optional[int]:
        """Count points in collection."""
        try:
            await self._ensure_connected()
            result = await self._client.count(
                collection_name=collection_name,
                exact=True
            )
            return result.count

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
            score_threshold: Minimum score threshold
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            List of search results
        """
        try:
            await self._ensure_connected()

            # New qdrant-client API uses query_points instead of search
            response = await self._client.query_points(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            return self._parse_query_response(response, with_payload, with_vectors)

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
        Vector search with advanced filtering.

        Args:
            collection_name: Collection name
            vector: Query vector
            filter_conditions: Filter with 'must', 'should', 'must_not' keys
            limit: Maximum number of results
            score_threshold: Minimum score threshold
            offset: Pagination offset
            with_payload: Include payload in results
            with_vectors: Include vectors in results
            params: Search parameters

        Returns:
            List of search results
        """
        try:
            await self._ensure_connected()

            qdrant_filter = None
            if filter_conditions:
                qdrant_filter = self._build_filter(filter_conditions)

            # New qdrant-client API uses query_points instead of search
            response = await self._client.query_points(
                collection_name=collection_name,
                query=vector,
                query_filter=qdrant_filter,
                limit=limit,
                score_threshold=score_threshold,
                offset=offset or 0,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            return self._parse_query_response(response, with_payload, with_vectors)

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

            qdrant_filter = None
            if filter_conditions:
                qdrant_filter = self._build_filter(filter_conditions)

            records, next_offset = await self._client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                limit=limit,
                offset=offset_id,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            points = []
            for record in records:
                point_data = {
                    'id': record.id,
                    'payload': record.payload if with_payload else None,
                    'vector': record.vector if with_vectors else None
                }
                points.append(point_data)

            return {'points': points, 'next_offset': next_offset}

        except Exception as e:
            return self.handle_error(e, "scroll")

    async def recommend(
        self,
        collection_name: str,
        positive: List[Any],
        negative: Optional[List[Any]] = None,
        filter_conditions: Optional[Dict] = None,
        limit: int = 10,
        with_payload: bool = True,
        with_vectors: bool = False
    ) -> Optional[List[Dict]]:
        """
        Recommendation search based on positive/negative examples.

        Args:
            collection_name: Collection name
            positive: List of positive example IDs
            negative: List of negative example IDs
            filter_conditions: Optional filter conditions
            limit: Maximum number of results
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            List of recommended results
        """
        try:
            await self._ensure_connected()

            qdrant_filter = None
            if filter_conditions:
                qdrant_filter = self._build_filter(filter_conditions)

            # New qdrant-client API uses query_points with RecommendQuery
            recommend_query = RecommendQuery(
                recommend=RecommendInput(
                    positive=positive,
                    negative=negative or []
                )
            )

            response = await self._client.query_points(
                collection_name=collection_name,
                query=recommend_query,
                query_filter=qdrant_filter,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            return self._parse_query_response(response, with_payload, with_vectors)

        except Exception as e:
            return self.handle_error(e, "recommend")

    # ============================================
    # Payload Operations
    # ============================================

    async def update_payload(self, collection_name: str, ids: List[Any],
                            payload: Dict[str, Any]) -> Optional[str]:
        """Update payload for specific points."""
        try:
            await self._ensure_connected()

            result = await self._client.set_payload(
                collection_name=collection_name,
                payload=payload,
                points=ids,
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "update payload")

    async def delete_payload_fields(self, collection_name: str, ids: List[Any],
                                   keys: List[str]) -> Optional[str]:
        """Delete specific payload fields."""
        try:
            await self._ensure_connected()

            result = await self._client.delete_payload(
                collection_name=collection_name,
                keys=keys,
                points=ids,
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "delete payload fields")

    async def clear_payload(self, collection_name: str,
                           ids: List[Any]) -> Optional[str]:
        """Clear all payload data from points."""
        try:
            await self._ensure_connected()

            result = await self._client.clear_payload(
                collection_name=collection_name,
                points_selector=PointIdsList(points=ids),
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "clear payload")

    # ============================================
    # Index Management
    # ============================================

    async def create_field_index(self, collection_name: str, field_name: str,
                                field_type: str = 'keyword') -> Optional[str]:
        """Create index on payload field."""
        try:
            await self._ensure_connected()

            # Map field type to PayloadSchemaType
            type_map = {
                'keyword': PayloadSchemaType.KEYWORD,
                'integer': PayloadSchemaType.INTEGER,
                'float': PayloadSchemaType.FLOAT,
                'geo': PayloadSchemaType.GEO,
                'text': PayloadSchemaType.TEXT,
            }

            schema_type = type_map.get(field_type.lower(), PayloadSchemaType.KEYWORD)

            result = await self._client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type,
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "create field index")

    async def delete_field_index(self, collection_name: str,
                                field_name: str) -> Optional[str]:
        """Delete payload field index."""
        try:
            await self._ensure_connected()

            result = await self._client.delete_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                wait=True
            )

            return str(result.operation_id) if hasattr(result, 'operation_id') else 'success'

        except Exception as e:
            return self.handle_error(e, "delete field index")

    # ============================================
    # Snapshot Operations
    # ============================================

    async def create_snapshot(self, collection_name: str) -> Optional[str]:
        """Create collection snapshot."""
        try:
            await self._ensure_connected()

            result = await self._client.create_snapshot(collection_name)

            return result.name if hasattr(result, 'name') else 'success'

        except Exception as e:
            return self.handle_error(e, "create snapshot")

    async def list_snapshots(self, collection_name: str) -> Optional[List[Dict]]:
        """List all snapshots for collection."""
        try:
            await self._ensure_connected()

            snapshots = await self._client.list_snapshots(collection_name)

            result = []
            for snap in snapshots:
                result.append({
                    'name': snap.name,
                    'created_at': snap.creation_time,
                    'size_bytes': snap.size
                })
            return result

        except Exception as e:
            return self.handle_error(e, "list snapshots")

    async def delete_snapshot(self, collection_name: str,
                             snapshot_name: str) -> Optional[bool]:
        """Delete snapshot."""
        try:
            await self._ensure_connected()

            await self._client.delete_snapshot(
                collection_name=collection_name,
                snapshot_name=snapshot_name
            )
            return True

        except Exception as e:
            return self.handle_error(e, "delete snapshot")

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
        """Execute multiple searches concurrently."""
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
        """Upsert multiple batches of points concurrently."""
        tasks = [
            self.upsert_points(collection_name, batch)
            for batch in point_batches
        ]
        return await asyncio.gather(*tasks)

    # ============================================
    # Helper Methods
    # ============================================

    def _build_filter(self, filter_conditions: Dict) -> Filter:
        """Build Qdrant Filter from dictionary."""
        must = []
        should = []
        must_not = []

        if 'must' in filter_conditions:
            for cond in filter_conditions['must']:
                must.append(self._build_filter_condition(cond))

        if 'should' in filter_conditions:
            for cond in filter_conditions['should']:
                should.append(self._build_filter_condition(cond))

        if 'must_not' in filter_conditions:
            for cond in filter_conditions['must_not']:
                must_not.append(self._build_filter_condition(cond))

        return Filter(
            must=must if must else None,
            should=should if should else None,
            must_not=must_not if must_not else None
        )

    def _build_filter_condition(self, condition: Dict) -> FieldCondition:
        """Build FieldCondition from dictionary."""
        field = condition['field']

        if 'match' in condition:
            match_val = condition['match']
            if 'keyword' in match_val:
                return FieldCondition(key=field, match=MatchValue(value=match_val['keyword']))
            elif 'integer' in match_val:
                return FieldCondition(key=field, match=MatchValue(value=match_val['integer']))
            elif 'boolean' in match_val:
                return FieldCondition(key=field, match=MatchValue(value=match_val['boolean']))

        elif 'range' in condition:
            range_val = condition['range']
            return FieldCondition(
                key=field,
                range=Range(
                    gt=range_val.get('gt'),
                    gte=range_val.get('gte'),
                    lt=range_val.get('lt'),
                    lte=range_val.get('lte')
                )
            )

        elif 'geo_bounding_box' in condition:
            geo_box = condition['geo_bounding_box']
            return FieldCondition(
                key=field,
                geo_bounding_box=GeoBoundingBox(
                    top_left=GeoPoint(**geo_box['top_left']),
                    bottom_right=GeoPoint(**geo_box['bottom_right'])
                )
            )

        elif 'geo_radius' in condition:
            geo_rad = condition['geo_radius']
            return FieldCondition(
                key=field,
                geo_radius=GeoRadius(
                    center=GeoPoint(**geo_rad['center']),
                    radius=geo_rad['radius_meters']
                )
            )

        # Default to match any value
        return FieldCondition(key=field, match=MatchValue(value=True))

    def _parse_query_response(self, response, with_payload: bool, with_vectors: bool) -> List[Dict]:
        """Parse query response to dictionary (new qdrant-client API)."""
        results = []
        for point in response.points:
            result = {
                'score': point.score if hasattr(point, 'score') else None,
                'id': point.id,
                'payload': point.payload if with_payload and hasattr(point, 'payload') else None,
                'vector': point.vector if with_vectors and hasattr(point, 'vector') else None
            }
            results.append(result)
        return results

    def _parse_scored_points(self, scored_points: List[ScoredPoint],
                            with_payload: bool, with_vectors: bool) -> List[Dict]:
        """Parse scored points to dictionary."""
        results = []
        for sp in scored_points:
            result = {
                'score': sp.score,
                'id': sp.id,
                'payload': sp.payload if with_payload else None,
                'vector': sp.vector if with_vectors else None
            }
            results.append(result)
        return results


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncQdrantClient(
            host='localhost',
            port=6333,
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # List collections
            collections = await client.list_collections()
            print(f"Collections: {collections}")

            # Create collection
            await client.create_collection('test_collection', vector_size=128)

            # Upsert points
            points = [
                {'id': 1, 'vector': [0.1] * 128, 'payload': {'name': 'test1'}},
                {'id': 2, 'vector': [0.2] * 128, 'payload': {'name': 'test2'}},
            ]
            await client.upsert_points('test_collection', points)

            # Search
            results = await client.search('test_collection', [0.1] * 128, limit=5)
            print(f"Search results: {results}")

            # Cleanup
            await client.delete_collection('test_collection')

    asyncio.run(main())
