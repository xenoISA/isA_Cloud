#!/usr/bin/env python3
"""
Redis gRPC Client
Redis cache client
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from .base_client import BaseGRPCClient
from .proto import redis_service_pb2, redis_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class RedisClient(BaseGRPCClient):
    """Redis gRPC Client"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 organization_id: Optional[str] = None, lazy_connect: bool = True,
                 enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        Initialize Redis client

        Args:
            host: Service host (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'redis')
        """
        # Let BaseGRPCClient handle Consul discovery and fallback defaults
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
        self.organization_id = organization_id or 'default-org'

    def _create_stub(self):
        """Create Redis service stub"""
        return redis_service_pb2_grpc.RedisServiceStub(self.channel)

    def service_name(self) -> str:
        return "Redis"

    def default_port(self) -> int:
        return 50055

    def health_check(self) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.RedisHealthCheckRequest(
                deep_check=False
            )
            response = self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'redis_status': response.redis_status,
                'connected_clients': response.connected_clients,
                'used_memory_bytes': response.used_memory_bytes
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    def set(self, key: str, value: str, ttl_seconds: int = 0) -> Optional[bool]:
        """Set key-value"""
        try:
            self._ensure_connected()

            # Use SetWithExpirationRequest if TTL is provided
            if ttl_seconds > 0:
                from google.protobuf.duration_pb2 import Duration
                duration = Duration()
                duration.seconds = ttl_seconds

                request = redis_service_pb2.SetWithExpirationRequest(
                    user_id=self.user_id,
                    organization_id=self.organization_id,
                    key=key,
                    value=value,
                    expiration=duration
                )
                response = self.stub.SetWithExpiration(request)
            else:
                request = redis_service_pb2.SetRequest(
                    user_id=self.user_id,
                    organization_id=self.organization_id,
                    key=key,
                    value=value
                )
                response = self.stub.Set(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Set key-value")
            return False

    def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.GetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.Get(request)

            if response.found:
                return response.value
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get key-value")

    def delete(self, key: str) -> Optional[bool]:
        """Delete key"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.DeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.Delete(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Delete key")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ExistsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.Exists(request)

            return response.exists

        except Exception as e:
            self.handle_error(e, "Check key exists")
            return False

    def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> Optional[bool]:
        """Set key-value with TTL"""
        return self.set(key, value, ttl_seconds)

    def append(self, key: str, value: str) -> Optional[int]:
        """Append value to key"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.AppendRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                value=value
            )

            response = self.stub.Append(request)

            return response.length

        except Exception as e:
            return self.handle_error(e, "Append to key")

    def mset(self, key_values: Dict[str, str]) -> Optional[bool]:
        """Batch set key-values"""
        try:
            self._ensure_connected()
            
            # Set each key-value pair individually since proto doesn't have MSet
            success_count = 0
            for key, value in key_values.items():
                request = redis_service_pb2.SetRequest(
                    user_id=self.user_id,
                    organization_id=self.organization_id,
                    key=key,
                    value=value
                )
                response = self.stub.Set(request)
                if response.success:
                    success_count += 1

            if success_count == len(key_values):
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Batch set key-values")
            return False

    def mget(self, keys: List[str]) -> Dict[str, str]:
        """Batch get key-values"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.GetMultipleRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = self.stub.GetMultiple(request)

            # Convert KeyValue list to dict
            values = {kv.key: kv.value for kv in response.values}
            return values

        except Exception as e:
            return self.handle_error(e, "Batch get key-values") or {}

    def incr(self, key: str, delta: int = 1) -> Optional[int]:
        """Increment"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.IncrementRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                delta=delta
            )

            response = self.stub.Increment(request)

            return response.value

        except Exception as e:
            return self.handle_error(e, "Increment")

    def decr(self, key: str, delta: int = 1) -> Optional[int]:
        """Decrement"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.DecrementRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                delta=delta
            )

            response = self.stub.Decrement(request)

            return response.value

        except Exception as e:
            return self.handle_error(e, "Decrement")

    def expire(self, key: str, seconds: int) -> Optional[bool]:
        """Set expiration time"""
        try:
            self._ensure_connected()
            
            from google.protobuf.duration_pb2 import Duration
            duration = Duration()
            duration.seconds = seconds
            
            request = redis_service_pb2.ExpireRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                expiration=duration
            )

            response = self.stub.Expire(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Set expiration")
            return False

    def ttl(self, key: str) -> Optional[int]:
        """Get time to live (seconds)"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.GetTTLRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.GetTTL(request)

            return response.ttl_seconds

        except Exception as e:
            return self.handle_error(e, "Get TTL")

    def delete_multiple(self, keys: List[str]) -> Optional[int]:
        """Delete multiple keys"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.DeleteMultipleRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = self.stub.DeleteMultiple(request)

            if response.success:
                return response.deleted_count
            else:
                return 0

        except Exception as e:
            self.handle_error(e, "Delete multiple keys")
            return 0

    def rename(self, old_key: str, new_key: str) -> Optional[bool]:
        """Rename key"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.RenameRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                old_key=old_key,
                new_key=new_key
            )

            response = self.stub.Rename(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Rename key")
            return False

    def list_keys(self, pattern: str = "*", limit: int = 100) -> List[str]:
        """List keys matching pattern"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ListKeysRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                pattern=pattern,
                limit=limit
            )

            response = self.stub.ListKeys(request)

            return list(response.keys)

        except Exception as e:
            return self.handle_error(e, "List keys") or []

    def lpush(self, key: str, values: List[str]) -> Optional[int]:
        """Left push to list"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.LPushRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                values=values
            )

            response = self.stub.LPush(request)

            return response.length

        except Exception as e:
            return self.handle_error(e, "Left push to list")

    def rpush(self, key: str, values: List[str]) -> Optional[int]:
        """Right push to list"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.RPushRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                values=values
            )

            response = self.stub.RPush(request)

            return response.length

        except Exception as e:
            return self.handle_error(e, "Right push to list")

    def lrange(self, key: str, start: int = 0, stop: int = -1) -> List[str]:
        """Get list range"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.LRangeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                start=start,
                stop=stop
            )

            response = self.stub.LRange(request)

            return list(response.values)

        except Exception as e:
            return self.handle_error(e, "Get list range") or []

    def lpop(self, key: str) -> Optional[str]:
        """Pop element from left of list"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.LPopRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.LPop(request)

            if response.found:
                return response.value
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Left pop from list")

    def rpop(self, key: str) -> Optional[str]:
        """Pop element from right of list"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.RPopRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.RPop(request)

            if response.found:
                return response.value
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Right pop from list")

    def llen(self, key: str) -> Optional[int]:
        """Get list length"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.LLenRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.LLen(request)

            return response.length

        except Exception as e:
            return self.handle_error(e, "Get list length")

    def lindex(self, key: str, index: int) -> Optional[str]:
        """Get list element at index"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.LIndexRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                index=index
            )

            response = self.stub.LIndex(request)

            if response.found:
                return response.value
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get list element")

    def ltrim(self, key: str, start: int, stop: int) -> Optional[bool]:
        """Trim list to specified range"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.LTrimRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                start=start,
                stop=stop
            )

            response = self.stub.LTrim(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Trim list")
            return False

    def hset(self, key: str, field: str, value: str) -> Optional[bool]:
        """Set hash field"""
        try:
            self._ensure_connected()

            # Create HashField message
            hash_field = redis_service_pb2.HashField(field=field, value=value)

            request = redis_service_pb2.HSetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                fields=[hash_field]
            )

            response = self.stub.HSet(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Set hash field")
            return False

    def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HGetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                field=field
            )

            response = self.stub.HGet(request)

            if response.found:
                return response.value
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get hash field")

    def hgetall(self, key: str) -> Dict[str, str]:
        """Get all hash fields"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HGetAllRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.HGetAll(request)

            # Convert repeated HashField to dict
            fields = {f.field: f.value for f in response.fields}
            return fields

        except Exception as e:
            return self.handle_error(e, "Get all hash fields") or {}

    def hdelete(self, key: str, fields: List[str]) -> Optional[int]:
        """Delete hash fields"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HDeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                fields=fields
            )

            response = self.stub.HDelete(request)

            if response.success:
                return response.deleted_count
            else:
                return 0

        except Exception as e:
            self.handle_error(e, "Delete hash fields")
            return 0

    def hexists(self, key: str, field: str) -> bool:
        """Check if hash field exists"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HExistsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                field=field
            )

            response = self.stub.HExists(request)

            return response.exists

        except Exception as e:
            self.handle_error(e, "Check hash field exists")
            return False

    def hkeys(self, key: str) -> List[str]:
        """Get all hash field names"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HKeysRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.HKeys(request)

            return list(response.fields)

        except Exception as e:
            return self.handle_error(e, "Get hash keys") or []

    def hvalues(self, key: str) -> List[str]:
        """Get all hash values"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HValuesRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.HValues(request)

            return list(response.values)

        except Exception as e:
            return self.handle_error(e, "Get hash values") or []

    def hincrement(self, key: str, field: str, delta: int = 1) -> Optional[int]:
        """Increment hash field value"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.HIncrementRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                field=field,
                delta=delta
            )

            response = self.stub.HIncrement(request)

            return response.value

        except Exception as e:
            return self.handle_error(e, "Increment hash field")

    # ============================================
    # Set Operations
    # ============================================

    def sadd(self, key: str, members: List[str]) -> Optional[int]:
        """Add members to set"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SAddRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = self.stub.SAdd(request)

            return response.added_count

        except Exception as e:
            return self.handle_error(e, "Add to set")

    def sremove(self, key: str, members: List[str]) -> Optional[int]:
        """Remove members from set"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SRemoveRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = self.stub.SRemove(request)

            return response.removed_count

        except Exception as e:
            return self.handle_error(e, "Remove from set")

    def smembers(self, key: str) -> List[str]:
        """Get all set members"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SMembersRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.SMembers(request)

            return list(response.members)

        except Exception as e:
            return self.handle_error(e, "Get set members") or []

    def sismember(self, key: str, member: str) -> bool:
        """Check if member is in set"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SIsMemberRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member
            )

            response = self.stub.SIsMember(request)

            return response.is_member

        except Exception as e:
            self.handle_error(e, "Check set membership")
            return False

    def scard(self, key: str) -> Optional[int]:
        """Get set cardinality (size)"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SCardRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.SCard(request)

            return response.count

        except Exception as e:
            return self.handle_error(e, "Get set cardinality")

    def sunion(self, keys: List[str]) -> List[str]:
        """Get union of sets"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SUnionRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = self.stub.SUnion(request)

            return list(response.members)

        except Exception as e:
            return self.handle_error(e, "Get set union") or []

    def sinter(self, keys: List[str]) -> List[str]:
        """Get intersection of sets"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SInterRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = self.stub.SInter(request)

            return list(response.members)

        except Exception as e:
            return self.handle_error(e, "Get set intersection") or []

    def sdiff(self, keys: List[str]) -> List[str]:
        """Get difference of sets"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.SDiffRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = self.stub.SDiff(request)

            return list(response.members)

        except Exception as e:
            return self.handle_error(e, "Get set difference") or []

    # ============================================
    # Sorted Set Operations
    # ============================================

    def zadd(self, key: str, score_members: Dict[str, float]) -> Optional[int]:
        """
        Add members to sorted set with scores

        Args:
            key: Sorted set key
            score_members: Dict of {member: score}

        Returns:
            Number of members added
        """
        try:
            self._ensure_connected()

            # Create ZSetMember messages
            members = [
                redis_service_pb2.ZSetMember(member=member, score=score)
                for member, score in score_members.items()
            ]

            request = redis_service_pb2.ZAddRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = self.stub.ZAdd(request)

            return response.added_count

        except Exception as e:
            self.handle_error(e, "Add to sorted set")
            return None

    def zrange(self, key: str, start: int = 0, stop: int = -1, with_scores: bool = False) -> List:
        """
        Get sorted set range

        Args:
            key: Sorted set key
            start: Start index
            stop: Stop index (-1 for end)
            with_scores: Return scores with members

        Returns:
            List of members or list of (member, score) tuples if with_scores=True
        """
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZRangeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                start=start,
                stop=stop,
                with_scores=with_scores
            )

            response = self.stub.ZRange(request)

            if with_scores:
                result = [(m.member, m.score) for m in response.members]
            else:
                result = [m.member for m in response.members]

            return result

        except Exception as e:
            return self.handle_error(e, "Get sorted set range") or []

    def zrem(self, key: str, members: List[str]) -> Optional[int]:
        """
        Remove members from sorted set

        Args:
            key: Sorted set key
            members: List of members to remove

        Returns:
            Number of members removed
        """
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZRemoveRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = self.stub.ZRemove(request)

            return response.removed_count

        except Exception as e:
            self.handle_error(e, "Remove from sorted set")
            return None

    def zremrangebyrank(self, key: str, start: int, stop: int) -> Optional[int]:
        """
        Remove sorted set members by rank range

        Args:
            key: Sorted set key
            start: Start rank
            stop: Stop rank

        Returns:
            Number of members removed
        """
        try:
            # Get members in range first
            members_to_remove = self.zrange(key, start, stop, with_scores=False)

            if not members_to_remove:
                return 0

            # Remove them
            return self.zrem(key, members_to_remove)

        except Exception as e:
            self.handle_error(e, "Remove sorted set by rank")
            return None

    def zrange_by_score(self, key: str, min_score: float, max_score: float, 
                        offset: int = 0, count: int = -1) -> List[tuple]:
        """
        Get sorted set members by score range

        Args:
            key: Sorted set key
            min_score: Minimum score
            max_score: Maximum score
            offset: Offset for pagination
            count: Number of results (-1 for all)

        Returns:
            List of (member, score) tuples
        """
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZRangeByScoreRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                min_score=min_score,
                max_score=max_score,
                offset=offset,
                count=count
            )

            response = self.stub.ZRangeByScore(request)

            result = [(m.member, m.score) for m in response.members]
            return result

        except Exception as e:
            return self.handle_error(e, "Get sorted set by score") or []

    def zrank(self, key: str, member: str) -> Optional[int]:
        """Get member rank in sorted set"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZRankRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member
            )

            response = self.stub.ZRank(request)

            if response.found:
                return response.rank
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get sorted set rank")

    def zscore(self, key: str, member: str) -> Optional[float]:
        """Get member score in sorted set"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZScoreRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member
            )

            response = self.stub.ZScore(request)

            if response.found:
                return response.score
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get sorted set score")

    def zcard(self, key: str) -> Optional[int]:
        """Get sorted set cardinality (size)"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZCardRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.ZCard(request)

            return response.count

        except Exception as e:
            return self.handle_error(e, "Get sorted set cardinality")

    def zincrement(self, key: str, member: str, delta: float = 1.0) -> Optional[float]:
        """Increment member score in sorted set"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ZIncrementRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member,
                delta=delta
            )

            response = self.stub.ZIncrement(request)

            return response.score

        except Exception as e:
            return self.handle_error(e, "Increment sorted set score")


    # ============================================
    # Distributed Lock Operations
    # ============================================

    def acquire_lock(self, lock_key: str, ttl_seconds: int = 10, wait_timeout_seconds: int = 5) -> Optional[str]:
        """
        Acquire distributed lock

        Args:
            lock_key: Lock key
            ttl_seconds: Lock TTL in seconds
            wait_timeout_seconds: Wait timeout in seconds

        Returns:
            lock_id if successful, None otherwise
        """
        try:
            self._ensure_connected()
            
            from google.protobuf.duration_pb2 import Duration
            ttl = Duration()
            ttl.seconds = ttl_seconds
            wait_timeout = Duration()
            wait_timeout.seconds = wait_timeout_seconds
            
            request = redis_service_pb2.AcquireLockRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                lock_key=lock_key,
                ttl=ttl,
                wait_timeout=wait_timeout
            )

            response = self.stub.AcquireLock(request)

            if response.acquired:
                return response.lock_id
            else:
                return None

        except Exception as e:
            self.handle_error(e, "Acquire lock")
            return None

    def release_lock(self, lock_key: str, lock_id: str) -> bool:
        """Release distributed lock"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ReleaseLockRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                lock_key=lock_key,
                lock_id=lock_id
            )

            response = self.stub.ReleaseLock(request)

            if response.released:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Release lock")
            return False

    def renew_lock(self, lock_key: str, lock_id: str, ttl_seconds: int = 10) -> bool:
        """Renew distributed lock"""
        try:
            self._ensure_connected()
            
            from google.protobuf.duration_pb2 import Duration
            ttl = Duration()
            ttl.seconds = ttl_seconds
            
            request = redis_service_pb2.RenewLockRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                lock_key=lock_key,
                lock_id=lock_id,
                ttl=ttl
            )

            response = self.stub.RenewLock(request)

            if response.renewed:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Renew lock")
            return False

    # ============================================
    # Pub/Sub Operations
    # ============================================

    def publish(self, channel: str, message: str) -> Optional[int]:
        """Publish message to channel"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.PublishRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                channel=channel,
                message=message
            )

            response = self.stub.Publish(request)

            return response.subscriber_count

        except Exception as e:
            return self.handle_error(e, "Publish message")

    def subscribe(self, channels: List[str], callback=None):
        """
        Subscribe to channels (streaming)
        
        Args:
            channels: List of channel names
            callback: Function to call for each message (takes channel, message, timestamp)
        """
        try:
            self._ensure_connected()
            request = redis_service_pb2.SubscribeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                channels=channels
            )

            for message in self.stub.Subscribe(request):
                if callback:
                    callback(message.channel, message.message, message.timestamp)

        except Exception as e:
            self.handle_error(e, "Subscribe to channels")

    def unsubscribe(self, channels: List[str]) -> bool:
        """Unsubscribe from channels"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.UnsubscribeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                channels=channels
            )

            response = self.stub.Unsubscribe(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Unsubscribe from channels")
            return False

    # ============================================
    # Batch Operations
    # ============================================

    def execute_batch(self, commands: List[Dict[str, any]]) -> Optional[Dict]:
        """
        Execute batch commands
        
        Args:
            commands: List of command dicts with keys: operation, key, value, expiration
        """
        try:
            self._ensure_connected()
            
            batch_commands = []
            for cmd in commands:
                from google.protobuf.duration_pb2 import Duration
                
                expiration = None
                if 'expiration' in cmd and cmd['expiration']:
                    expiration = Duration()
                    expiration.seconds = cmd['expiration']
                
                batch_cmd = redis_service_pb2.BatchCommand(
                    operation=cmd.get('operation', ''),
                    key=cmd.get('key', ''),
                    value=cmd.get('value', ''),
                    expiration=expiration
                )
                batch_commands.append(batch_cmd)
            
            request = redis_service_pb2.RedisBatchRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                commands=batch_commands
            )

            response = self.stub.ExecuteBatch(request)

            if response.success:
                return {
                    'success': True,
                    'executed_count': response.executed_count,
                    'errors': list(response.errors)
                }
            else:
                return {
                    'success': False,
                    'executed_count': response.executed_count,
                    'errors': list(response.errors)
                }

        except Exception as e:
            self.handle_error(e, "Execute batch")
            return None

    # ============================================
    # Session Management
    # ============================================

    def create_session(self, data: Dict[str, str], ttl_seconds: int = 3600) -> Optional[str]:
        """Create session"""
        try:
            self._ensure_connected()
            
            from google.protobuf.duration_pb2 import Duration
            ttl = Duration()
            ttl.seconds = ttl_seconds
            
            request = redis_service_pb2.CreateSessionRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                data=data,
                ttl=ttl
            )

            response = self.stub.CreateSession(request)

            return response.session_id

        except Exception as e:
            return self.handle_error(e, "Create session")

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.GetSessionRequest(
                user_id=self.user_id,
                session_id=session_id
            )

            response = self.stub.GetSession(request)

            if response.found:
                return dict(response.session.data)
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get session")

    def update_session(self, session_id: str, data: Dict[str, str], extend_ttl: bool = True) -> bool:
        """Update session"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.UpdateSessionRequest(
                user_id=self.user_id,
                session_id=session_id,
                data=data,
                extend_ttl=extend_ttl
            )

            response = self.stub.UpdateSession(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Update session")
            return False

    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.DeleteSessionRequest(
                user_id=self.user_id,
                session_id=session_id
            )

            response = self.stub.DeleteSession(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Delete session")
            return False

    def list_sessions(self) -> List[Dict]:
        """List all sessions"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.ListSessionsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.ListSessions(request)

            sessions = []
            for session in response.sessions:
                sessions.append({
                    'session_id': session.session_id,
                    'user_id': session.user_id,
                    'data': dict(session.data),
                    'created_at': session.created_at,
                    'expires_at': session.expires_at
                })

            return sessions

        except Exception as e:
            return self.handle_error(e, "List sessions") or []

    # ============================================
    # Monitoring Operations
    # ============================================

    def get_statistics(self) -> Optional[Dict]:
        """Get Redis statistics"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.GetStatistics(request)

            stats = {
                'total_keys': response.total_keys,
                'memory_used_bytes': response.memory_used_bytes,
                'commands_processed': response.commands_processed,
                'connections_received': response.connections_received,
                'hit_rate': response.hit_rate,
                'key_type_distribution': dict(response.key_type_distribution)
            }

            return stats

        except Exception as e:
            return self.handle_error(e, "Get statistics")

    def get_key_info(self, key: str) -> Optional[Dict]:
        """Get key information"""
        try:
            self._ensure_connected()
            request = redis_service_pb2.GetKeyInfoRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = self.stub.GetKeyInfo(request)

            if response.exists:
                info = {
                    'exists': True,
                    'type': response.type,
                    'ttl_seconds': response.ttl_seconds,
                    'size_bytes': response.size_bytes,
                    'created_at': response.created_at,
                    'last_accessed': response.last_accessed
                }
                return info
            else:
                return {'exists': False}

        except Exception as e:
            return self.handle_error(e, "Get key info")


# Convenience usage example
if __name__ == '__main__':
    with RedisClient(host='localhost', port=50055, user_id='test_user') as client:
        # Health check
        client.health_check()

        # Basic operations
        client.set('user:1:name', 'John Doe')
        name = client.get('user:1:name')

        # With TTL
        client.set_with_ttl('session:abc123', 'user_data', ttl_seconds=3600)
        ttl = client.ttl('session:abc123')

        # Batch operations
        client.mset({
            'user:2:name': 'Jane Smith',
            'user:2:email': 'jane@example.com',
            'user:2:age': '25'
        })

        users = client.mget(['user:2:name', 'user:2:email', 'user:2:age'])

        # Counter
        counter = client.incr('page:views')

        # List operations
        client.lpush('logs', ['log1', 'log2', 'log3'])
        logs = client.lrange('logs', 0, -1)

        # Hash operations
        client.hset('user:3', 'name', 'Bob Wilson')
        client.hset('user:3', 'email', 'bob@example.com')
        user_data = client.hgetall('user:3')
