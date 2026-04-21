"""Unit tests for ConsulRegistry — #119."""
import json
import pytest
from unittest.mock import MagicMock, patch, call


# ============================================================================
# L1 — Pure helper functions
# ============================================================================


class TestIsLoopback:
    """_is_loopback detects loopback addresses."""

    def test_ipv4_loopback(self):
        from isa_common.consul_client import _is_loopback
        assert _is_loopback("127.0.0.1") is True

    def test_ipv6_loopback(self):
        from isa_common.consul_client import _is_loopback
        assert _is_loopback("::1") is True

    def test_localhost_string(self):
        from isa_common.consul_client import _is_loopback
        assert _is_loopback("localhost") is True
        assert _is_loopback("LOCALHOST") is True

    def test_non_loopback(self):
        from isa_common.consul_client import _is_loopback
        assert _is_loopback("10.0.0.1") is False
        assert _is_loopback("192.168.1.1") is False

    def test_127_x_variants(self):
        from isa_common.consul_client import _is_loopback
        assert _is_loopback("127.0.0.2") is True
        assert _is_loopback("127.255.255.255") is True


# ============================================================================
# L2 — ConsulRegistry initialization
# ============================================================================


class TestConsulRegistryInit:
    """ConsulRegistry init and service ID."""

    def test_init_with_service(self, consul_registry):
        assert consul_registry.service_name == "test-service"
        assert consul_registry.service_port == 8080
        assert consul_registry.service_id is not None
        assert "test-service" in consul_registry.service_id

    def test_init_discovery_only(self):
        with patch("isa_common.consul_client.consul.Consul"):
            from isa_common.consul_client import ConsulRegistry
            registry = ConsulRegistry()
            assert registry.service_name is None
            assert registry.service_id is None

    def test_init_prefers_desktop_gateway_ip_for_native_macos_dev(self):
        with patch("isa_common.consul_client.consul.Consul"):
            from isa_common.consul_client import ConsulRegistry

            with patch("isa_common.consul_client.sys.platform", "darwin"), \
                 patch(
                     "isa_common.consul_client.socket.getaddrinfo",
                     return_value=[
                         (2, None, None, None, ("192.168.65.254", 0)),
                     ],
                 ), \
                 patch("isa_common.consul_client.socket.gethostname", return_value="my-mac.local"), \
                 patch.dict("os.environ", {}, clear=True):
                registry = ConsulRegistry(
                    service_name="test-service",
                    service_port=8080,
                )

        assert registry.service_host == "192.168.65.254"
        assert registry.service_id == "test-service-192.168.65.254-8080"

    def test_init_normalizes_service_host_alias_to_ip_for_native_macos_dev(self):
        with patch("isa_common.consul_client.consul.Consul"):
            from isa_common.consul_client import ConsulRegistry

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
                registry = ConsulRegistry(
                    service_name="test-service",
                    service_port=8080,
                )

        assert registry.service_host == "192.168.65.254"
        assert registry.service_id == "test-service-192.168.65.254-8080"

    def test_init_does_not_use_host_docker_internal_inside_kubernetes(self):
        with patch("isa_common.consul_client.consul.Consul"):
            from isa_common.consul_client import ConsulRegistry

            with patch("isa_common.consul_client.sys.platform", "darwin"), \
                 patch("isa_common.consul_client.socket.getaddrinfo", return_value=[object()]), \
                 patch.dict(
                     "os.environ",
                     {
                         "KUBERNETES_SERVICE_HOST": "10.96.0.1",
                         "HOSTNAME": "apisix-pod-0",
                     },
                     clear=True,
                 ):
                registry = ConsulRegistry(
                    service_name="test-service",
                    service_port=8080,
                )

        assert registry.service_host == "apisix-pod-0"
        assert registry.service_id == "test-service-apisix-pod-0-8080"


# ============================================================================
# L2 — Registration / deregistration
# ============================================================================


