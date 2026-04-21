"""Unit tests for AsyncConsulRegistry — #121."""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ============================================================================
# L1 — Verify it extends AsyncBaseClient
# ============================================================================


class TestAsyncConsulRegistryInheritance:
    """AsyncConsulRegistry must extend AsyncBaseClient."""

    def test_is_subclass_of_async_base_client(self):
        from isa_common.async_base_client import AsyncBaseClient
        from isa_common.consul_client import AsyncConsulRegistry

        assert issubclass(AsyncConsulRegistry, AsyncBaseClient)

    def test_has_service_name(self):
        from isa_common.consul_client import AsyncConsulRegistry

        assert AsyncConsulRegistry.SERVICE_NAME == "Consul"

    def test_exported_from_package(self):
        from isa_common import AsyncConsulRegistry
        assert AsyncConsulRegistry is not None


# ============================================================================
# L2 — Context manager support
# ============================================================================


class TestAsyncConsulContextManager:
    """Supports async with."""

    async def test_async_context_manager(self):
        from isa_common.consul_client import AsyncConsulRegistry

        with patch("isa_common.consul_client.consul.Consul") as MockConsul:
            MockConsul.return_value = MagicMock()
            async with AsyncConsulRegistry(
                consul_host="localhost", consul_port=8500, lazy_connect=True
            ) as client:
                assert client.is_connected


class TestAsyncConsulRegistryInit:
    """AsyncConsulRegistry host resolution."""

    def test_init_prefers_desktop_gateway_ip_for_native_macos_dev(self):
        with patch("isa_common.consul_client.consul.Consul"):
            from isa_common.consul_client import AsyncConsulRegistry

            with patch("isa_common.consul_client.sys.platform", "darwin"), \
                 patch(
                     "isa_common.consul_client.socket.getaddrinfo",
                     return_value=[
                         (2, None, None, None, ("192.168.65.254", 0)),
                     ],
                 ), \
                 patch("isa_common.consul_client.socket.gethostname", return_value="my-mac.local"), \
                 patch.dict("os.environ", {}, clear=True):
                registry = AsyncConsulRegistry(
                    service_name="test-service",
                    service_port=8080,
                    lazy_connect=True,
                )

        assert registry.service_host == "192.168.65.254"
        assert registry.service_id == "test-service-192.168.65.254-8080"

    def test_init_normalizes_service_host_alias_to_ip_for_native_macos_dev(self):
        with patch("isa_common.consul_client.consul.Consul"):
            from isa_common.consul_client import AsyncConsulRegistry

            with patch("isa_common.consul_client.sys.platform", "darwin"), \
                 patch(
                     "isa_common.consul_client.socket.getaddrinfo",
                     return_value=[
                         (2, None, None, None, ("192.168.65.254", 0)),
                     ],
                 ), \
                 patch.dict(
                     "os.environ",
                     {"SERVICE_HOST": "host.docker.internal"},
                     clear=True,
                 ):
                registry = AsyncConsulRegistry(
                    service_name="test-service",
                    service_port=8080,
                    lazy_connect=True,
                )

        assert registry.service_host == "192.168.65.254"
        assert registry.service_id == "test-service-192.168.65.254-8080"


# ============================================================================
# L2 — Connect / disconnect lifecycle
# ============================================================================


class TestAsyncConsulConnect:
    """_connect initializes consul client."""

    async def test_connect(self, async_consul_registry):
        # Fixture already sets _connected = True, so verify the consul client exists
        assert async_consul_registry._consul is not None
        assert async_consul_registry.is_connected

    async def test_disconnect(self, async_consul_registry):
        await async_consul_registry._disconnect()
        assert async_consul_registry._consul is None


# ============================================================================
# L2 — Health check
# ============================================================================


class TestAsyncConsulHealthCheck:
    """health_check returns consul status."""

    async def test_health_check_healthy(self, async_consul_registry):
        async_consul_registry._consul.agent.self.return_value = {
            "Config": {"NodeName": "test-node"},
            "Member": {"Status": 1},
        }
        result = await async_consul_registry.health_check()
        assert result["healthy"] is True

    async def test_health_check_error(self, async_consul_registry):
        async_consul_registry._consul.agent.self.side_effect = Exception("timeout")
        result = await async_consul_registry.health_check()
        assert result is None


# ============================================================================
# L2 — Registration
# ============================================================================


class TestAsyncConsulRegister:
    """Async register/deregister operations."""

    async def test_register_success(self, async_consul_registry):
        async_consul_registry._consul.agent.service.register = MagicMock()
        async_consul_registry._consul.agent.check.ttl_pass = MagicMock()
        async_consul_registry._consul.agent.services.return_value = {}

        result = await async_consul_registry.register()
        assert result is True

    async def test_register_failure(self, async_consul_registry):
        async_consul_registry._consul.agent.service.register = MagicMock(
            side_effect=Exception("connection refused")
        )
        async_consul_registry._consul.agent.services.return_value = {}

        result = await async_consul_registry.register()
        assert result is False

    async def test_deregister_success(self, async_consul_registry):
        async_consul_registry._consul.agent.service.deregister = MagicMock()

        result = await async_consul_registry.deregister()
        assert result is True

    async def test_deregister_failure(self, async_consul_registry):
        async_consul_registry._consul.agent.service.deregister = MagicMock(
            side_effect=Exception("not found")
        )
        result = await async_consul_registry.deregister()
        assert result is False


