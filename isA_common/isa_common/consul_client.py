"""
Consul Service Registry Module
w
Provides service registration and health check functionality for microservices
"""

import asyncio
import json
import logging
import os
import socket
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import ipaddress

import consul

from .async_base_client import AsyncBaseClient

logger = logging.getLogger(__name__)


def _is_loopback(host: str) -> bool:
    """Return True if *host* is a loopback address (127.x.x.x, ::1, localhost)."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _usable_service_host(addr: Optional[str]) -> bool:
    """Return True when *addr* can be advertised to gateways/other services."""
    return bool(addr) and addr != "0.0.0.0" and not _is_loopback(addr)


def _is_resolvable(host: str) -> bool:
    """Return True if the current runtime can resolve *host*."""
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False


def _first_non_loopback_ip(host: str) -> Optional[str]:
    """Resolve *host* to a non-loopback IP, preferring IPv4 for local dev."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None

    ipv6_candidate = None
    for family, _, _, _, sockaddr in infos:
        address = sockaddr[0]
        if not _usable_service_host(address):
            continue

        if family == socket.AF_INET:
            return address

        if family == socket.AF_INET6 and ipv6_candidate is None:
            ipv6_candidate = address

    return ipv6_candidate


def _desktop_gateway_host() -> Optional[str]:
    """
    Prefer Docker Desktop's stable host-gateway IP for native macOS dev services.

    This keeps local services reachable from Kind/APISIX without requiring every
    service repo to export SERVICE_HOST manually. APISIX 3.16 rejects Consul
    discovery nodes that are still domain-shaped hosts, so we normalize the
    Docker Desktop alias to a concrete IP before advertising it. Kubernetes
    workloads must not use this fallback, so it is only considered outside
    cluster runtimes.
    """
    if sys.platform != "darwin" or os.getenv("KUBERNETES_SERVICE_HOST"):
        return None

    return _first_non_loopback_ip("host.docker.internal")


def _normalize_service_host(host: Optional[str]) -> Optional[str]:
    """
    Normalize a host before advertising it to Consul.

    For native macOS local development we prefer concrete IPs over DNS names so
    APISIX Consul discovery can forward to them without tripping over domain
    host restrictions.
    """
    if not _usable_service_host(host):
        return host

    if sys.platform != "darwin" or os.getenv("KUBERNETES_SERVICE_HOST"):
        return host

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        return _first_non_loopback_ip(host) or host


def _resolve_service_host(service_host: Optional[str]) -> str:
    """Resolve the address that Consul should advertise for the service."""
    if _usable_service_host(service_host):
        return _normalize_service_host(service_host)

    env_host = os.getenv("SERVICE_HOST")
    if _usable_service_host(env_host):
        return _normalize_service_host(env_host)

    desktop_gateway = _desktop_gateway_host()
    if desktop_gateway:
        return desktop_gateway

    hostname = os.getenv("HOSTNAME", socket.gethostname())
    if _usable_service_host(hostname):
        return _normalize_service_host(hostname)

    return hostname