class TestConsulRegistryRegister:
    """register() and deregister() operations."""

    def test_register_success(self, consul_registry):
        consul_registry.consul.agent.service.register = MagicMock()
        consul_registry.consul.agent.check.ttl_pass = MagicMock()
        consul_registry.consul.agent.services.return_value = {}

        result = consul_registry.register()
        assert result is True
        consul_registry.consul.agent.service.register.assert_called_once()

    def test_register_failure(self, consul_registry):
        consul_registry.consul.agent.service.register = MagicMock(
            side_effect=Exception("connection refused")
        )
        consul_registry.consul.agent.services.return_value = {}

        result = consul_registry.register()
        assert result is False

    def test_deregister_success(self, consul_registry):
        consul_registry.consul.agent.service.deregister = MagicMock()

        result = consul_registry.deregister()
        assert result is True
        consul_registry.consul.agent.service.deregister.assert_called_once_with(
            consul_registry.service_id
        )

    def test_deregister_failure(self, consul_registry):
        consul_registry.consul.agent.service.deregister = MagicMock(
            side_effect=Exception("not found")
        )

        result = consul_registry.deregister()
        assert result is False


class TestConsulRegistryCleanupStale:
    """cleanup_stale_registrations removes old entries."""

    def test_cleanup_removes_stale(self, consul_registry):
        consul_registry.consul.agent.services.return_value = {
            consul_registry.service_id: {
                "Service": "test-service",
                "Port": 8080,
                "Address": consul_registry.service_host,
            },
            "test-service-old-host-8080": {
                "Service": "test-service",
                "Port": 8080,
                "Address": "old-host",
            },
        }
        consul_registry.consul.agent.service.deregister = MagicMock()

        count = consul_registry.cleanup_stale_registrations()
        assert count == 1
        consul_registry.consul.agent.service.deregister.assert_called_once_with(
            "test-service-old-host-8080"
        )

    def test_cleanup_no_stale(self, consul_registry):
        consul_registry.consul.agent.services.return_value = {
            consul_registry.service_id: {
                "Service": "test-service",
                "Port": 8080,
                "Address": consul_registry.service_host,
            },
        }

        count = consul_registry.cleanup_stale_registrations()
        assert count == 0

    def test_cleanup_handles_error(self, consul_registry):
        consul_registry.consul.agent.services.side_effect = Exception("timeout")
        count = consul_registry.cleanup_stale_registrations()
        assert count == 0


# ============================================================================
# L2 — Configuration management
# ============================================================================


class TestConsulRegistryConfig:
    """KV store get/set/get_all operations."""

    def test_get_config_string(self, consul_registry):
        consul_registry.consul.kv.get.return_value = (
            1, {"Value": b"hello"}
        )
        result = consul_registry.get_config("key1")
        assert result == "hello"

    def test_get_config_json(self, consul_registry):
        consul_registry.consul.kv.get.return_value = (
            1, {"Value": json.dumps({"a": 1}).encode()}
        )
        result = consul_registry.get_config("key1")
        assert result == {"a": 1}

    def test_get_config_missing(self, consul_registry):
        consul_registry.consul.kv.get.return_value = (0, None)
        result = consul_registry.get_config("missing", default="fallback")
        assert result == "fallback"

    def test_get_config_error(self, consul_registry):
        consul_registry.consul.kv.get.side_effect = Exception("timeout")
        result = consul_registry.get_config("key1", default="safe")
        assert result == "safe"

    def test_set_config_string(self, consul_registry):
        consul_registry.consul.kv.put.return_value = True
        result = consul_registry.set_config("key1", "value1")
        assert result is True
        consul_registry.consul.kv.put.assert_called_once_with(
            "test-service/key1", "value1"
        )

    def test_set_config_dict(self, consul_registry):
        consul_registry.consul.kv.put.return_value = True
        result = consul_registry.set_config("key1", {"a": 1})
        assert result is True
        call_args = consul_registry.consul.kv.put.call_args
        assert json.loads(call_args[0][1]) == {"a": 1}

    def test_set_config_error(self, consul_registry):
        consul_registry.consul.kv.put.side_effect = Exception("timeout")
        result = consul_registry.set_config("key1", "val")
        assert result is False

    def test_get_all_config(self, consul_registry):
        consul_registry.consul.kv.get.return_value = (1, [
            {"Key": "test-service/db_host", "Value": b"localhost"},
            {"Key": "test-service/db_port", "Value": b"5432"},
        ])
        result = consul_registry.get_all_config()
        assert result == {"db_host": "localhost", "db_port": 5432}

    def test_get_all_config_empty(self, consul_registry):
        consul_registry.consul.kv.get.return_value = (0, None)
        result = consul_registry.get_all_config()
        assert result == {}


