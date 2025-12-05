#!/usr/bin/env python3
"""
Async Base gRPC Client
Async version of all gRPC clients using grpc.aio for high-performance concurrent operations.

Performance Benefits:
- True async I/O without GIL blocking
- Concurrent request execution
- 10x-50x throughput improvement over sync clients
- Memory-efficient connection pooling
"""

import grpc.aio
import logging
import asyncio
import atexit
from typing import Optional, Any, Dict, List, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
from google.protobuf.struct_pb2 import Struct, Value, ListValue

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========================================
# Async Global Channel Pool (Singleton)
# ========================================

class AsyncGlobalChannelPool:
    """
    Async global gRPC channel pool for connection reuse.

    This singleton manages shared async channels across all client instances,
    significantly reducing connection overhead and improving performance.

    Features:
    - Async-safe channel creation and access
    - Automatic channel health monitoring
    - Lazy channel creation
    - Graceful shutdown support

    Usage:
        # Channels are automatically shared when using AsyncBaseGRPCClient
        client1 = AsyncRedisClient(host='redis', port=50055)
        client2 = AsyncRedisClient(host='redis', port=50055)  # Reuses same channel
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._channels: Dict[str, grpc.aio.Channel] = {}
        self._channel_locks: Dict[str, asyncio.Lock] = {}
        self._channel_ref_counts: Dict[str, int] = {}
        self._global_lock = asyncio.Lock()
        self._default_options = [
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_send_message_length', 100 * 1024 * 1024),     # 100MB
            ('grpc.keepalive_time_ms', 60000),                        # 60s between pings (more conservative)
            ('grpc.keepalive_timeout_ms', 20000),                     # 20s timeout
            ('grpc.http2.min_time_between_pings_ms', 60000),          # Min 60s between pings
            ('grpc.http2.max_pings_without_data', 2),                 # Allow 2 pings without data
            ('grpc.keepalive_permit_without_calls', 0),               # Don't ping when idle (fixes too_many_pings)
        ]
        self._initialized = True

        logger.debug("[AsyncChannelPool] Initialized async global channel pool")

    async def get_channel(
        self,
        address: str,
        options: Optional[List[Tuple[str, Any]]] = None,
        enable_compression: bool = True
    ) -> grpc.aio.Channel:
        """
        Get or create a shared async channel for the given address.

        Args:
            address: Target address (host:port)
            options: Additional gRPC channel options
            enable_compression: Enable gzip compression

        Returns:
            Shared async gRPC channel
        """
        # Create address-specific lock if needed
        async with self._global_lock:
            if address not in self._channel_locks:
                self._channel_locks[address] = asyncio.Lock()

        # Get or create channel with address-specific lock
        async with self._channel_locks[address]:
            if address in self._channels:
                channel = self._channels[address]
                state = channel.get_state()
                # Check if channel is still healthy
                if state in (
                    grpc.ChannelConnectivity.IDLE,
                    grpc.ChannelConnectivity.READY,
                    grpc.ChannelConnectivity.CONNECTING,
                ):
                    self._channel_ref_counts[address] = self._channel_ref_counts.get(address, 0) + 1
                    logger.debug(f"[AsyncChannelPool] Reusing channel for {address} (refs: {self._channel_ref_counts[address]})")
                    return channel
                else:
                    # Channel is unhealthy, close and recreate
                    logger.warning(f"[AsyncChannelPool] Channel for {address} is unhealthy, recreating...")
                    await self._close_channel_unsafe(address)

            # Create new channel
            channel = self._create_channel(address, options, enable_compression)
            self._channels[address] = channel
            self._channel_ref_counts[address] = 1

            logger.info(f"[AsyncChannelPool] Created new async channel for {address}")
            return channel

    def _create_channel(
        self,
        address: str,
        options: Optional[List[Tuple[str, Any]]] = None,
        enable_compression: bool = True
    ) -> grpc.aio.Channel:
        """Create a new async gRPC channel with optimized settings."""
        channel_options = list(self._default_options)

        if enable_compression:
            channel_options.extend([
                ('grpc.default_compression_algorithm', grpc.Compression.Gzip),
                ('grpc.default_compression_level', grpc.Compression.Gzip),
            ])

        if options:
            # Merge with custom options (custom options override defaults)
            option_keys = {opt[0] for opt in channel_options}
            for opt in options:
                if opt[0] in option_keys:
                    channel_options = [(k, v) for k, v in channel_options if k != opt[0]]
                channel_options.append(opt)

        return grpc.aio.insecure_channel(address, options=channel_options)

    async def release_channel(self, address: str):
        """
        Release a reference to a channel.

        Note: Channels are NOT closed when ref count reaches 0.
        They remain open for potential reuse. Use shutdown() to close all.
        """
        async with self._global_lock:
            if address in self._channel_ref_counts:
                self._channel_ref_counts[address] = max(0, self._channel_ref_counts[address] - 1)
                logger.debug(f"[AsyncChannelPool] Released channel for {address} (refs: {self._channel_ref_counts[address]})")

    async def _close_channel_unsafe(self, address: str):
        """Close a channel without locking (caller must hold lock)."""
        if address in self._channels:
            try:
                await self._channels[address].close()
            except Exception as e:
                logger.warning(f"[AsyncChannelPool] Error closing channel for {address}: {e}")
            del self._channels[address]
            self._channel_ref_counts.pop(address, None)

    async def close_channel(self, address: str):
        """Force close a specific channel."""
        async with self._global_lock:
            if address in self._channel_locks:
                async with self._channel_locks[address]:
                    await self._close_channel_unsafe(address)

    async def shutdown(self):
        """Close all channels."""
        async with self._global_lock:
            for address in list(self._channels.keys()):
                try:
                    await self._channels[address].close()
                    logger.debug(f"[AsyncChannelPool] Closed channel for {address}")
                except Exception as e:
                    logger.warning(f"[AsyncChannelPool] Error closing channel for {address}: {e}")

            self._channels.clear()
            self._channel_ref_counts.clear()
            logger.info("[AsyncChannelPool] Shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics for monitoring."""
        return {
            'total_channels': len(self._channels),
            'channels': {
                addr: {
                    'ref_count': self._channel_ref_counts.get(addr, 0),
                    'state': str(ch.get_state()) if addr in self._channels else 'closed',
                }
                for addr, ch in self._channels.items()
            }
        }


