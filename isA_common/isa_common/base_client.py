#!/usr/bin/env python3
"""
Base gRPC Client
所有 gRPC 客户端的基类，提供统一的连接管理和错误处理
"""

import grpc
import logging
import threading
import time
import atexit
from typing import Optional, Any, Dict, List, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.protobuf.struct_pb2 import Struct, Value, ListValue
from google.protobuf.message import Message

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========================================
# Global Channel Pool (Singleton)
# ========================================

class GlobalChannelPool:
    """
    Global gRPC channel pool for connection reuse.

    This singleton manages shared channels across all client instances,
    significantly reducing connection overhead and improving performance.

    Features:
    - Thread-safe channel creation and access
    - Automatic channel health monitoring
    - Lazy channel creation
    - Graceful shutdown on process exit

    Usage:
        # Channels are automatically shared when using BaseGRPCClient
        client1 = RedisClient(host='redis', port=50055)  # Creates channel
        client2 = RedisClient(host='redis', port=50055)  # Reuses same channel
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._channels: Dict[str, grpc.Channel] = {}
        self._channel_locks: Dict[str, threading.Lock] = {}
        self._channel_ref_counts: Dict[str, int] = {}
        self._channel_created_at: Dict[str, float] = {}
        self._global_lock = threading.Lock()
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

        # Register cleanup on exit
        atexit.register(self.shutdown)

        logger.debug("[ChannelPool] Initialized global channel pool")

    def get_channel(
        self,
        address: str,
        options: Optional[List[Tuple[str, Any]]] = None,
        enable_compression: bool = True
    ) -> grpc.Channel:
        """
        Get or create a shared channel for the given address.

        Args:
            address: Target address (host:port)
            options: Additional gRPC channel options
            enable_compression: Enable gzip compression

        Returns:
            Shared gRPC channel
        """
        # Create address-specific lock if needed
        with self._global_lock:
            if address not in self._channel_locks:
                self._channel_locks[address] = threading.Lock()

        # Get or create channel with address-specific lock
        with self._channel_locks[address]:
            if address in self._channels:
                channel = self._channels[address]
                # Check if channel is still healthy
                if self._is_channel_healthy(channel):
                    self._channel_ref_counts[address] = self._channel_ref_counts.get(address, 0) + 1
                    logger.debug(f"[ChannelPool] Reusing channel for {address} (refs: {self._channel_ref_counts[address]})")
                    return channel
                else:
                    # Channel is unhealthy, close and recreate
                    logger.warning(f"[ChannelPool] Channel for {address} is unhealthy, recreating...")
                    self._close_channel_unsafe(address)

            # Create new channel
            channel = self._create_channel(address, options, enable_compression)
            self._channels[address] = channel
            self._channel_ref_counts[address] = 1
            self._channel_created_at[address] = time.time()

            logger.info(f"[ChannelPool] Created new channel for {address}")
            return channel

    def _create_channel(
        self,
        address: str,
        options: Optional[List[Tuple[str, Any]]] = None,
        enable_compression: bool = True
    ) -> grpc.Channel:
        """Create a new gRPC channel with optimized settings."""
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

        return grpc.insecure_channel(address, options=channel_options)

    def _is_channel_healthy(self, channel: grpc.Channel) -> bool:
        """Check if channel is in a healthy state."""
        try:
            state = channel._channel.check_connectivity_state(False)
            # IDLE, READY, CONNECTING are considered healthy
            # TRANSIENT_FAILURE, SHUTDOWN are unhealthy
            return state in (
                grpc.ChannelConnectivity.IDLE,
                grpc.ChannelConnectivity.READY,
                grpc.ChannelConnectivity.CONNECTING,
            )
        except Exception:
            return False

    def release_channel(self, address: str):
        """
        Release a reference to a channel.

        Note: Channels are NOT closed when ref count reaches 0.
        They remain open for potential reuse. Use shutdown() to close all.
        """
        with self._global_lock:
            if address in self._channel_ref_counts:
                self._channel_ref_counts[address] = max(0, self._channel_ref_counts[address] - 1)
                logger.debug(f"[ChannelPool] Released channel for {address} (refs: {self._channel_ref_counts[address]})")

    def _close_channel_unsafe(self, address: str):
        """Close a channel without locking (caller must hold lock)."""
        if address in self._channels:
            try:
                self._channels[address].close()
            except Exception as e:
                logger.warning(f"[ChannelPool] Error closing channel for {address}: {e}")
            del self._channels[address]
            self._channel_ref_counts.pop(address, None)
            self._channel_created_at.pop(address, None)

    def close_channel(self, address: str):
        """Force close a specific channel."""
        with self._global_lock:
            if address in self._channel_locks:
                with self._channel_locks[address]:
                    self._close_channel_unsafe(address)

    def shutdown(self):
        """Close all channels. Called automatically on process exit."""
        with self._global_lock:
            for address in list(self._channels.keys()):
                try:
                    self._channels[address].close()
                    logger.debug(f"[ChannelPool] Closed channel for {address}")
                except Exception as e:
                    logger.warning(f"[ChannelPool] Error closing channel for {address}: {e}")

            self._channels.clear()
            self._channel_ref_counts.clear()
            self._channel_created_at.clear()
            logger.info("[ChannelPool] Shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics for monitoring."""
        with self._global_lock:
            return {
                'total_channels': len(self._channels),
                'channels': {
                    addr: {
                        'ref_count': self._channel_ref_counts.get(addr, 0),
                        'age_seconds': time.time() - self._channel_created_at.get(addr, time.time()),
                        'healthy': self._is_channel_healthy(ch) if addr in self._channels else False,
                    }
                    for addr, ch in self._channels.items()
                }
            }