# ============================================================================
# L2 — Service discovery
# ============================================================================


class TestConsulRegistryDiscovery:
    """Service discovery operations."""

    def test_discover_service(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [
            {
                "Service": {
                    "ID": "svc-1",
                    "Address": "10.0.0.1",
                    "Port": 8080,
                    "Tags": ["v1"],
                    "Meta": {},
                }
            },
            {
                "Service": {
                    "ID": "svc-2",
                    "Address": "10.0.0.2",
                    "Port": 8080,
                    "Tags": ["v1"],
                    "Meta": {},
                }
            },
        ])

        instances = consul_registry.discover_service("my-service")
        assert len(instances) == 2
        assert instances[0]["address"] == "10.0.0.1"

    def test_discover_service_empty(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [])
        instances = consul_registry.discover_service("missing-service")
        assert instances == []

    def test_discover_service_error(self, consul_registry):
        consul_registry.consul.health.service.side_effect = Exception("timeout")
        instances = consul_registry.discover_service("my-service")
        assert instances == []


class TestConsulRegistryEndpoint:
    """get_service_endpoint and get_service_address."""

    def test_get_service_endpoint_single(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [
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
        result = consul_registry.get_service_endpoint("my-service")
        assert result == "http://10.0.0.1:8080"

    def test_get_service_endpoint_none(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [])
        result = consul_registry.get_service_endpoint("missing")
        assert result is None

    def test_get_service_address_with_fallback(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [])
        result = consul_registry.get_service_address(
            "missing", fallback_url="http://localhost:9090", max_retries=1
        )
        assert result == "http://localhost:9090"

    def test_get_service_address_no_fallback_raises(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [])
        with pytest.raises(ValueError, match="not found"):
            consul_registry.get_service_address("missing", max_retries=1)

    def test_get_service_address_success(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [
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
        result = consul_registry.get_service_address("my-service")
        assert result == "http://10.0.0.1:8080"


class TestConsulRegistryConvenience:
    """Convenience get_*_service_url methods."""

    def test_get_auth_service_url_not_found(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [])
        with pytest.raises(ValueError, match="auth_service"):
            consul_registry.get_auth_service_url()

    def test_get_auth_service_url_found(self, consul_registry):
        consul_registry.consul.health.service.return_value = (1, [
            {
                "Service": {
                    "ID": "auth-1",
                    "Address": "10.0.0.1",
                    "Port": 8001,
                    "Tags": [],
                    "Meta": {},
                }
            },
        ])
        result = consul_registry.get_auth_service_url()
        assert result == "http://10.0.0.1:8001"


class TestConsulRegistryRoundRobin:
    """Round-robin load balancing."""

    def test_round_robin_cycles(self, consul_registry):
        instances = [
            {"id": "a", "address": "10.0.0.1", "port": 8080, "tags": [], "meta": {}},
            {"id": "b", "address": "10.0.0.2", "port": 8080, "tags": [], "meta": {}},
        ]
        first = consul_registry._get_round_robin_instance("svc", instances)
        second = consul_registry._get_round_robin_instance("svc", instances)
        third = consul_registry._get_round_robin_instance("svc", instances)
        assert first["id"] == "a"
        assert second["id"] == "b"
        assert third["id"] == "a"  # Wraps around


class TestConsulRegistryMaintenance:
    """start_maintenance / stop_maintenance."""

    def test_stop_maintenance_cancels_task(self, consul_registry):
        mock_task = MagicMock()
        consul_registry._health_check_task = mock_task
        consul_registry.stop_maintenance()
        mock_task.cancel.assert_called_once()
        assert consul_registry._health_check_task is None

    def test_stop_maintenance_noop_when_no_task(self, consul_registry):
        consul_registry._health_check_task = None
        consul_registry.stop_maintenance()  # Should not raise