# ============================================================================
# L2 — Stale cleanup
# ============================================================================


class TestAsyncConsulCleanupStale:
    """Async cleanup_stale_registrations."""

    async def test_cleanup_removes_stale(self, async_consul_registry):
        async_consul_registry._consul.agent.services.return_value = {
            async_consul_registry.service_id: {
                "Service": "test-service",
                "Port": 8080,
                "Address": async_consul_registry.service_host,
            },
            "test-service-old-host-8080": {
                "Service": "test-service",
                "Port": 8080,
                "Address": "old-host",
            },
        }
        async_consul_registry._consul.agent.service.deregister = MagicMock()

        count = await async_consul_registry.cleanup_stale_registrations()
        assert count == 1

    async def test_cleanup_no_stale(self, async_consul_registry):
        async_consul_registry._consul.agent.services.return_value = {
            async_consul_registry.service_id: {
                "Service": "test-service",
                "Port": 8080,
                "Address": async_consul_registry.service_host,
            },
        }
        count = await async_consul_registry.cleanup_stale_registrations()
        assert count == 0


# ============================================================================
# L2 — Config management (KV store)
# ============================================================================


class TestAsyncConsulConfig:
    """Async KV store get/set."""

    async def test_get_config(self, async_consul_registry):
        async_consul_registry._consul.kv.get.return_value = (
            1, {"Value": b"hello"}
        )
        result = await async_consul_registry.get_config("key1")
        assert result == "hello"

    async def test_get_config_json(self, async_consul_registry):
        async_consul_registry._consul.kv.get.return_value = (
            1, {"Value": json.dumps({"a": 1}).encode()}
        )
        result = await async_consul_registry.get_config("key1")
        assert result == {"a": 1}

    async def test_get_config_missing(self, async_consul_registry):
        async_consul_registry._consul.kv.get.return_value = (0, None)
        result = await async_consul_registry.get_config("missing", default="fallback")
        assert result == "fallback"

    async def test_set_config(self, async_consul_registry):
        async_consul_registry._consul.kv.put.return_value = True
        result = await async_consul_registry.set_config("key1", "val")
        assert result is True

    async def test_set_config_dict(self, async_consul_registry):
        async_consul_registry._consul.kv.put.return_value = True
        result = await async_consul_registry.set_config("key1", {"a": 1})
        assert result is True

    async def test_get_all_config(self, async_consul_registry):
        async_consul_registry._consul.kv.get.return_value = (1, [
            {"Key": "test-service/db_host", "Value": b"localhost"},
            {"Key": "test-service/db_port", "Value": b"5432"},
        ])
        result = await async_consul_registry.get_all_config()
        assert result == {"db_host": "localhost", "db_port": 5432}


# ============================================================================
# L2 — Service discovery
# ============================================================================


class TestAsyncConsulDiscovery:
    """Async service discovery."""

    async def test_discover_service(self, async_consul_registry):
        async_consul_registry._consul.health.service.return_value = (1, [
            {
                "Service": {
                    "ID": "svc-1",
                    "Address": "10.0.0.1",
                    "Port": 8080,
                    "Tags": ["v1"],
                    "Meta": {},
                }
            },
        ])
        instances = await async_consul_registry.discover_service("my-service")
        assert len(instances) == 1
        assert instances[0]["address"] == "10.0.0.1"

    async def test_discover_service_empty(self, async_consul_registry):
        async_consul_registry._consul.health.service.return_value = (1, [])
        instances = await async_consul_registry.discover_service("missing")
        assert instances == []

    async def test_get_service_endpoint(self, async_consul_registry):
        async_consul_registry._consul.health.service.return_value = (1, [
            {
                "Service": {
                    "ID": "svc-1",
                    "Address": "10.0.0.1",
                    "Port": 8080,
                    "Tags": [],
                    "Meta": {},
                }
            },
        ])
        result = await async_consul_registry.get_service_endpoint("my-service")
        assert result == "http://10.0.0.1:8080"

    async def test_get_service_address_with_fallback(self, async_consul_registry):
        async_consul_registry._consul.health.service.return_value = (1, [])
        result = await async_consul_registry.get_service_address(
            "missing", fallback_url="http://localhost:9090", max_retries=1
        )
        assert result == "http://localhost:9090"

    async def test_get_service_address_no_fallback_raises(self, async_consul_registry):
        async_consul_registry._consul.health.service.return_value = (1, [])
        with pytest.raises(ValueError, match="not found"):
            await async_consul_registry.get_service_address("missing", max_retries=1)


# ============================================================================
# L2 — Backward compatibility
# ============================================================================


class TestConsulLifespanCompat:
    """consul_lifespan still works."""

    def test_consul_lifespan_importable(self):
        from isa_common import consul_lifespan
        assert callable(consul_lifespan)

    def test_old_consul_registry_still_exists(self):
        from isa_common import ConsulRegistry
        # Original sync class is still available
        assert ConsulRegistry is not None
