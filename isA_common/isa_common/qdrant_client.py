#!/usr/bin/env python3
"""
Qdrant gRPC Client
Qdrant vector database client
"""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
from .base_client import BaseGRPCClient
from .proto import qdrant_service_pb2, qdrant_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class QdrantClient(BaseGRPCClient):
    """Qdrant gRPC client"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        Initialize Qdrant client

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'qdrant')
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
        """Create Qdrant service stub"""
        return qdrant_service_pb2_grpc.QdrantServiceStub(self.channel)

    def service_name(self) -> str:
        return "Qdrant"

    def default_port(self) -> int:
        return 50062

    def health_check(self) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = qdrant_service_pb2.QdrantHealthCheckRequest()
            response = self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'version': response.version
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    def create_collection(self, collection_name: str, vector_size: int,
                         distance: str = 'Cosine') -> Optional[bool]:
        """Create vector collection

        Args:
            collection_name: Collection name
            vector_size: Vector dimension size
            distance: Distance metric (Cosine, Euclid, Dot, Manhattan)

        Returns:
            True if successful, None otherwise
        """
        try:
            self._ensure_connected()

            # Map distance string to enum (aligned with Qdrant official proto)
            distance_map = {
                'Cosine': qdrant_service_pb2.DISTANCE_COSINE,       # 1
                'Euclid': qdrant_service_pb2.DISTANCE_EUCLID,       # 2
                'Dot': qdrant_service_pb2.DISTANCE_DOT,             # 3
                'Manhattan': qdrant_service_pb2.DISTANCE_MANHATTAN  # 4
            }

            vector_params = qdrant_service_pb2.VectorParams(
                size=vector_size,
                distance=distance_map.get(distance, qdrant_service_pb2.DISTANCE_COSINE)
            )

            # CreateCollectionRequest uses oneof vectors_config
            request = qdrant_service_pb2.CreateCollectionRequest(
                collection_name=collection_name
            )
            request.vector_params.CopyFrom(vector_params)

            response = self.stub.CreateCollection(request)

            if response.metadata.success:
                return True
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Create collection")

    def list_collections(self) -> List[str]:
        """List all collections

        Returns:
            List of collection names
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.ListCollectionsRequest()
            response = self.stub.ListCollections(request)

            if response.metadata.success:
                collections = [c.name for c in response.collections]
                return collections
            else:
                return []

        except Exception as e:
            self.handle_error(e, "List collections")
            return []

    def delete_collection(self, collection_name: str) -> Optional[bool]:
        """Delete collection

        Args:
            collection_name: Collection name

        Returns:
            True if successful
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.DeleteCollectionRequest(
                collection_name=collection_name
            )

            response = self.stub.DeleteCollection(request)

            if response.metadata.success:
                return True
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete collection")

    def upsert_points(self, collection_name: str, points: List[Dict[str, Any]]) -> Optional[str]:
        """Insert or update vector points

        Args:
            collection_name: Collection name
            points: List of point dictionaries with 'id', 'vector', 'payload'
                   Example: {'id': 1, 'vector': [0.1, 0.2, ...], 'payload': {'key': 'value'}}

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

            proto_points = []
            for p in points:
                # Create point ID (using oneof)
                point_id = p.get('id')
                if isinstance(point_id, int):
                    point = qdrant_service_pb2.Point(num_id=point_id)
                else:
                    point = qdrant_service_pb2.Point(str_id=str(point_id))

                # Create vector (using oneof)
                vector = qdrant_service_pb2.Vector(data=p.get('vector', []))
                point.vector.CopyFrom(vector)

                # Add payload if provided
                if 'payload' in p and p['payload']:
                    from google.protobuf.struct_pb2 import Struct
                    payload_struct = Struct()
                    payload_struct.update(p['payload'])
                    point.payload.CopyFrom(payload_struct)

                proto_points.append(point)

            request = qdrant_service_pb2.UpsertPointsRequest(
                collection_name=collection_name,
                points=proto_points,
                wait=True
            )

            response = self.stub.UpsertPoints(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Upsert points")

    def search(self, collection_name: str, vector: List[float], limit: int = 10,
               score_threshold: Optional[float] = None, with_payload: bool = True,
               with_vectors: bool = False) -> Optional[List[Dict]]:
        """Vector similarity search

        Args:
            collection_name: Collection name
            vector: Query vector
            limit: Maximum number of results
            score_threshold: Minimum score threshold
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            List of search results with score and point data
        """
        try:
            self._ensure_connected()

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

            response = self.stub.Search(request)

            if response.metadata.success:
                results = []
                for scored_point in response.result:
                    result = {
                        'score': scored_point.score,
                        'id': None,
                        'payload': None,
                        'vector': None
                    }

                    # Extract ID (using oneof field names)
                    if scored_point.point.HasField('num_id'):
                        result['id'] = scored_point.point.num_id
                    elif scored_point.point.HasField('str_id'):
                        result['id'] = scored_point.point.str_id

                    # Extract payload (google.protobuf.Struct doesn't use HasField)
                    if with_payload and scored_point.point.payload:
                        from google.protobuf.json_format import MessageToDict
                        result['payload'] = MessageToDict(scored_point.point.payload)

                    # Extract vector (using oneof field name)
                    if with_vectors and scored_point.point.HasField('vector'):
                        result['vector'] = list(scored_point.point.vector.data)

                    results.append(result)

                return results
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Search")

    def delete_points(self, collection_name: str, ids: List[Any]) -> Optional[str]:
        """Delete vector points

        Args:
            collection_name: Collection name
            ids: List of point IDs to delete

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

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

            response = self.stub.DeletePoints(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete points")

    def count_points(self, collection_name: str) -> Optional[int]:
        """Count points in collection

        Args:
            collection_name: Collection name

        Returns:
            Number of points in collection
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.CountRequest(
                collection_name=collection_name,
                exact=True
            )

            response = self.stub.Count(request)

            if response.metadata.success:
                count = response.count
                return count
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Count points")

    def get_collection_info(self, collection_name: str) -> Optional[Dict]:
        """Get collection information

        Args:
            collection_name: Collection name

        Returns:
            Collection info dictionary
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.GetCollectionInfoRequest(
                collection_name=collection_name
            )

            response = self.stub.GetCollectionInfo(request)

            if response.metadata.success:
                info = {
                    'status': response.info.status,
                    'points_count': response.info.points_count,
                    'segments_count': response.info.segments_count
                }
                return info
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get collection info")

    # ============================================
    # Advanced Search Operations
    # ============================================

    def search_with_filter(self, collection_name: str, vector: List[float],
                          filter_conditions: Optional[Dict] = None,
                          limit: int = 10, score_threshold: Optional[float] = None,
                          offset: Optional[int] = None, with_payload: bool = True,
                          with_vectors: bool = False, params: Optional[Dict] = None) -> Optional[List[Dict]]:
        """Vector search with advanced filtering and options

        Args:
            collection_name: Collection name
            vector: Query vector
            filter_conditions: Filter conditions dictionary with 'must', 'should', 'must_not' keys
            limit: Maximum number of results
            score_threshold: Minimum score threshold
            offset: Pagination offset
            with_payload: Include payload in results
            with_vectors: Include vectors in results
            params: Search parameters (hnsw_ef, exact, etc.)

        Returns:
            List of search results

        Example filter_conditions:
            {
                'must': [
                    {'field': 'category', 'match': {'keyword': 'electronics'}},
                    {'field': 'price', 'range': {'lte': 1000}}
                ]
            }
        """
        try:
            self._ensure_connected()

            proto_vector = qdrant_service_pb2.Vector(data=vector)

            request = qdrant_service_pb2.SearchRequest(
                collection_name=collection_name,
                vector=proto_vector,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            # Add filter if provided
            if filter_conditions:
                proto_filter = self._build_filter(filter_conditions)
                request.filter.CopyFrom(proto_filter)

            # Add score threshold
            if score_threshold is not None:
                request.score_threshold = score_threshold

            # Add offset
            if offset is not None:
                request.offset = offset

            # Add search params
            if params:
                from google.protobuf.struct_pb2 import Struct
                params_struct = Struct()
                params_struct.update(params)
                request.params.CopyFrom(params_struct)

            response = self.stub.Search(request)

            if response.metadata.success:
                results = self._parse_scored_points(response.result, with_payload, with_vectors)
                return results
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Search with filter")

    def scroll(self, collection_name: str, filter_conditions: Optional[Dict] = None,
              limit: int = 100, offset_id: Optional[Any] = None,
              with_payload: bool = True, with_vectors: bool = False) -> Optional[Dict]:
        """Scroll through all points in collection

        Args:
            collection_name: Collection name
            filter_conditions: Optional filter conditions
            limit: Number of points per page
            offset_id: Start from this point ID
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            Dictionary with 'points' and 'next_offset' keys
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.ScrollRequest(
                collection_name=collection_name,
                limit=limit,
                with_payload=with_payload,
                with_vectors=with_vectors
            )

            # Add filter if provided
            if filter_conditions:
                proto_filter = self._build_filter(filter_conditions)
                request.filter.CopyFrom(proto_filter)

            # Add offset if provided
            if offset_id is not None:
                if isinstance(offset_id, int):
                    request.offset.num = offset_id
                else:
                    request.offset.str = str(offset_id)

            response = self.stub.Scroll(request)

            if response.metadata.success:
                points = []
                for point in response.points:
                    point_data = {'id': None, 'payload': None, 'vector': None}

                    # Extract ID
                    if point.HasField('num_id'):
                        point_data['id'] = point.num_id
                    elif point.HasField('str_id'):
                        point_data['id'] = point.str_id

                    # Extract payload
                    if with_payload and point.payload:
                        from google.protobuf.json_format import MessageToDict
                        point_data['payload'] = MessageToDict(point.payload)

                    # Extract vector
                    if with_vectors and point.HasField('vector'):
                        point_data['vector'] = list(point.vector.data)

                    points.append(point_data)

                # Extract next offset
                next_offset = None
                if response.HasField('next_page_offset'):
                    if response.next_page_offset.HasField('num'):
                        next_offset = response.next_page_offset.num
                    elif response.next_page_offset.HasField('str'):
                        next_offset = response.next_page_offset.str

                return {'points': points, 'next_offset': next_offset}
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Scroll")

    def recommend(self, collection_name: str, positive: List[Any], negative: List[Any] = None,
                 filter_conditions: Optional[Dict] = None, limit: int = 10,
                 with_payload: bool = True, with_vectors: bool = False) -> Optional[List[Dict]]:
        """Recommendation search based on positive/negative examples

        Args:
            collection_name: Collection name
            positive: List of positive example IDs
            negative: List of negative example IDs (optional)
            filter_conditions: Optional filter conditions
            limit: Maximum number of results
            with_payload: Include payload in results
            with_vectors: Include vectors in results

        Returns:
            List of recommended results
        """
        try:
            self._ensure_connected()

            # Build positive IDs
            positive_ids = []
            for pid in positive:
                if isinstance(pid, int):
                    positive_ids.append(qdrant_service_pb2.PointId(num=pid))
                else:
                    positive_ids.append(qdrant_service_pb2.PointId(str=str(pid)))

            # Build negative IDs
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

            # Add filter if provided
            if filter_conditions:
                proto_filter = self._build_filter(filter_conditions)
                request.filter.CopyFrom(proto_filter)

            response = self.stub.Recommend(request)

            if response.metadata.success:
                results = self._parse_scored_points(response.result, with_payload, with_vectors)
                return results
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Recommend")

    # ============================================
    # Payload Operations
    # ============================================

    def update_payload(self, collection_name: str, ids: List[Any],
                      payload: Dict[str, Any]) -> Optional[str]:
        """Update payload for specific points

        Args:
            collection_name: Collection name
            ids: List of point IDs
            payload: Payload data to update

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

            # Build point IDs
            proto_ids = []
            for point_id in ids:
                if isinstance(point_id, int):
                    proto_ids.append(qdrant_service_pb2.PointId(num=point_id))
                else:
                    proto_ids.append(qdrant_service_pb2.PointId(str=str(point_id)))

            point_id_list = qdrant_service_pb2.PointIdList(ids=proto_ids)

            # Convert payload to struct
            from google.protobuf.struct_pb2 import Struct
            payload_struct = Struct()
            payload_struct.update(payload)

            request = qdrant_service_pb2.UpdatePayloadRequest(
                collection_name=collection_name,
                ids=point_id_list,
                payload=payload_struct,
                wait=True
            )

            response = self.stub.UpdatePayload(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Update payload")

    def delete_payload_fields(self, collection_name: str, ids: List[Any],
                             keys: List[str]) -> Optional[str]:
        """Delete specific payload fields

        Args:
            collection_name: Collection name
            ids: List of point IDs
            keys: List of payload field names to delete

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

            # Build point IDs
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

            response = self.stub.DeletePayload(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete payload fields")

    def clear_payload(self, collection_name: str, ids: List[Any]) -> Optional[str]:
        """Clear all payload data from points

        Args:
            collection_name: Collection name
            ids: List of point IDs

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

            # Build point IDs
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

            response = self.stub.ClearPayload(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Clear payload")

    # ============================================
    # Index Management
    # ============================================

    def create_field_index(self, collection_name: str, field_name: str,
                          field_type: str = 'keyword') -> Optional[str]:
        """Create index on payload field

        Args:
            collection_name: Collection name
            field_name: Field name to index
            field_type: Field type (keyword, integer, float, geo, text)

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.CreateFieldIndexRequest(
                collection_name=collection_name,
                field_name=field_name,
                field_type=field_type,
                wait=True
            )

            response = self.stub.CreateFieldIndex(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Create field index")

    def delete_field_index(self, collection_name: str, field_name: str) -> Optional[str]:
        """Delete payload field index

        Args:
            collection_name: Collection name
            field_name: Field name

        Returns:
            Operation ID if successful
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.DeleteFieldIndexRequest(
                collection_name=collection_name,
                field_name=field_name,
                wait=True
            )

            response = self.stub.DeleteFieldIndex(request)

            if response.metadata.success:
                return response.operation_id
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete field index")

    # ============================================
    # Snapshot Operations
    # ============================================

    def create_snapshot(self, collection_name: str) -> Optional[str]:
        """Create collection snapshot

        Args:
            collection_name: Collection name

        Returns:
            Snapshot name if successful
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.CreateSnapshotRequest(
                collection_name=collection_name
            )

            response = self.stub.CreateSnapshot(request)

            if response.metadata.success:
                return response.snapshot_name
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Create snapshot")

    def list_snapshots(self, collection_name: str) -> Optional[List[Dict]]:
        """List all snapshots for collection

        Args:
            collection_name: Collection name

        Returns:
            List of snapshot descriptions
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.ListSnapshotsRequest(
                collection_name=collection_name
            )

            response = self.stub.ListSnapshots(request)

            if response.metadata.success:
                snapshots = []
                for snap in response.snapshots:
                    snapshots.append({
                        'name': snap.name,
                        'created_at': snap.created_at.ToDatetime(),
                        'size_bytes': snap.size_bytes
                    })
                return snapshots
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "List snapshots")

    def delete_snapshot(self, collection_name: str, snapshot_name: str) -> Optional[bool]:
        """Delete snapshot

        Args:
            collection_name: Collection name
            snapshot_name: Snapshot name

        Returns:
            True if successful
        """
        try:
            self._ensure_connected()

            request = qdrant_service_pb2.DeleteSnapshotRequest(
                collection_name=collection_name,
                snapshot_name=snapshot_name
            )

            response = self.stub.DeleteSnapshot(request)

            if response.metadata.success:
                return True
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Delete snapshot")

    # ============================================
    # Helper Methods
    # ============================================

    def _build_filter(self, filter_conditions: Dict) -> "qdrant_service_pb2.Filter":
        """Build protobuf Filter from dictionary

        Args:
            filter_conditions: Dictionary with 'must', 'should', 'must_not' keys

        Returns:
            Protobuf Filter object
        """
        proto_filter = qdrant_service_pb2.Filter()

        # Build must conditions
        if 'must' in filter_conditions:
            for cond in filter_conditions['must']:
                proto_filter.must.append(self._build_filter_condition(cond))

        # Build should conditions
        if 'should' in filter_conditions:
            for cond in filter_conditions['should']:
                proto_filter.should.append(self._build_filter_condition(cond))

        # Build must_not conditions
        if 'must_not' in filter_conditions:
            for cond in filter_conditions['must_not']:
                proto_filter.must_not.append(self._build_filter_condition(cond))

        return proto_filter

    def _build_filter_condition(self, condition: Dict) -> "qdrant_service_pb2.FilterCondition":
        """Build protobuf FilterCondition from dictionary

        Args:
            condition: Condition dictionary with 'field' and condition type

        Returns:
            Protobuf FilterCondition object
        """
        filter_cond = qdrant_service_pb2.FilterCondition(field=condition['field'])

        # Match condition
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

        # Range condition
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

        # Geo bounding box
        elif 'geo_bounding_box' in condition:
            geo_box = qdrant_service_pb2.GeoBoundingBoxCondition(
                top_left=qdrant_service_pb2.GeoPoint(**condition['geo_bounding_box']['top_left']),
                bottom_right=qdrant_service_pb2.GeoPoint(**condition['geo_bounding_box']['bottom_right'])
            )
            filter_cond.geo_bounding_box.CopyFrom(geo_box)

        # Geo radius
        elif 'geo_radius' in condition:
            geo_rad = qdrant_service_pb2.GeoRadiusCondition(
                center=qdrant_service_pb2.GeoPoint(**condition['geo_radius']['center']),
                radius_meters=condition['geo_radius']['radius_meters']
            )
            filter_cond.geo_radius.CopyFrom(geo_rad)

        return filter_cond

    def _parse_scored_points(self, scored_points, with_payload: bool, with_vectors: bool) -> List[Dict]:
        """Parse scored points from protobuf to dictionary

        Args:
            scored_points: List of protobuf ScoredPoint objects
            with_payload: Whether payload was requested
            with_vectors: Whether vectors were requested

        Returns:
            List of result dictionaries
        """
        results = []
        for scored_point in scored_points:
            result = {
                'score': scored_point.score,
                'id': None,
                'payload': None,
                'vector': None
            }

            # Extract ID
            if scored_point.point.HasField('num_id'):
                result['id'] = scored_point.point.num_id
            elif scored_point.point.HasField('str_id'):
                result['id'] = scored_point.point.str_id

            # Extract payload
            if with_payload and scored_point.point.payload:
                from google.protobuf.json_format import MessageToDict
                result['payload'] = MessageToDict(scored_point.point.payload)

            # Extract vector
            if with_vectors and scored_point.point.HasField('vector'):
                result['vector'] = list(scored_point.point.vector.data)

            results.append(result)

        return results