# Global pool instance
_channel_pool = GlobalChannelPool()


class BaseGRPCClient(ABC):
    """gRPC 客户端基类"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        初始化 gRPC 客户端

        Args:
            host: 服务地址 (optional, will use Consul discovery if not provided)
            port: 服务端口 (optional, will use Consul discovery if not provided)
            user_id: 用户 ID (用于多租户隔离)
            lazy_connect: 是否延迟连接 (默认: True, 更快的启动速度)
            enable_compression: 是否启用 gRPC 压缩 (默认: True)
            enable_retry: 是否启用重试逻辑 (默认: True)
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
        self.channel = None
        self.stub = None
        self._connect_lock = threading.Lock()
        self._connected = False

        # Connect immediately if not lazy
        if not lazy_connect:
            self._ensure_connected()

    def _discover_service_endpoint(self) -> tuple:
        """
        Discover service endpoint via Consul

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
                    port = self.default_port()  # Service-specific default port

                logger.info(f"[{self.service_name()}] Discovered via Consul: {host}:{port}")
                return host, port

            except Exception as e:
                logger.warning(f"[{self.service_name()}] Failed to discover via Consul: {e}. Using defaults.")
                return 'localhost', self.default_port()
        else:
            logger.debug(f"[{self.service_name()}] No Consul registry provided. Using defaults.")
            return 'localhost', self.default_port()
    
    def _ensure_connected(self):
        """确保已连接（线程安全的延迟连接，使用全局连接池）"""
        if self._connected and self.channel is not None:
            return

        with self._connect_lock:
            # Double-check after acquiring lock
            if self._connected and self.channel is not None:
                return

            logger.debug(f"[{self.service_name()}] Connecting to {self.address}...")

            # Get shared channel from global pool
            self.channel = _channel_pool.get_channel(
                address=self.address,
                enable_compression=self.enable_compression
            )

            # Create stub (each client has its own stub, but shares the channel)
            self.stub = self._create_stub()

            # Mark as connected
            self._connected = True
            logger.debug(f"[{self.service_name()}] Connected successfully to {self.address} (using shared channel)")

    @abstractmethod
    def _create_stub(self):
        """子类实现：创建特定服务的 stub"""
        pass

    @abstractmethod
    def service_name(self) -> str:
        """子类实现：返回服务名称"""
        pass

    @abstractmethod
    def default_port(self) -> int:
        """子类实现：返回默认端口"""
        pass

    def _call_with_retry(self, func, *args, **kwargs):
        """带重试的 RPC 调用"""
        if not self.enable_retry:
            return func(*args, **kwargs)

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(grpc.RpcError),
            reraise=True
        )
        def _retry_wrapper():
            self._ensure_connected()
            return func(*args, **kwargs)

        try:
            return _retry_wrapper()
        except grpc.RpcError as e:
            logger.error(f"[{self.service_name()}] RPC failed after retries: {e.code()} - {e.details()}")
            raise

    def handle_error(self, e: Exception, operation: str = "操作"):
        """统一错误处理"""
        logger.error(f"[{self.service_name()}] {operation} 失败:")
        if isinstance(e, grpc.RpcError):
            logger.error(f"  错误代码: {e.code()}")
            logger.error(f"  错误详情: {e.details()}")
        else:
            logger.error(f"  错误: {e}")
        return None
    
    def close(self):
        """
        Release connection reference.

        Note: This does NOT close the underlying channel, as it may be shared
        with other clients. The channel is managed by GlobalChannelPool and
        will be closed on process exit or when explicitly requested.
        """
        if self._connected and self.address:
            _channel_pool.release_channel(self.address)
            self._connected = False
            self.stub = None
            # Don't set channel to None - other clients may still use it
            logger.debug(f"[{self.service_name()}] Released connection to {self.address}")

    def force_close(self):
        """
        Force close the underlying channel.

        WARNING: This will affect ALL clients using this channel.
        Use only when you're sure no other clients need this connection.
        """
        if self.address:
            _channel_pool.close_channel(self.address)
            self._connected = False
            self.channel = None
            self.stub = None
            logger.info(f"[{self.service_name()}] Force closed channel to {self.address}")

    def reconnect(self):
        """Force reconnect by closing current channel and creating new one."""
        self.force_close()
        self._ensure_connected()
        logger.info(f"[{self.service_name()}] Reconnected to {self.address}")

    @staticmethod
    def get_pool_stats() -> Dict[str, Any]:
        """Get global channel pool statistics for monitoring."""
        return _channel_pool.get_stats()

    def __enter__(self):
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时释放连接引用（不关闭共享channel）"""
        self.close()

    # ========================================
    # Proto Serialization Helpers
    # ========================================

    def _proto_struct_to_dict(self, struct: Struct) -> Dict[str, Any]:
        """
        Recursively convert protobuf Struct to Python dict.

        This method properly handles nested Struct/ListValue objects,
        ensuring all JSONB/nested fields are converted to native Python types.

        Args:
            struct: protobuf Struct object

        Returns:
            Python dictionary with all nested structures converted
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

        Args:
            value: protobuf Value object

        Returns:
            Python native type (str, int, float, bool, dict, list, or None)
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

        Args:
            proto_map: protobuf map field (e.g., response.details, response.metadata)

        Returns:
            Python dictionary
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

        Args:
            data: Any data that might be a protobuf type

        Returns:
            Native Python type
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