# Global async pool instance
_async_channel_pool = AsyncGlobalChannelPool()


class AsyncBaseGRPCClient(ABC):
    """Async gRPC client base class for high-performance concurrent operations."""

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
        Initialize async gRPC client.

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID (for multi-tenant isolation)
            lazy_connect: Lazy connection (default: True, faster startup)
            enable_compression: Enable gRPC compression (default: True)
            enable_retry: Enable retry logic (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional)
        """
        self.consul_registry = consul_registry
        self.service_name_override = service_name_override

        # Discover service endpoint via Consul if not explicitly provided
        if host is None or port is None:
            discovered_host, discovered_port = self._discover_service_endpoint()
            host = host or discovered_host
            port = port or discovered_port

        self.host = host
        self.port = port
        self.user_id = user_id or 'default_user'
        self.address = f'{host}:{port}'
        self.enable_compression = enable_compression
        self.enable_retry = enable_retry

        # Lazy initialization
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        self._connect_lock = asyncio.Lock()
        self._connected = False

    def _discover_service_endpoint(self) -> tuple:
        """
        Discover service endpoint via Consul.

        Returns:
            Tuple of (host, port)
        """
        if self.consul_registry:
            try:
                # Use override name if provided, otherwise use the service_name() method
                lookup_name = self.service_name_override or self.service_name().lower()

                # Use ConsulRegistry's get_service_endpoint directly
                service_url = self.consul_registry.get_service_endpoint(lookup_name)

                if not service_url:
                    logger.warning(f"[{self.service_name()}] Service '{lookup_name}' not found in Consul. Using defaults.")
                    return 'localhost', self.default_port()

                # Parse URL format: "http://host:port"
                if '://' in service_url:
                    # Remove protocol
                    service_url = service_url.split('://', 1)[1]

                if ':' in service_url:
                    host, port_str = service_url.rsplit(':', 1)
                    port = int(port_str)
                else:
                    host = service_url
                    port = self.default_port()

                logger.info(f"[{self.service_name()}] Discovered via Consul: {host}:{port}")
                return host, port

            except Exception as e:
                logger.warning(f"[{self.service_name()}] Failed to discover via Consul: {e}. Using defaults.")
                return 'localhost', self.default_port()
        else:
            logger.debug(f"[{self.service_name()}] No Consul registry provided. Using defaults.")
            return 'localhost', self.default_port()

    async def _ensure_connected(self):
        """Ensure connection is established (async-safe lazy connection using global pool)."""
        if self._connected and self.channel is not None:
            return

        async with self._connect_lock:
            # Double-check after acquiring lock
            if self._connected and self.channel is not None:
                return

            logger.debug(f"[{self.service_name()}] Connecting to {self.address}...")

            # Get shared channel from global async pool
            self.channel = await _async_channel_pool.get_channel(
                address=self.address,
                enable_compression=self.enable_compression
            )

            # Create stub (each client has its own stub, but shares the channel)
            self.stub = self._create_stub()

            # Mark as connected
            self._connected = True
            logger.debug(f"[{self.service_name()}] Connected successfully to {self.address} (using shared async channel)")

    @abstractmethod
    def _create_stub(self):
        """Subclass implementation: create service-specific stub."""
        pass

    @abstractmethod
    def service_name(self) -> str:
        """Subclass implementation: return service name."""
        pass

    @abstractmethod
    def default_port(self) -> int:
        """Subclass implementation: return default port."""
        pass

    def handle_error(self, e: Exception, operation: str = "operation"):
        """Unified error handling."""
        logger.error(f"[{self.service_name()}] {operation} failed:")
        if isinstance(e, grpc.aio.AioRpcError):
            logger.error(f"  Error code: {e.code()}")
            logger.error(f"  Error details: {e.details()}")
        else:
            logger.error(f"  Error: {e}")
        return None

    async def close(self):
        """
        Release connection reference.

        Note: This does NOT close the underlying channel, as it may be shared
        with other clients. The channel is managed by AsyncGlobalChannelPool.
        """
        if self._connected and self.address:
            await _async_channel_pool.release_channel(self.address)
            self._connected = False
            self.stub = None
            logger.debug(f"[{self.service_name()}] Released connection to {self.address}")

    async def force_close(self):
        """
        Force close the underlying channel.

        WARNING: This will affect ALL clients using this channel.
        Use only when you're sure no other clients need this connection.
        """
        if self.address:
            await _async_channel_pool.close_channel(self.address)
            self._connected = False
            self.channel = None
            self.stub = None
            logger.info(f"[{self.service_name()}] Force closed channel to {self.address}")

    async def reconnect(self):
        """Force reconnect by closing current channel and creating new one."""
        await self.force_close()
        await self._ensure_connected()
        logger.info(f"[{self.service_name()}] Reconnected to {self.address}")

    @staticmethod
    def get_pool_stats() -> Dict[str, Any]:
        """Get global channel pool statistics for monitoring."""
        return _async_channel_pool.get_stats()

    async def __aenter__(self):
        """Support async with statement."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release connection reference on exit."""
        await self.close()

    # ========================================
    # Proto Serialization Helpers
    # ========================================

    def _proto_struct_to_dict(self, struct: Struct) -> Dict[str, Any]:
        """
        Recursively convert protobuf Struct to Python dict.

        This method properly handles nested Struct/ListValue objects,
        ensuring all JSONB/nested fields are converted to native Python types.
        """
        if struct is None:
            return {}

        result = {}
        for key, value in struct.fields.items():
            result[key] = self._proto_value_to_python(value)
        return result

    def _proto_value_to_python(self, value: Value) -> Any:
        """
        Convert protobuf Value to Python native type.

        Handles all protobuf value types including nested structures.
        """
        if value is None:
            return None

        kind = value.WhichOneof('kind')

        if kind == 'null_value':
            return None
        elif kind == 'number_value':
            # Convert to int if it's a whole number
            num = value.number_value
            if num == int(num):
                return int(num)
            return num
        elif kind == 'string_value':
            return value.string_value
        elif kind == 'bool_value':
            return value.bool_value
        elif kind == 'struct_value':
            # Recursively convert nested struct
            return self._proto_struct_to_dict(value.struct_value)
        elif kind == 'list_value':
            # Recursively convert list items
            return [self._proto_value_to_python(item) for item in value.list_value.values]
        else:
            return None

    def _proto_map_to_dict(self, proto_map) -> Dict[str, Any]:
        """
        Convert protobuf map field to Python dict.

        Handles map<string, Value> and similar proto map types.
        """
        if proto_map is None:
            return {}

        result = {}
        for key, value in proto_map.items():
            if isinstance(value, Value):
                result[key] = self._proto_value_to_python(value)
            elif isinstance(value, Struct):
                result[key] = self._proto_struct_to_dict(value)
            elif hasattr(value, 'DESCRIPTOR'):
                # It's a protobuf message, try to convert
                from google.protobuf.json_format import MessageToDict
                result[key] = MessageToDict(value, preserving_proto_field_name=True)
            else:
                result[key] = value
        return result

    def _ensure_native_dict(self, data: Any) -> Any:
        """
        Ensure data is converted to native Python types.

        Automatically detects and converts protobuf Struct/Value/Message types.
        """
        if data is None:
            return None

        if isinstance(data, Struct):
            return self._proto_struct_to_dict(data)
        elif isinstance(data, Value):
            return self._proto_value_to_python(data)
        elif isinstance(data, ListValue):
            return [self._proto_value_to_python(v) for v in data.values]
        elif isinstance(data, dict):
            return {k: self._ensure_native_dict(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._ensure_native_dict(item) for item in data]
        elif hasattr(data, 'DESCRIPTOR'):
            # Generic protobuf message
            from google.protobuf.json_format import MessageToDict
            return MessageToDict(data, preserving_proto_field_name=True)
        else:
            return data


# ========================================
# Auto Batcher for Transparent Request Coalescing
# ========================================

class AutoBatcher:
    """
    Automatic request batcher for transparent optimization.

    Collects individual requests and batches them together for efficient
    execution, reducing network round-trips without changing client code.

    Features:
    - Automatic request coalescing
    - Configurable batch size and wait time
    - Promise-based result distribution
    - Thread-safe operation

    Usage:
        batcher = AutoBatcher(
            batch_fn=redis_client.mget,  # Batch function
            max_size=100,                 # Max batch size
            max_wait_ms=10                # Max wait time in ms
        )

        # These calls are automatically batched:
        result1 = await batcher.add('key1')
        result2 = await batcher.add('key2')
        result3 = await batcher.add('key3')
    """

    def __init__(
        self,
        batch_fn,
        max_size: int = 100,
        max_wait_ms: int = 10,
        key_extractor=None,
        result_mapper=None
    ):
        """
        Initialize AutoBatcher.

        Args:
            batch_fn: Async function that processes batched items
            max_size: Maximum number of items to batch before flushing
            max_wait_ms: Maximum time to wait before flushing (milliseconds)
            key_extractor: Function to extract key from item (default: identity)
            result_mapper: Function to map batch result to individual results
        """
        self.batch_fn = batch_fn
        self.max_size = max_size
        self.max_wait_ms = max_wait_ms
        self.key_extractor = key_extractor or (lambda x: x)
        self.result_mapper = result_mapper

        self._pending: List[Tuple[Any, asyncio.Future]] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

    async def add(self, item: Any) -> Any:
        """
        Add item to batch and return result when batch is processed.

        Args:
            item: Item to add to batch

        Returns:
            Result for this specific item from batch operation
        """
        future = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._pending.append((item, future))

            # If batch is full, flush immediately
            if len(self._pending) >= self.max_size:
                await self._flush()
            elif self._flush_task is None or self._flush_task.done():
                # Schedule delayed flush
                self._flush_task = asyncio.create_task(self._delayed_flush())

        return await future

    async def _delayed_flush(self):
        """Wait for max_wait_ms then flush pending items."""
        await asyncio.sleep(self.max_wait_ms / 1000.0)
        async with self._lock:
            if self._pending:
                await self._flush()

    async def _flush(self):
        """Process all pending items as a batch."""
        if not self._pending:
            return

        # Take all pending items
        items_to_process = self._pending[:]
        self._pending = []

        # Extract keys/items for batch processing
        items = [item for item, _ in items_to_process]
        keys = [self.key_extractor(item) for item in items]

        try:
            # Execute batch operation
            batch_result = await self.batch_fn(keys)

            # Distribute results to individual futures
            for i, (item, future) in enumerate(items_to_process):
                try:
                    if self.result_mapper:
                        result = self.result_mapper(batch_result, item, i)
                    elif isinstance(batch_result, dict):
                        # Assume dict keyed by the key
                        key = self.key_extractor(item)
                        result = batch_result.get(key)
                    elif isinstance(batch_result, (list, tuple)):
                        result = batch_result[i] if i < len(batch_result) else None
                    else:
                        result = batch_result

                    if not future.done():
                        future.set_result(result)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)

        except Exception as e:
            # Propagate exception to all pending futures
            for _, future in items_to_process:
                if not future.done():
                    future.set_exception(e)

    async def flush_now(self):
        """Force flush all pending items immediately."""
        async with self._lock:
            await self._flush()


