#!/usr/bin/env python3
"""
Async Redis gRPC Client
High-performance async Redis client using grpc.aio

Performance Benefits:
- True async I/O without GIL blocking
- Concurrent request execution (10x-50x throughput improvement)
- Automatic request batching support
- Memory-efficient connection pooling
"""

from typing import List, Dict, Optional, AsyncIterator, TYPE_CHECKING
from .async_base_client import AsyncBaseGRPCClient, BatchedRedisGet, BatchedRedisSet
from .proto import redis_service_pb2, redis_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class AsyncRedisClient(AsyncBaseGRPCClient):
    """Async Redis gRPC Client for high-performance concurrent operations."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        lazy_connect: bool = True,
        enable_compression: bool = True,
        enable_retry: bool = True,
        consul_registry: Optional['ConsulRegistry'] = None,
        service_name_override: Optional[str] = None,
        enable_auto_batching: bool = False,
        auto_batch_size: int = 100,
        auto_batch_wait_ms: int = 5
    ):
        """
        Initialize async Redis client.

        Args:
            host: Service host (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional)
            enable_auto_batching: Enable automatic request batching (default: False)
            auto_batch_size: Max items per batch when auto-batching
            auto_batch_wait_ms: Max wait time before flush when auto-batching
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
        self.organization_id = organization_id or 'default-org'

        # Auto-batching support
        self._enable_auto_batching = enable_auto_batching
        self._batched_get: Optional[BatchedRedisGet] = None
        self._batched_set: Optional[BatchedRedisSet] = None
        if enable_auto_batching:
            self._batched_get = BatchedRedisGet(self, auto_batch_size, auto_batch_wait_ms)
            self._batched_set = BatchedRedisSet(self, auto_batch_size, auto_batch_wait_ms)

    def _create_stub(self):
        """Create Redis service stub."""
        return redis_service_pb2_grpc.RedisServiceStub(self.channel)

    def service_name(self) -> str:
        return "Redis"

    def default_port(self) -> int:
        return 50055

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.RedisHealthCheckRequest(deep_check=deep_check)
            response = await self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'redis_status': response.redis_status,
                'connected_clients': response.connected_clients,
                'used_memory_bytes': response.used_memory_bytes
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    # ============================================
    # String Operations
    # ============================================

    async def set(self, key: str, value: str, ttl_seconds: int = 0) -> Optional[bool]:
        """Set key-value."""
        try:
            await self._ensure_connected()

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
                response = await self.stub.SetWithExpiration(request)
            else:
                request = redis_service_pb2.SetRequest(
                    user_id=self.user_id,
                    organization_id=self.organization_id,
                    key=key,
                    value=value
                )
                response = await self.stub.Set(request)

            return response.success

        except Exception as e:
            self.handle_error(e, "Set key-value")
            return False

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        # Use auto-batching if enabled
        if self._enable_auto_batching and self._batched_get:
            return await self._batched_get.get(key)

        try:
            await self._ensure_connected()
            request = redis_service_pb2.GetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.Get(request)

            if response.found:
                return response.value
            return None

        except Exception as e:
            return self.handle_error(e, "Get key-value")

    async def delete(self, key: str) -> Optional[bool]:
        """Delete key."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.DeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.Delete(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "Delete key")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ExistsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.Exists(request)
            return response.exists

        except Exception as e:
            self.handle_error(e, "Check key exists")
            return False

    async def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> Optional[bool]:
        """Set key-value with TTL."""
        return await self.set(key, value, ttl_seconds)

    async def append(self, key: str, value: str) -> Optional[int]:
        """Append value to key."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.AppendRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                value=value
            )

            response = await self.stub.Append(request)
            return response.length

        except Exception as e:
            return self.handle_error(e, "Append to key")

    # ============================================
    # Batch Operations
    # ============================================

    async def mset(self, key_values: Dict[str, str], ttl_seconds: int = 0) -> Optional[bool]:
        """Batch set key-values using ExecuteBatch for optimal performance."""
        try:
            await self._ensure_connected()

            batch_commands = []
            for key, value in key_values.items():
                cmd = redis_service_pb2.BatchCommand(
                    operation='SET',
                    key=key,
                    value=value
                )
                if ttl_seconds > 0:
                    from google.protobuf.duration_pb2 import Duration
                    expiration = Duration()
                    expiration.seconds = ttl_seconds
                    cmd.expiration.CopyFrom(expiration)
                batch_commands.append(cmd)

            request = redis_service_pb2.RedisBatchRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                commands=batch_commands
            )

            response = await self.stub.ExecuteBatch(request)

            if response.success and response.executed_count == len(key_values):
                return True
            return False

        except Exception as e:
            self.handle_error(e, "Batch set key-values")
            return False

    async def mget(self, keys: List[str]) -> Dict[str, str]:
        """Batch get key-values."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.GetMultipleRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = await self.stub.GetMultiple(request)

            values = {kv.key: kv.value for kv in response.values}
            return values

        except Exception as e:
            return self.handle_error(e, "Batch get key-values") or {}

    async def delete_multiple(self, keys: List[str]) -> Optional[int]:
        """Delete multiple keys."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.DeleteMultipleRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                keys=keys
            )

            response = await self.stub.DeleteMultiple(request)

            if response.success:
                return response.deleted_count
            return 0

        except Exception as e:
            self.handle_error(e, "Delete multiple keys")
            return 0

    async def execute_batch(self, commands: List[Dict]) -> Optional[Dict]:
        """Execute batch commands."""
        try:
            await self._ensure_connected()

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

            response = await self.stub.ExecuteBatch(request)

            return {
                'success': response.success,
                'executed_count': response.executed_count,
                'errors': list(response.errors)
            }

        except Exception as e:
            self.handle_error(e, "Execute batch")
            return None

    # ============================================
    # Counter Operations
    # ============================================

    async def incr(self, key: str, delta: int = 1) -> Optional[int]:
        """Increment."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.IncrementRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                delta=delta
            )

            response = await self.stub.Increment(request)
            return response.value

        except Exception as e:
            return self.handle_error(e, "Increment")

    async def decr(self, key: str, delta: int = 1) -> Optional[int]:
        """Decrement."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.DecrementRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                delta=delta
            )

            response = await self.stub.Decrement(request)
            return response.value

        except Exception as e:
            return self.handle_error(e, "Decrement")

    # ============================================
    # Key Operations
    # ============================================

    async def expire(self, key: str, seconds: int) -> Optional[bool]:
        """Set expiration time."""
        try:
            await self._ensure_connected()

            from google.protobuf.duration_pb2 import Duration
            duration = Duration()
            duration.seconds = seconds

            request = redis_service_pb2.ExpireRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                expiration=duration
            )

            response = await self.stub.Expire(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "Set expiration")
            return False

    async def ttl(self, key: str) -> Optional[int]:
        """Get time to live (seconds)."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.GetTTLRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.GetTTL(request)
            return response.ttl_seconds

        except Exception as e:
            return self.handle_error(e, "Get TTL")

    async def rename(self, old_key: str, new_key: str) -> Optional[bool]:
        """Rename key."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.RenameRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                old_key=old_key,
                new_key=new_key
            )

            response = await self.stub.Rename(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "Rename key")
            return False

    async def list_keys(self, pattern: str = "*", limit: int = 100) -> List[str]:
        """List keys matching pattern."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ListKeysRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                pattern=pattern,
                limit=limit
            )

            response = await self.stub.ListKeys(request)
            return list(response.keys)

        except Exception as e:
            return self.handle_error(e, "List keys") or []

    # ============================================
    # List Operations
    # ============================================

    async def lpush(self, key: str, values: List[str]) -> Optional[int]:
        """Left push to list."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.LPushRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                values=values
            )

            response = await self.stub.LPush(request)
            return response.length

        except Exception as e:
            return self.handle_error(e, "Left push to list")

    async def rpush(self, key: str, values: List[str]) -> Optional[int]:
        """Right push to list."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.RPushRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                values=values
            )

            response = await self.stub.RPush(request)
            return response.length

        except Exception as e:
            return self.handle_error(e, "Right push to list")

    async def lrange(self, key: str, start: int = 0, stop: int = -1) -> List[str]:
        """Get list range."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.LRangeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                start=start,
                stop=stop
            )

            response = await self.stub.LRange(request)
            return list(response.values)

        except Exception as e:
            return self.handle_error(e, "Get list range") or []

    async def lpop(self, key: str) -> Optional[str]:
        """Pop element from left of list."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.LPopRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.LPop(request)

            if response.found:
                return response.value
            return None

        except Exception as e:
            return self.handle_error(e, "Left pop from list")

    async def rpop(self, key: str) -> Optional[str]:
        """Pop element from right of list."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.RPopRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.RPop(request)

            if response.found:
                return response.value
            return None

        except Exception as e:
            return self.handle_error(e, "Right pop from list")

    async def llen(self, key: str) -> Optional[int]:
        """Get list length."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.LLenRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.LLen(request)
            return response.length

        except Exception as e:
            return self.handle_error(e, "Get list length")

    # ============================================
    # Hash Operations
    # ============================================

    async def hset(self, key: str, field: str, value: str) -> Optional[bool]:
        """Set hash field."""
        try:
            await self._ensure_connected()

            hash_field = redis_service_pb2.HashField(field=field, value=value)

            request = redis_service_pb2.HSetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                fields=[hash_field]
            )

            response = await self.stub.HSet(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "Set hash field")
            return False

    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.HGetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                field=field
            )

            response = await self.stub.HGet(request)

            if response.found:
                return response.value
            return None

        except Exception as e:
            return self.handle_error(e, "Get hash field")

    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all hash fields."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.HGetAllRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.HGetAll(request)

            fields = {f.field: f.value for f in response.fields}
            return fields

        except Exception as e:
            return self.handle_error(e, "Get all hash fields") or {}

    async def hdelete(self, key: str, fields: List[str]) -> Optional[int]:
        """Delete hash fields."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.HDeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                fields=fields
            )

            response = await self.stub.HDelete(request)

            if response.success:
                return response.deleted_count
            return 0

        except Exception as e:
            self.handle_error(e, "Delete hash fields")
            return 0

    async def hexists(self, key: str, field: str) -> bool:
        """Check if hash field exists."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.HExistsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                field=field
            )

            response = await self.stub.HExists(request)
            return response.exists

        except Exception as e:
            self.handle_error(e, "Check hash field exists")
            return False

    # ============================================
    # Set Operations
    # ============================================

    async def sadd(self, key: str, members: List[str]) -> Optional[int]:
        """Add members to set."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.SAddRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = await self.stub.SAdd(request)
            return response.added_count

        except Exception as e:
            return self.handle_error(e, "Add to set")

    async def sremove(self, key: str, members: List[str]) -> Optional[int]:
        """Remove members from set."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.SRemoveRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = await self.stub.SRemove(request)
            return response.removed_count

        except Exception as e:
            return self.handle_error(e, "Remove from set")

    async def smembers(self, key: str) -> List[str]:
        """Get all set members."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.SMembersRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.SMembers(request)
            return list(response.members)

        except Exception as e:
            return self.handle_error(e, "Get set members") or []

    async def sismember(self, key: str, member: str) -> bool:
        """Check if member is in set."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.SIsMemberRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member
            )

            response = await self.stub.SIsMember(request)
            return response.is_member

        except Exception as e:
            self.handle_error(e, "Check set membership")
            return False

    async def scard(self, key: str) -> Optional[int]:
        """Get set cardinality (size)."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.SCardRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.SCard(request)
            return response.count

        except Exception as e:
            return self.handle_error(e, "Get set cardinality")

    # ============================================
    # Sorted Set Operations
    # ============================================

    async def zadd(self, key: str, score_members: Dict[str, float]) -> Optional[int]:
        """Add members to sorted set with scores."""
        try:
            await self._ensure_connected()

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

            response = await self.stub.ZAdd(request)
            return response.added_count

        except Exception as e:
            self.handle_error(e, "Add to sorted set")
            return None

    async def zrange(self, key: str, start: int = 0, stop: int = -1, with_scores: bool = False) -> List:
        """Get sorted set range."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ZRangeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                start=start,
                stop=stop,
                with_scores=with_scores
            )

            response = await self.stub.ZRange(request)

            if with_scores:
                return [(m.member, m.score) for m in response.members]
            return [m.member for m in response.members]

        except Exception as e:
            return self.handle_error(e, "Get sorted set range") or []

    async def zrem(self, key: str, members: List[str]) -> Optional[int]:
        """Remove members from sorted set."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ZRemoveRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                members=members
            )

            response = await self.stub.ZRemove(request)
            return response.removed_count

        except Exception as e:
            self.handle_error(e, "Remove from sorted set")
            return None

    async def zrank(self, key: str, member: str) -> Optional[int]:
        """Get member rank in sorted set."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ZRankRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member
            )

            response = await self.stub.ZRank(request)

            if response.found:
                return response.rank
            return None

        except Exception as e:
            return self.handle_error(e, "Get sorted set rank")

    async def zscore(self, key: str, member: str) -> Optional[float]:
        """Get member score in sorted set."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ZScoreRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key,
                member=member
            )

            response = await self.stub.ZScore(request)

            if response.found:
                return response.score
            return None

        except Exception as e:
            return self.handle_error(e, "Get sorted set score")

    async def zcard(self, key: str) -> Optional[int]:
        """Get sorted set cardinality (size)."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ZCardRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                key=key
            )

            response = await self.stub.ZCard(request)
            return response.count

        except Exception as e:
            return self.handle_error(e, "Get sorted set cardinality")

    # ============================================
    # Distributed Lock Operations
    # ============================================

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 10, wait_timeout_seconds: int = 5) -> Optional[str]:
        """Acquire distributed lock."""
        try:
            await self._ensure_connected()

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

            response = await self.stub.AcquireLock(request)

            if response.acquired:
                return response.lock_id
            return None

        except Exception as e:
            self.handle_error(e, "Acquire lock")
            return None

    async def release_lock(self, lock_key: str, lock_id: str) -> bool:
        """Release distributed lock."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.ReleaseLockRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                lock_key=lock_key,
                lock_id=lock_id
            )

            response = await self.stub.ReleaseLock(request)
            return response.released

        except Exception as e:
            self.handle_error(e, "Release lock")
            return False

    async def renew_lock(self, lock_key: str, lock_id: str, ttl_seconds: int = 10) -> bool:
        """Renew distributed lock."""
        try:
            await self._ensure_connected()

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

            response = await self.stub.RenewLock(request)
            return response.renewed

        except Exception as e:
            self.handle_error(e, "Renew lock")
            return False

    # ============================================
    # Pub/Sub Operations
    # ============================================

    async def publish(self, channel: str, message: str) -> Optional[int]:
        """Publish message to channel."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.PublishRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                channel=channel,
                message=message
            )

            response = await self.stub.Publish(request)
            return response.subscriber_count

        except Exception as e:
            return self.handle_error(e, "Publish message")

    async def subscribe(self, channels: List[str]) -> AsyncIterator[Dict]:
        """
        Subscribe to channels (streaming).

        Yields:
            Dict with 'channel', 'message', 'timestamp' for each message
        """
        try:
            await self._ensure_connected()
            request = redis_service_pb2.SubscribeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                channels=channels
            )

            async for message in self.stub.Subscribe(request):
                yield {
                    'channel': message.channel,
                    'message': message.message,
                    'timestamp': message.timestamp
                }

        except Exception as e:
            self.handle_error(e, "Subscribe to channels")

    # ============================================
    # Session Management
    # ============================================

    async def create_session(self, data: Dict[str, str], ttl_seconds: int = 3600) -> Optional[str]:
        """Create session."""
        try:
            await self._ensure_connected()

            from google.protobuf.duration_pb2 import Duration
            ttl = Duration()
            ttl.seconds = ttl_seconds

            request = redis_service_pb2.CreateSessionRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                data=data,
                ttl=ttl
            )

            response = await self.stub.CreateSession(request)
            return response.session_id

        except Exception as e:
            return self.handle_error(e, "Create session")

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.GetSessionRequest(
                user_id=self.user_id,
                session_id=session_id
            )

            response = await self.stub.GetSession(request)

            if response.found:
                return self._proto_map_to_dict(response.session.data)
            return None

        except Exception as e:
            return self.handle_error(e, "Get session")

    async def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.DeleteSessionRequest(
                user_id=self.user_id,
                session_id=session_id
            )

            response = await self.stub.DeleteSession(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "Delete session")
            return False

    # ============================================
    # Statistics
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get Redis statistics."""
        try:
            await self._ensure_connected()
            request = redis_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = await self.stub.GetStatistics(request)

            return {
                'total_keys': response.total_keys,
                'memory_used_bytes': response.memory_used_bytes,
                'commands_processed': response.commands_processed,
                'connections_received': response.connections_received,
                'hit_rate': response.hit_rate,
                'key_type_distribution': self._proto_map_to_dict(response.key_type_distribution)
            }

        except Exception as e:
            return self.handle_error(e, "Get statistics")

    # ============================================
    # Concurrent Operations Helper
    # ============================================

    async def get_many_concurrent(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """
        Get multiple keys concurrently using asyncio.gather.

        This is useful when you want individual get calls to run concurrently
        without using the batch mget operation.

        Args:
            keys: List of keys to get

        Returns:
            Dict mapping keys to their values (None if not found)
        """
        import asyncio

        async def get_single(key: str) -> tuple:
            value = await self.get(key)
            return (key, value)

        results = await asyncio.gather(*[get_single(k) for k in keys])
        return dict(results)

    async def set_many_concurrent(self, key_values: Dict[str, str], ttl_seconds: int = 0) -> Dict[str, bool]:
        """
        Set multiple key-values concurrently using asyncio.gather.

        Args:
            key_values: Dict of key-value pairs
            ttl_seconds: TTL for all keys

        Returns:
            Dict mapping keys to success status
        """
        import asyncio

        async def set_single(key: str, value: str) -> tuple:
            success = await self.set(key, value, ttl_seconds)
            return (key, success)

        results = await asyncio.gather(*[set_single(k, v) for k, v in key_values.items()])
        return dict(results)


# Example usage
if __name__ == '__main__':
    import asyncio

    async def main():
        async with AsyncRedisClient(host='localhost', port=50055, user_id='test_user') as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Basic operations
            await client.set('async:key1', 'value1')
            value = await client.get('async:key1')
            print(f"Got: {value}")

            # Batch operations
            await client.mset({
                'async:key2': 'value2',
                'async:key3': 'value3',
                'async:key4': 'value4'
            })

            values = await client.mget(['async:key2', 'async:key3', 'async:key4'])
            print(f"Batch get: {values}")

            # Concurrent operations
            concurrent_results = await client.get_many_concurrent([
                'async:key1', 'async:key2', 'async:key3'
            ])
            print(f"Concurrent get: {concurrent_results}")

    asyncio.run(main())
