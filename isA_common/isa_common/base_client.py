#!/usr/bin/env python3
"""
Base gRPC Client
所有 gRPC 客户端的基类，提供统一的连接管理和错误处理
"""

import grpc
import logging
import threading
from typing import Optional, TYPE_CHECKING
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        """确保已连接（线程安全的延迟连接）"""
        if self._connected and self.channel is not None:
            return

        with self._connect_lock:
            # Double-check after acquiring lock
            if self._connected and self.channel is not None:
                return

            logger.debug(f"[{self.service_name()}] Connecting to {self.address}...")

            # Build channel options
            options = [
                ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
                ('grpc.max_send_message_length', 100 * 1024 * 1024),     # 100MB
                ('grpc.keepalive_time_ms', 30000),                        # 30s between pings
                ('grpc.keepalive_timeout_ms', 10000),                     # 10s timeout for ping response
                ('grpc.http2.min_time_between_pings_ms', 30000),          # Min 30s between pings
                ('grpc.http2.max_pings_without_data', 0),                 # Allow pings without data
                ('grpc.keepalive_permit_without_calls', 1),               # Allow keepalive when no calls
            ]

            # Add compression if enabled
            if self.enable_compression:
                options.append(('grpc.default_compression_algorithm', grpc.Compression.Gzip))
                options.append(('grpc.default_compression_level', grpc.Compression.Gzip))

            # Create channel
            self.channel = grpc.insecure_channel(self.address, options=options)

            # Create stub
            self.stub = self._create_stub()

            # Mark as connected
            self._connected = True
            logger.debug(f"[{self.service_name()}] Connected successfully to {self.address}")

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
        """关闭连接"""
        if self.channel is not None:
            self.channel.close()
            self._connected = False
            logger.debug(f"[{self.service_name()}] Connection closed")
    
    def __enter__(self):
        """支持 with 语句"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动关闭连接"""
        self.close()