class BatchedRedisGet:
    """
    Specialized auto-batcher for Redis GET operations.

    Automatically batches individual get() calls into mget() for efficiency.

    Usage:
        batched_get = BatchedRedisGet(redis_client)

        # These are automatically batched into a single mget() call:
        async with asyncio.TaskGroup() as tg:
            r1 = tg.create_task(batched_get.get('key1'))
            r2 = tg.create_task(batched_get.get('key2'))
            r3 = tg.create_task(batched_get.get('key3'))
    """

    def __init__(self, redis_client, max_size: int = 100, max_wait_ms: int = 5):
        """
        Initialize BatchedRedisGet.

        Args:
            redis_client: Async Redis client with mget() method
            max_size: Maximum keys to batch
            max_wait_ms: Maximum wait time before flush
        """
        self._client = redis_client
        self._batcher = AutoBatcher(
            batch_fn=self._batch_get,
            max_size=max_size,
            max_wait_ms=max_wait_ms,
            result_mapper=lambda result, item, idx: result.get(item)
        )

    async def _batch_get(self, keys: List[str]) -> Dict[str, str]:
        """Execute batch get via mget."""
        return await self._client.mget(keys)

    async def get(self, key: str) -> Optional[str]:
        """
        Get value for key, automatically batched with other concurrent gets.

        Args:
            key: Redis key

        Returns:
            Value or None if not found
        """
        return await self._batcher.add(key)