class ConsulRegistry:
    """Handles service registration and discovery with Consul"""

    def __init__(
        self,
        service_name: Optional[str] = None,
        service_port: Optional[int] = None,
        consul_host: str = "localhost",
        consul_port: int = 8500,
        service_host: Optional[str] = None,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, str]] = None,
        health_check_type: str = "ttl",  # ttl or http
    ):
        """
        Initialize Consul registry

        Args:
            service_name: Name of the service to register (optional, required only for registration)
            service_port: Port the service is running on (optional, required only for registration)
            consul_host: Consul server host
            consul_port: Consul server port
            service_host: Service host (defaults to hostname)
            tags: Service tags for discovery
            meta: Service metadata for APISIX routing (e.g., {"api_path": "/api/v1/billing", "auth_required": "true"})
            health_check_type: Type of health check (ttl or http)

        Note:
            - For discovery-only usage, you can omit service_name and service_port
            - For registration, both service_name and service_port are required
            - meta can contain routing information for dynamic APISIX configuration
        """
        self.consul = consul.Consul(host=consul_host, port=consul_port)
        self.service_name = service_name
        self.service_port = service_port
        self.meta = meta or {}

        # Only set these if we're registering (have service_name and service_port)
        if service_name and service_port is not None:
            self.service_host = _resolve_service_host(service_host)

            # Final guard: warn if the resolved address is still loopback
            if _is_loopback(self.service_host):
                logger.warning(
                    f"Consul will register {service_name} at loopback address "
                    f"'{self.service_host}'. This is unreachable from APISIX/gateway "
                    f"context and will cause 502 errors. Set SERVICE_HOST to a "
                    f"routable address (container hostname, K8s service DNS, or "
                    f"host-reachable IP)."
                )

            self.service_id = f"{service_name}-{self.service_host}-{service_port}"
        else:
            self.service_host = service_host or os.getenv(
                "HOSTNAME", socket.gethostname()
            )
            self.service_id = None  # No service ID for discovery-only mode

        self.tags = tags or []
        self.check_interval = "15s"
        self.deregister_after = "90s"  # 增加到90秒，给服务更多时间
        self._health_check_task = None
        self.health_check_type = health_check_type
        self.ttl_interval = 30  # 标准30秒TTL间隔

    def cleanup_stale_registrations(self) -> int:
        """
        Clean up stale registrations for this service before registering.
        Removes any existing registrations with different hostnames (e.g., old container IDs).

        Returns:
            Number of stale registrations removed
        """
        try:
            removed_count = 0
            services = self.consul.agent.services()

            # Find all registrations for this service name on the same port
            for service_id, service_info in services.items():
                if (
                    service_info["Service"] == self.service_name
                    and service_info["Port"] == self.service_port
                    and service_id != self.service_id
                ):  # Different service_id = stale
                    logger.info(
                        f"🧹 Removing stale registration: {service_id} (address: {service_info['Address']})"
                    )
                    self.consul.agent.service.deregister(service_id)
                    removed_count += 1

            if removed_count > 0:
                logger.info(
                    f"✨ Cleaned up {removed_count} stale registration(s) for {self.service_name}"
                )

            return removed_count

        except Exception as e:
            logger.warning(f"⚠️  Failed to cleanup stale registrations: {e}")
            return 0

    def register(self, cleanup_stale: bool = True) -> bool:
        """
        Register service with Consul

        Args:
            cleanup_stale: If True, remove stale registrations before registering (default: True)
        """
        try:
            # Clean up stale registrations first
            if cleanup_stale:
                self.cleanup_stale_registrations()

            # Choose health check type
            if self.health_check_type == "ttl":
                check = consul.Check.ttl(f"{self.ttl_interval}s")
            else:
                check = consul.Check.http(
                    f"http://{self.service_host}:{self.service_port}/health",
                    interval=self.check_interval,
                    timeout="5s",
                    deregister=self.deregister_after,
                )

            # Register service with selected health check
            self.consul.agent.service.register(
                name=self.service_name,
                service_id=self.service_id,
                address=self.service_host,
                port=self.service_port,
                tags=self.tags,
                meta=self.meta,
                check=check,
            )

            # If TTL, immediately pass the health check
            if self.health_check_type == "ttl":
                self.consul.agent.check.ttl_pass(f"service:{self.service_id}")

            logger.info(
                f"✅ Service registered with Consul: {self.service_name} "
                f"({self.service_id}) at {self.service_host}:{self.service_port} "
                f"with {self.health_check_type} health check, tags: {self.tags}"
            )
            self._log_service_metrics("register", True)
            return True

        except Exception as e:
            logger.error(f"❌ Failed to register service with Consul: {e}")
            self._log_service_metrics("register", False)
            return False

    def deregister(self) -> bool:
        """Deregister service from Consul"""
        try:
            self.consul.agent.service.deregister(self.service_id)
            logger.info(f"✅ Service deregistered from Consul: {self.service_id}")
            self._log_service_metrics("deregister", True)
            return True

        except Exception as e:
            logger.error(f"❌ Failed to deregister service from Consul: {e}")
            self._log_service_metrics("deregister", False)
            return False

    async def maintain_registration(self):
        """Maintain service registration (re-register if needed)"""
        retry_count = 0
        max_retries = 3

        while True:
            try:
                # Check if service is still registered
                services = self.consul.agent.services()
                if self.service_id not in services:
                    logger.warning(
                        f"Service {self.service_id} not found in Consul, re-registering..."
                    )
                    if self.register():
                        retry_count = 0  # 重置重试计数
                        logger.info(f"Successfully re-registered {self.service_id}")
                    else:
                        retry_count += 1
                        logger.error(
                            f"Failed to re-register {self.service_id}, retry {retry_count}/{max_retries}"
                        )

                # If using TTL checks, update the health status
                if self.health_check_type == "ttl":
                    try:
                        self.consul.agent.check.ttl_pass(
                            f"service:{self.service_id}",
                            f"Service is healthy - {self.service_name}@{self.service_host}:{self.service_port}",
                        )
                        logger.debug(f"TTL health check passed for {self.service_id}")
                        retry_count = 0  # TTL成功则重置重试计数
                    except Exception as e:
                        retry_count += 1
                        logger.warning(
                            f"Failed to update TTL health check: {e}, retry {retry_count}/{max_retries}"
                        )

                        # 如果TTL连续失败，尝试重新注册
                        if retry_count >= max_retries:
                            logger.error(
                                f"TTL failed {max_retries} times, attempting re-registration"
                            )
                            self.register()
                            retry_count = 0

                # 动态调整睡眠时间，错误时更频繁检查
                if retry_count > 0:
                    sleep_time = 5  # 有错误时5秒检查一次
                else:
                    sleep_time = (
                        self.ttl_interval / 2 if self.health_check_type == "ttl" else 30
                    )

                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                logger.error(
                    f"Error maintaining registration: {e}, retry {retry_count}/{max_retries}"
                )
                # 指数退避
                sleep_time = min(10 * (2 ** (retry_count - 1)), 60)
                await asyncio.sleep(sleep_time)

    def start_maintenance(self):
        """Start the background maintenance task"""
        if not self._health_check_task:
            loop = asyncio.get_event_loop()
            self._health_check_task = loop.create_task(self.maintain_registration())

    def stop_maintenance(self):
        """Stop the background maintenance task"""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

    # Configuration Management Methods
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value from Consul KV store"""
        try:
            full_key = f"{self.service_name}/{key}"
            index, data = self.consul.kv.get(full_key)
            if data and data.get("Value"):
                value = data["Value"].decode("utf-8")
                # Try to parse as JSON
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return default
        except Exception as e:
            logger.error(f"Failed to get config {key}: {e}")
            return default

    def set_config(self, key: str, value: Any) -> bool:
        """Set configuration value in Consul KV store"""
        try:
            full_key = f"{self.service_name}/{key}"
            # Convert to JSON if not string
            if not isinstance(value, str):
                value = json.dumps(value)
            return self.consul.kv.put(full_key, value)
        except Exception as e:
            logger.error(f"Failed to set config {key}: {e}")
            return False

    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration for this service"""
        try:
            prefix = f"{self.service_name}/"
            index, data = self.consul.kv.get(prefix, recurse=True)
            if not data:
                return {}

            config = {}
            for item in data:
                if item["Value"]:
                    key = item["Key"].replace(prefix, "")
                    value = item["Value"].decode("utf-8")
                    try:
                        config[key] = json.loads(value)
                    except json.JSONDecodeError:
                        config[key] = value
            return config
        except Exception as e:
            logger.error(f"Failed to get all config: {e}")
            return {}

    def watch_config(self, key: str, callback):
        """Watch for configuration changes (blocking call)"""
        full_key = f"{self.service_name}/{key}"
        index = None
        while True:
            try:
                index, data = self.consul.kv.get(full_key, index=index, wait="30s")
                if data:
                    value = data["Value"].decode("utf-8")
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                    callback(key, value)
            except Exception as e:
                logger.error(f"Error watching config {key}: {e}")
                break

    # Service Discovery Methods
    def discover_service(self, service_name: str) -> List[Dict[str, Any]]:
        """Discover healthy instances of a service"""
        try:
            # Get health checks for the service
            index, services = self.consul.health.service(service_name, passing=True)

            instances = []
            for service in services:
                instance = {
                    "id": service["Service"]["ID"],
                    "address": service["Service"]["Address"],
                    "port": service["Service"]["Port"],
                    "tags": service["Service"].get("Tags", []),
                    "meta": service["Service"].get("Meta", {}),
                }
                instances.append(instance)

            return instances
        except Exception as e:
            logger.error(f"Failed to discover service {service_name}: {e}")
            return []

    def get_service_endpoint(
        self, service_name: str, strategy: str = "health_weighted"
    ) -> Optional[str]:
        """Get a single service endpoint using advanced load balancing strategy"""
        instances = self.discover_service(service_name)
        if not instances:
            return None

        # 只有一个实例时直接返回
        if len(instances) == 1:
            instance = instances[0]
            return f"http://{instance['address']}:{instance['port']}"

        # 高级负载均衡策略
        if strategy == "health_weighted":
            # 基于健康状态和权重选择最佳实例
            instance = self._select_best_instance(instances)
        elif strategy == "random":
            import random

            instance = random.choice(instances)
        elif strategy == "round_robin":
            # 实现真正的轮询（使用实例缓存）
            instance = self._get_round_robin_instance(service_name, instances)
        elif strategy == "least_connections":
            # 选择连接数最少的实例（模拟实现）
            instance = min(instances, key=lambda x: hash(x["id"]) % 100)
        else:
            # 默认随机选择
            import random

            instance = random.choice(instances)

        return f"http://{instance['address']}:{instance['port']}"

    def _select_best_instance(self, instances: List[Dict[str, Any]]) -> Dict[str, Any]:
        """选择最佳实例（基于健康状态和负载）"""
        # 简单实现：优先选择标签包含'preferred'的实例
        preferred_instances = [
            inst for inst in instances if "preferred" in inst.get("tags", [])
        ]
        if preferred_instances:
            import random

            return random.choice(preferred_instances)

        # 没有首选实例时随机选择
        import random

        return random.choice(instances)

    def _get_round_robin_instance(
        self, service_name: str, instances: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """实现真正的轮询负载均衡"""
        if not hasattr(self, "_round_robin_counters"):
            self._round_robin_counters = {}

        if service_name not in self._round_robin_counters:
            self._round_robin_counters[service_name] = 0

        # 获取当前计数器并递增
        counter = self._round_robin_counters[service_name]
        self._round_robin_counters[service_name] = (counter + 1) % len(instances)

        return instances[counter]

    def _log_service_metrics(
        self, operation: str, success: bool, service_name: str = None
    ):
        """记录服务操作指标"""
        service = service_name or self.service_name
        status = "SUCCESS" if success else "FAILED"

        # 使用项目统一的logger记录指标
        logger.info(
            f"🔍 CONSUL_METRICS | operation={operation} | service={service} | "
            f"status={status} | service_id={self.service_id}"
        )

    def get_service_address(
        self,
        service_name: str,
        fallback_url: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Get service address from Consul discovery with automatic fallback and retry

        Args:
            service_name: Name of the service to discover
            fallback_url: Fallback URL if service not found in Consul (e.g., "http://localhost:8201")
            max_retries: Maximum number of discovery attempts

        Returns:
            Service URL (from Consul or fallback)

        Example:
            consul = ConsulRegistry("my_service", 8080)
            url = consul.get_service_address("account_service", "http://localhost:8201")
            # Returns: "http://10.0.1.5:8201" (from Consul) or "http://localhost:8201" (fallback)
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                endpoint = self.get_service_endpoint(service_name)
                if endpoint:
                    logger.debug(
                        f"Discovered {service_name} at {endpoint} (attempt {attempt + 1})"
                    )
                    return endpoint

                # 如果没找到服务但没有异常，记录并继续
                last_error = f"Service {service_name} not found in Consul registry"

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Consul discovery attempt {attempt + 1} failed for {service_name}: {e}"
                )

                # 短暂等待后重试（除了最后一次）
                if attempt < max_retries - 1:
                    import time

                    time.sleep(0.5 * (attempt + 1))  # 递增延迟

        # 所有重试都失败，使用fallback
        if fallback_url:
            logger.warning(
                f"All {max_retries} discovery attempts failed for {service_name}: {last_error}, using fallback: {fallback_url}"
            )
            return fallback_url

        raise ValueError(
            f"Service {service_name} not found after {max_retries} attempts and no fallback provided. Last error: {last_error}"
        )

    def watch_service(self, service_name: str, callback, wait_time: str = "30s"):
        """Watch for changes in service instances"""
        index = None
        while True:
            try:
                index, services = self.consul.health.service(
                    service_name, passing=True, index=index, wait=wait_time
                )
                # Convert to simplified format
                instances = []
                for service in services:
                    instances.append(
                        {
                            "id": service["Service"]["ID"],
                            "address": service["Service"]["Address"],
                            "port": service["Service"]["Port"],
                        }
                    )
                callback(service_name, instances)
            except Exception as e:
                logger.error(f"Error watching service {service_name}: {e}")
                break

    # ============================================
    # Convenience Methods for Service Discovery
    # ============================================

    def get_auth_service_url(self) -> str:
        """Get auth service URL"""
        endpoint = self.get_service_endpoint("auth_service")
        if not endpoint:
            raise ValueError("Service auth_service not found in Consul")
        return endpoint

    def get_payment_service_url(self) -> str:
        """Get payment service URL"""
        endpoint = self.get_service_endpoint("payment_service")
        if not endpoint:
            raise ValueError("Service payment_service not found in Consul")
        return endpoint

    def get_storage_service_url(self) -> str:
        """Get storage service URL"""
        endpoint = self.get_service_endpoint("storage_service")
        if not endpoint:
            raise ValueError("Service storage_service not found in Consul")
        return endpoint

    def get_notification_service_url(self) -> str:
        """Get notification service URL"""
        endpoint = self.get_service_endpoint("notification_service")
        if not endpoint:
            raise ValueError("Service notification_service not found in Consul")
        return endpoint

    def get_account_service_url(self) -> str:
        """Get account service URL"""
        endpoint = self.get_service_endpoint("account_service")
        if not endpoint:
            raise ValueError("Service account_service not found in Consul")
        return endpoint

    def get_session_service_url(self) -> str:
        """Get session service URL"""
        endpoint = self.get_service_endpoint("session_service")
        if not endpoint:
            raise ValueError("Service session_service not found in Consul")
        return endpoint

    def get_order_service_url(self) -> str:
        """Get order service URL"""
        endpoint = self.get_service_endpoint("order_service")
        if not endpoint:
            raise ValueError("Service order_service not found in Consul")
        return endpoint

    def get_task_service_url(self) -> str:
        """Get task service URL"""
        endpoint = self.get_service_endpoint("task_service")
        if not endpoint:
            raise ValueError("Service task_service not found in Consul")
        return endpoint

    def get_device_service_url(self) -> str:
        """Get device service URL"""
        endpoint = self.get_service_endpoint("device_service")
        if not endpoint:
            raise ValueError("Service device_service not found in Consul")
        return endpoint

    def get_organization_service_url(self) -> str:
        """Get organization service URL"""
        endpoint = self.get_service_endpoint("organization_service")
        if not endpoint:
            raise ValueError("Service organization_service not found in Consul")
        return endpoint

    # Infrastructure Services Discovery
    def get_nats_url(self) -> str:
        """Get NATS message queue URL"""
        endpoint = self.get_service_endpoint("nats-grpc-service")
        if not endpoint:
            raise ValueError("Service nats-grpc-service not found in Consul")
        return endpoint

    def get_redis_url(self) -> str:
        """Get Redis cache URL"""
        endpoint = self.get_service_endpoint("redis-grpc-service")
        if not endpoint:
            raise ValueError("Service redis-grpc-service not found in Consul")
        return endpoint

    def get_loki_url(self) -> str:
        """Get Loki logging service URL"""
        endpoint = self.get_service_endpoint("loki-grpc-service")
        if not endpoint:
            raise ValueError("Service loki-grpc-service not found in Consul")
        return endpoint

    def get_minio_endpoint(self) -> str:
        """Get MinIO object storage endpoint"""
        endpoint = self.get_service_endpoint("minio-grpc-service")
        if not endpoint:
            raise ValueError("Service minio-grpc-service not found in Consul")
        return endpoint

    def get_duckdb_url(self) -> str:
        """Get DuckDB service URL"""
        endpoint = self.get_service_endpoint("duckdb-grpc-service")
        if not endpoint:
            raise ValueError("Service duckdb-grpc-service not found in Consul")
        return endpoint


class AsyncConsulRegistry(AsyncBaseClient):
    """
    Async-compatible Consul service registry — extends AsyncBaseClient.

    Wraps the synchronous python-consul library with asyncio.to_thread()
    so all calls are non-blocking. Supports ``async with`` context manager,
    ``health_check()``, and the same registration / discovery / KV API as
    the synchronous ConsulRegistry.

    Usage::

        async with AsyncConsulRegistry(
            service_name="my-service",
            service_port=8080,
        ) as registry:
            await registry.register()
            endpoint = await registry.get_service_endpoint("other-service")
    """

    SERVICE_NAME = "Consul"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 8500
    ENV_PREFIX = "CONSUL"

    def __init__(
        self,
        service_name: Optional[str] = None,
        service_port: Optional[int] = None,
        consul_host: str = "localhost",
        consul_port: int = 8500,
        service_host: Optional[str] = None,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, str]] = None,
        health_check_type: str = "ttl",
        **kwargs,
    ):
        super().__init__(host=consul_host, port=consul_port, **kwargs)

        self.service_name = service_name
        self.service_port = service_port
        self.meta = meta or {}
        self.tags = tags or []
        self.health_check_type = health_check_type
        self.check_interval = "15s"
        self.deregister_after = "90s"
        self.ttl_interval = 30
        self._consul = None
        self._health_check_task = None

        # Resolve service host (same logic as sync ConsulRegistry)
        if service_name and service_port is not None:
            self.service_host = _resolve_service_host(service_host)

            if _is_loopback(self.service_host):
                logger.warning(
                    f"Consul will register {service_name} at loopback address "
                    f"'{self.service_host}'. Set SERVICE_HOST to a routable address."
                )
            self.service_id = f"{service_name}-{self.service_host}-{service_port}"
        else:
            self.service_host = service_host or os.getenv(
                "HOSTNAME", socket.gethostname()
            )
            self.service_id = None

    # ------------------------------------------------------------------
    # AsyncBaseClient contract
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        self._consul = consul.Consul(host=self._host, port=self._port)
        self._logger.info(f"Consul client connected to {self._host}:{self._port}")

    async def _disconnect(self) -> None:
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        self._consul = None

    async def health_check(self) -> Optional[Dict]:
        try:
            await self._ensure_connected()
            info = await asyncio.to_thread(self._consul.agent.self)
            return {
                "healthy": True,
                "node": info.get("Config", {}).get("NodeName", "unknown"),
                "consul_host": self._host,
                "consul_port": self._port,
            }
        except Exception as e:
            return self.handle_error(e, "health check")

    # ------------------------------------------------------------------
    # Registration (async wrappers around sync consul calls)
    # ------------------------------------------------------------------

    async def register(self, cleanup_stale: bool = True) -> bool:
        try:
            await self._ensure_connected()
            if cleanup_stale:
                await self.cleanup_stale_registrations()

            if self.health_check_type == "ttl":
                check = consul.Check.ttl(f"{self.ttl_interval}s")
            else:
                check = consul.Check.http(
                    f"http://{self.service_host}:{self.service_port}/health",
                    interval=self.check_interval,
                    timeout="5s",
                    deregister=self.deregister_after,
                )

            await asyncio.to_thread(
                self._consul.agent.service.register,
                name=self.service_name,
                service_id=self.service_id,
                address=self.service_host,
                port=self.service_port,
                tags=self.tags,
                meta=self.meta,
                check=check,
            )

            if self.health_check_type == "ttl":
                await asyncio.to_thread(
                    self._consul.agent.check.ttl_pass,
                    f"service:{self.service_id}",
                )

            logger.info(
                f"✅ Service registered: {self.service_name} "
                f"({self.service_id}) at {self.service_host}:{self.service_port}"
            )
            return True
        except Exception as e:
            logger.error(f"❌ Failed to register service: {e}")
            return False

    async def deregister(self) -> bool:
        try:
            await self._ensure_connected()
            await asyncio.to_thread(
                self._consul.agent.service.deregister, self.service_id
            )
            logger.info(f"✅ Service deregistered: {self.service_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to deregister service: {e}")
            return False

    async def cleanup_stale_registrations(self) -> int:
        try:
            await self._ensure_connected()
            services = await asyncio.to_thread(self._consul.agent.services)
            removed = 0
            for sid, info in services.items():
                if (
                    info["Service"] == self.service_name
                    and info["Port"] == self.service_port
                    and sid != self.service_id
                ):
                    await asyncio.to_thread(
                        self._consul.agent.service.deregister, sid
                    )
                    removed += 1
            return removed
        except Exception as e:
            logger.warning(f"⚠️  Failed to cleanup stale registrations: {e}")
            return 0

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def maintain_registration(self):
        """Background task: re-register and TTL-pass periodically."""
        retry_count = 0
        max_retries = 3
        while True:
            try:
                services = await asyncio.to_thread(self._consul.agent.services)
                if self.service_id not in services:
                    logger.warning(f"Re-registering {self.service_id}")
                    if await self.register():
                        retry_count = 0

                if self.health_check_type == "ttl":
                    try:
                        await asyncio.to_thread(
                            self._consul.agent.check.ttl_pass,
                            f"service:{self.service_id}",
                            f"Healthy - {self.service_name}",
                        )
                        retry_count = 0
                    except Exception as e:
                        retry_count += 1
                        if retry_count >= max_retries:
                            await self.register()
                            retry_count = 0

                sleep_time = (
                    5
                    if retry_count > 0
                    else (self.ttl_interval / 2 if self.health_check_type == "ttl" else 30)
                )
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                await asyncio.sleep(min(10 * (2 ** (retry_count - 1)), 60))

    def start_maintenance(self):
        loop = asyncio.get_event_loop()
        self._health_check_task = loop.create_task(self.maintain_registration())

    def stop_maintenance(self):
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

    # ------------------------------------------------------------------
    # KV Configuration
    # ------------------------------------------------------------------

    async def get_config(self, key: str, default: Any = None) -> Any:
        try:
            await self._ensure_connected()
            full_key = f"{self.service_name}/{key}"
            _, data = await asyncio.to_thread(self._consul.kv.get, full_key)
            if data and data.get("Value"):
                value = data["Value"].decode("utf-8")
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return default
        except Exception as e:
            logger.error(f"Failed to get config {key}: {e}")
            return default

    async def set_config(self, key: str, value: Any) -> bool:
        try:
            await self._ensure_connected()
            full_key = f"{self.service_name}/{key}"
            if not isinstance(value, str):
                value = json.dumps(value)
            return await asyncio.to_thread(self._consul.kv.put, full_key, value)
        except Exception as e:
            logger.error(f"Failed to set config {key}: {e}")
            return False

    async def get_all_config(self) -> Dict[str, Any]:
        try:
            await self._ensure_connected()
            prefix = f"{self.service_name}/"
            _, data = await asyncio.to_thread(
                self._consul.kv.get, prefix, recurse=True
            )
            if not data:
                return {}
            config = {}
            for item in data:
                if item["Value"]:
                    key = item["Key"].replace(prefix, "")
                    value = item["Value"].decode("utf-8")
                    try:
                        config[key] = json.loads(value)
                    except json.JSONDecodeError:
                        config[key] = value
            return config
        except Exception as e:
            logger.error(f"Failed to get all config: {e}")
            return {}

    # ------------------------------------------------------------------
    # Service Discovery
    # ------------------------------------------------------------------

    async def discover_service(self, service_name: str) -> List[Dict[str, Any]]:
        try:
            await self._ensure_connected()
            _, services = await asyncio.to_thread(
                self._consul.health.service, service_name, passing=True
            )
            return [
                {
                    "id": s["Service"]["ID"],
                    "address": s["Service"]["Address"],
                    "port": s["Service"]["Port"],
                    "tags": s["Service"].get("Tags", []),
                    "meta": s["Service"].get("Meta", {}),
                }
                for s in services
            ]
        except Exception as e:
            logger.error(f"Failed to discover service {service_name}: {e}")
            return []

    async def get_service_endpoint(
        self, service_name: str, strategy: str = "health_weighted"
    ) -> Optional[str]:
        instances = await self.discover_service(service_name)
        if not instances:
            return None
        if len(instances) == 1:
            inst = instances[0]
            return f"http://{inst['address']}:{inst['port']}"

        import random

        if strategy == "round_robin":
            inst = self._get_round_robin_instance(service_name, instances)
        else:
            inst = random.choice(instances)
        return f"http://{inst['address']}:{inst['port']}"

    async def get_service_address(
        self,
        service_name: str,
        fallback_url: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        last_error = None
        for attempt in range(max_retries):
            try:
                endpoint = await self.get_service_endpoint(service_name)
                if endpoint:
                    return endpoint
                last_error = f"Service {service_name} not found in Consul registry"
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))

        if fallback_url:
            logger.warning(
                f"All discovery attempts failed for {service_name}: {last_error}, "
                f"using fallback: {fallback_url}"
            )
            return fallback_url

        raise ValueError(
            f"Service {service_name} not found after {max_retries} attempts "
            f"and no fallback provided. Last error: {last_error}"
        )

    def _get_round_robin_instance(
        self, service_name: str, instances: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not hasattr(self, "_round_robin_counters"):
            self._round_robin_counters = {}
        if service_name not in self._round_robin_counters:
            self._round_robin_counters[service_name] = 0
        counter = self._round_robin_counters[service_name]
        self._round_robin_counters[service_name] = (counter + 1) % len(instances)
        return instances[counter]


@asynccontextmanager
async def consul_lifespan(
    app,
    service_name: str,
    service_port: int,
    consul_host: str = "localhost",
    consul_port: int = 8500,
    tags: Optional[List[str]] = None,
    meta: Optional[Dict[str, str]] = None,
    health_check_type: str = "ttl",
):
    """
    FastAPI lifespan context manager for Consul registration

    Usage:
        app = FastAPI(lifespan=lambda app: consul_lifespan(
            app,
            "my-service",
            8080,
            meta={"api_path": "/api/v1/myservice", "auth_required": "true"}
        ))
    """
    # Startup
    # Prefer SERVICE_HOST, then macOS Docker Desktop host alias, then hostname.
    service_host = _resolve_service_host(None)

    registry = ConsulRegistry(
        service_name=service_name,
        service_port=service_port,
        consul_host=consul_host,
        consul_port=consul_port,
        service_host=service_host,  # Use SERVICE_HOST from env or hostname
        tags=tags,
        meta=meta,
        health_check_type=health_check_type,
    )

    # Register with Consul
    if registry.register():
        # Start maintenance task
        registry.start_maintenance()
        # Store in app state for access in routes
        app.state.consul_registry = registry
    else:
        logger.warning(
            "Failed to register with Consul, continuing without service discovery"
        )

    yield

    # Shutdown
    if hasattr(app.state, "consul_registry"):
        registry.stop_maintenance()
        registry.deregister()
