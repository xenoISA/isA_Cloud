#!/usr/bin/env python3
"""
Async Qdrant gRPC Client
High-performance async Qdrant vector database client using grpc.aio

Performance Benefits:
- True async I/O for vector similarity searches
- Concurrent embedding operations
- Non-blocking batch upserts
- High-throughput AI/ML workloads
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from google.protobuf.struct_pb2 import Struct
from google.protobuf.json_format import MessageToDict
from .async_base_client import AsyncBaseGRPCClient
from .proto import qdrant_service_pb2, qdrant_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)


class AsyncQdrantClient(AsyncBaseGRPCClient):
    """Async Qdrant gRPC client for high-performance vector search."""

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
        Initialize async Qdrant client.

        Args:
            host: Service address (optional)
            port: Service port (optional)
            user_id: User ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery
            service_name_override: Override service name for Consul lookup
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
        """Create Qdrant service stub."""
        return qdrant_service_pb2_grpc.QdrantServiceStub(self.channel)

    def service_name(self) -> str:
        return "Qdrant"

    def default_port(self) -> int:
        return 50062

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.QdrantHealthCheckRequest()
            response = await self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'version': response.version
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
                'Cosine': qdrant_service_pb2.DISTANCE_COSINE,
                'Euclid': qdrant_service_pb2.DISTANCE_EUCLID,
                'Dot': qdrant_service_pb2.DISTANCE_DOT,
                'Manhattan': qdrant_service_pb2.DISTANCE_MANHATTAN
            }

            vector_params = qdrant_service_pb2.VectorParams(
                size=vector_size,
                distance=distance_map.get(distance, qdrant_service_pb2.DISTANCE_COSINE)
            )

            request = qdrant_service_pb2.CreateCollectionRequest(
                collection_name=collection_name
            )
            request.vector_params.CopyFrom(vector_params)

            response = await self.stub.CreateCollection(request)

            if response.metadata.success:
                return True
            return None

        except Exception as e:
            return self.handle_error(e, "create collection")

    async def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.ListCollectionsRequest()
            response = await self.stub.ListCollections(request)

            if response.metadata.success:
                return [c.name for c in response.collections]
            return []

        except Exception as e:
            self.handle_error(e, "list collections")
            return []

    async def delete_collection(self, collection_name: str) -> Optional[bool]:
        """Delete collection."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.DeleteCollectionRequest(
                collection_name=collection_name
            )

            response = await self.stub.DeleteCollection(request)

            if response.metadata.success:
                return True
            return None

        except Exception as e:
            return self.handle_error(e, "delete collection")

    async def get_collection_info(self, collection_name: str) -> Optional[Dict]:
        """Get collection information."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.GetCollectionInfoRequest(
                collection_name=collection_name
            )

            response = await self.stub.GetCollectionInfo(request)

            if response.metadata.success:
                return {
                    'status': response.info.status,
                    'points_count': response.info.points_count,
                    'segments_count': response.info.segments_count
                }
            return None

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

            proto_points = []
            for p in points:
                point_id = p.get('id')
                if isinstance(point_id, int):
                    point = qdrant_service_pb2.Point(num_id=point_id)
                else:
                    point = qdrant_service_pb2.Point(str_id=str(point_id))

                vector = qdrant_service_pb2.Vector(data=p.get('vector', []))
                point.vector.CopyFrom(vector)

                if 'payload' in p and p['payload']:
                    payload_struct = Struct()
                    payload_struct.update(p['payload'])
                    point.payload.CopyFrom(payload_struct)

                proto_points.append(point)

            request = qdrant_service_pb2.UpsertPointsRequest(
                collection_name=collection_name,
                points=proto_points,
                wait=True
            )

            response = await self.stub.UpsertPoints(request)

            if response.metadata.success:
                return response.operation_id
            return None

        except Exception as e:
            return self.handle_error(e, "upsert points")

    async def delete_points(self, collection_name: str,
                           ids: List[Any]) -> Optional[str]:
        """Delete vector points."""
        try:
            await self._ensure_connected()

            proto_ids = []
            for point_id in ids:
                if isinstance(point_id, int):
                    proto_ids.append(qdrant_service_pb2.PointId(num=point_id))
                else:
                    proto_ids.append(qdrant_service_pb2.PointId(str=str(point_id)))

            point_id_list = qdrant_service_pb2.PointIdList(ids=proto_ids)

            request = qdrant_service_pb2.DeletePointsRequest(
                collection_name=collection_name,
                ids=point_id_list,
                wait=True
            )

            response = await self.stub.DeletePoints(request)

            if response.metadata.success:
                return response.operation_id
            return None

        except Exception as e:
            return self.handle_error(e, "delete points")

    async def count_points(self, collection_name: str) -> Optional[int]:
        """Count points in collection."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.CountRequest(
                collection_name=collection_name,
                exact=True
            )

            response = await self.stub.Count(request)

            if response.metadata.success:
                return response.count
            return None

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

            proto_vector = qdrant_service_pb2.Vector(data=vector)

            request = qdrant_service_pb2.SearchRequest(
                collection_name=collection_name,
                vector=proto_vector,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            if score_threshold is not None:
                request.score_threshold = score_threshold

            response = await self.stub.Search(request)

            if response.metadata.success:
                return self._parse_scored_points(response.result, with_payload, with_vectors)
            return None

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

            proto_vector = qdrant_service_pb2.Vector(data=vector)

            request = qdrant_service_pb2.SearchRequest(
                collection_name=collection_name,
                vector=proto_vector,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            if filter_conditions:
                proto_filter = self._build_filter(filter_conditions)
                request.filter.CopyFrom(proto_filter)

            if score_threshold is not None:
                request.score_threshold = score_threshold

            if offset is not None:
                request.offset = offset

            if params:
                params_struct = Struct()
                params_struct.update(params)
                request.params.CopyFrom(params_struct)

            response = await self.stub.Search(request)

            if response.metadata.success:
                return self._parse_scored_points(response.result, with_payload, with_vectors)
            return None

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

            request = qdrant_service_pb2.ScrollRequest(
                collection_name=collection_name,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            if filter_conditions:
                proto_filter = self._build_filter(filter_conditions)
                request.filter.CopyFrom(proto_filter)

            if offset_id is not None:
                if isinstance(offset_id, int):
                    request.offset.num = offset_id
                else:
                    request.offset.str = str(offset_id)

            response = await self.stub.Scroll(request)

            if response.metadata.success:
                points = []
                for point in response.points:
                    point_data = {'id': None, 'payload': None, 'vector': None}

                    if point.HasField('num_id'):
                        point_data['id'] = point.num_id
                    elif point.HasField('str_id'):
                        point_data['id'] = point.str_id

                    if with_payload and point.payload:
                        point_data['payload'] = MessageToDict(point.payload)

                    if with_vectors and point.HasField('vector'):
                        point_data['vector'] = list(point.vector.data)

                    points.append(point_data)

                next_offset = None
                if response.HasField('next_page_offset'):
                    if response.next_page_offset.HasField('num'):
                        next_offset = response.next_page_offset.num
                    elif response.next_page_offset.HasField('str'):
                        next_offset = response.next_page_offset.str

                return {'points': points, 'next_offset': next_offset}
            return None

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

            positive_ids = []
            for pid in positive:
                if isinstance(pid, int):
                    positive_ids.append(qdrant_service_pb2.PointId(num=pid))
                else:
                    positive_ids.append(qdrant_service_pb2.PointId(str=str(pid)))

            negative_ids = []
            if negative:
                for nid in negative:
                    if isinstance(nid, int):
                        negative_ids.append(qdrant_service_pb2.PointId(num=nid))
                    else:
                        negative_ids.append(qdrant_service_pb2.PointId(str=str(nid)))

            request = qdrant_service_pb2.RecommendRequest(
                collection_name=collection_name,
                positive=positive_ids,
                negative=negative_ids,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            if filter_conditions:
                proto_filter = self._build_filter(filter_conditions)
                request.filter.CopyFrom(proto_filter)

            response = await self.stub.Recommend(request)

            if response.metadata.success:
                return self._parse_scored_points(response.result, with_payload, with_vectors)
            return None

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

            proto_ids = []
            for point_id in ids:
                if isinstance(point_id, int):
                    proto_ids.append(qdrant_service_pb2.PointId(num=point_id))
                else:
                    proto_ids.append(qdrant_service_pb2.PointId(str=str(point_id)))

            point_id_list = qdrant_service_pb2.PointIdList(ids=proto_ids)

            payload_struct = Struct()
            payload_struct.update(payload)

            request = qdrant_service_pb2.UpdatePayloadRequest(
                collection_name=collection_name,
                ids=point_id_list,
                payload=payload_struct,
                wait=True
            )

            response = await self.stub.UpdatePayload(request)

            if response.metadata.success:
                return response.operation_id
            return None

        except Exception as e:
            return self.handle_error(e, "update payload")

    async def delete_payload_fields(self, collection_name: str, ids: List[Any],
                                   keys: List[str]) -> Optional[str]:
        """Delete specific payload fields."""
        try:
            await self._ensure_connected()

            proto_ids = []
            for point_id in ids:
                if isinstance(point_id, int):
                    proto_ids.append(qdrant_service_pb2.PointId(num=point_id))
                else:
                    proto_ids.append(qdrant_service_pb2.PointId(str=str(point_id)))

            point_id_list = qdrant_service_pb2.PointIdList(ids=proto_ids)

            request = qdrant_service_pb2.DeletePayloadRequest(
                collection_name=collection_name,
                ids=point_id_list,
                keys=keys,
                wait=True
            )

            response = await self.stub.DeletePayload(request)

            if response.metadata.success:
                return response.operation_id
            return None

        except Exception as e:
            return self.handle_error(e, "delete payload fields")

    async def clear_payload(self, collection_name: str,
                           ids: List[Any]) -> Optional[str]:
        """Clear all payload data from points."""
        try:
            await self._ensure_connected()

            proto_ids = []
            for point_id in ids:
                if isinstance(point_id, int):
                    proto_ids.append(qdrant_service_pb2.PointId(num=point_id))
                else:
                    proto_ids.append(qdrant_service_pb2.PointId(str=str(point_id)))

            point_id_list = qdrant_service_pb2.PointIdList(ids=proto_ids)

            request = qdrant_service_pb2.ClearPayloadRequest(
                collection_name=collection_name,
                ids=point_id_list,
                wait=True
            )

            response = await self.stub.ClearPayload(request)

            if response.metadata.success:
                return response.operation_id
            return None

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
            request = qdrant_service_pb2.CreateFieldIndexRequest(
                collection_name=collection_name,
                field_name=field_name,
                field_type=field_type,
                wait=True
            )

            response = await self.stub.CreateFieldIndex(request)

            if response.metadata.success:
                return response.operation_id
            return None

        except Exception as e:
            return self.handle_error(e, "create field index")

    async def delete_field_index(self, collection_name: str,
                                field_name: str) -> Optional[str]:
        """Delete payload field index."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.DeleteFieldIndexRequest(
                collection_name=collection_name,
                field_name=field_name,
                wait=True
            )

            response = await self.stub.DeleteFieldIndex(request)

            if response.metadata.success:
                return response.operation_id
            return None

        except Exception as e:
            return self.handle_error(e, "delete field index")

    # ============================================
    # Snapshot Operations
    # ============================================

    async def create_snapshot(self, collection_name: str) -> Optional[str]:
        """Create collection snapshot."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.CreateSnapshotRequest(
                collection_name=collection_name
            )

            response = await self.stub.CreateSnapshot(request)

            if response.metadata.success:
                return response.snapshot_name
            return None

        except Exception as e:
            return self.handle_error(e, "create snapshot")

    async def list_snapshots(self, collection_name: str) -> Optional[List[Dict]]:
        """List all snapshots for collection."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.ListSnapshotsRequest(
                collection_name=collection_name
            )

            response = await self.stub.ListSnapshots(request)

            if response.metadata.success:
                snapshots = []
                for snap in response.snapshots:
                    snapshots.append({
                        'name': snap.name,
                        'created_at': snap.created_at.ToDatetime(),
                        'size_bytes': snap.size_bytes
                    })
                return snapshots
            return None

        except Exception as e:
            return self.handle_error(e, "list snapshots")

    async def delete_snapshot(self, collection_name: str,
                             snapshot_name: str) -> Optional[bool]:
        """Delete snapshot."""
        try:
            await self._ensure_connected()
            request = qdrant_service_pb2.DeleteSnapshotRequest(
                collection_name=collection_name,
                snapshot_name=snapshot_name
            )

            response = await self.stub.DeleteSnapshot(request)

            if response.metadata.success:
                return True
            return None

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

    def _build_filter(self, filter_conditions: Dict) -> "qdrant_service_pb2.Filter":
        """Build protobuf Filter from dictionary."""
        proto_filter = qdrant_service_pb2.Filter()

        if 'must' in filter_conditions:
            for cond in filter_conditions['must']:
                proto_filter.must.append(self._build_filter_condition(cond))

        if 'should' in filter_conditions:
            for cond in filter_conditions['should']:
                proto_filter.should.append(self._build_filter_condition(cond))

        if 'must_not' in filter_conditions:
            for cond in filter_conditions['must_not']:
                proto_filter.must_not.append(self._build_filter_condition(cond))

        return proto_filter

    def _build_filter_condition(self, condition: Dict) -> "qdrant_service_pb2.FilterCondition":
        """Build protobuf FilterCondition from dictionary."""
        filter_cond = qdrant_service_pb2.FilterCondition(field=condition['field'])

        if 'match' in condition:
            match_cond = qdrant_service_pb2.MatchCondition()
            match_val = condition['match']
            if 'keyword' in match_val:
                match_cond.keyword = match_val['keyword']
            elif 'integer' in match_val:
                match_cond.integer = match_val['integer']
            elif 'boolean' in match_val:
                match_cond.boolean = match_val['boolean']
            filter_cond.match.CopyFrom(match_cond)

        elif 'range' in condition:
            range_cond = qdrant_service_pb2.RangeCondition()
            range_val = condition['range']
            if 'gt' in range_val:
                range_cond.gt = range_val['gt']
            if 'gte' in range_val:
                range_cond.gte = range_val['gte']
            if 'lt' in range_val:
                range_cond.lt = range_val['lt']
            if 'lte' in range_val:
                range_cond.lte = range_val['lte']
            filter_cond.range.CopyFrom(range_cond)

        elif 'geo_bounding_box' in condition:
            geo_box = qdrant_service_pb2.GeoBoundingBoxCondition(
                top_left=qdrant_service_pb2.GeoPoint(**condition['geo_bounding_box']['top_left']),
                bottom_right=qdrant_service_pb2.GeoPoint(**condition['geo_bounding_box']['bottom_right'])
            )
            filter_cond.geo_bounding_box.CopyFrom(geo_box)

        elif 'geo_radius' in condition:
            geo_rad = qdrant_service_pb2.GeoRadiusCondition(
                center=qdrant_service_pb2.GeoPoint(**condition['geo_radius']['center']),
                radius_meters=condition['geo_radius']['radius_meters']
            )
            filter_cond.geo_radius.CopyFrom(geo_rad)

        return filter_cond

    def _parse_scored_points(self, scored_points, with_payload: bool,
                            with_vectors: bool) -> List[Dict]:
        """Parse scored points from protobuf to dictionary."""
        results = []
        for scored_point in scored_points:
            result = {
                'score': scored_point.score,
                'id': None,
                'payload': None,
                'vector': None
            }

            if scored_point.point.HasField('num_id'):
                result['id'] = scored_point.point.num_id
            elif scored_point.point.HasField('str_id'):
                result['id'] = scored_point.point.str_id

            if with_payload and scored_point.point.payload:
                result['payload'] = MessageToDict(scored_point.point.payload)

            if with_vectors and scored_point.point.HasField('vector'):
                result['vector'] = list(scored_point.point.vector.data)

            results.append(result)

        return results
