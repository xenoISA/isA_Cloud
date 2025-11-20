"""
Consul Service Registry Module
w
Provides service registration and health check functionality for microservices
"""

import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import consul

logger = logging.getLogger(__name__)


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
            # Handle 0.0.0.0 which is invalid for Consul service registration
            # Priority: 1. Explicit service_host, 2. HOSTNAME env var, 3. socket.gethostname()
            # In Docker, HOSTNAME is set to the container name which is DNS resolvable
            import os

            if service_host and service_host != "0.0.0.0":
                self.service_host = service_host
            else:
                # Priority: SERVICE_HOST (K8s Service DNS) > HOSTNAME (Docker container name) > hostname
                # In K8s: SERVICE_HOST = "service.namespace.svc.cluster.local" (resolvable by Consul)
                # In Docker: SERVICE_HOST not set, falls back to HOSTNAME (container name, also resolvable)
                self.service_host = os.getenv("SERVICE_HOST") or os.getenv(
                    "HOSTNAME", socket.gethostname()
                )
            self.service_id = f"{service_name}-{self.service_host}-{service_port}"
        else:
            import os

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
    # Use SERVICE_HOST env var if available, otherwise use hostname
    import os

    service_host = os.getenv("SERVICE_HOST", socket.gethostname())

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