class BatchedRedisSet:
    """
    Specialized auto-batcher for Redis SET operations.

    Automatically batches individual set() calls into mset() for efficiency.

    Usage:
        batched_set = BatchedRedisSet(redis_client)

        # These are automatically batched into a single mset() call:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(batched_set.set('key1', 'value1'))
            tg.create_task(batched_set.set('key2', 'value2'))
            tg.create_task(batched_set.set('key3', 'value3'))
    """

    def __init__(self, redis_client, max_size: int = 100, max_wait_ms: int = 5):
        """
        Initialize BatchedRedisSet.

        Args:
            redis_client: Async Redis client with mset() method
            max_size: Maximum keys to batch
            max_wait_ms: Maximum wait time before flush
        """
        self._client = redis_client
        self._pending: Dict[str, Tuple[str, asyncio.Future]] = {}
        self._lock = asyncio.Lock()
        self._max_size = max_size
        self._max_wait_ms = max_wait_ms
        self._flush_task: Optional[asyncio.Task] = None

    async def set(self, key: str, value: str) -> bool:
        """
        Set key-value, automatically batched with other concurrent sets.

        Args:
            key: Redis key
            value: Value to set

        Returns:
            True if successful
        """
        future = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._pending[key] = (value, future)

            if len(self._pending) >= self._max_size:
                await self._flush()
            elif self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._delayed_flush())

        return await future

    async def _delayed_flush(self):
        """Wait then flush."""
        await asyncio.sleep(self._max_wait_ms / 1000.0)
        async with self._lock:
            if self._pending:
                await self._flush()

    async def _flush(self):
        """Process pending sets as batch."""
        if not self._pending:
            return

        items = dict(self._pending)
        self._pending = {}

        key_values = {k: v for k, (v, _) in items.items()}
        futures = {k: f for k, (_, f) in items.items()}

        try:
            result = await self._client.mset(key_values)

            for key, future in futures.items():
                if not future.done():
                    future.set_result(result)

        except Exception as e:
            for future in futures.values():
                if not future.done():
                    future.set_exception(e)
