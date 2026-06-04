"""L2 component tests — PluginServiceRegistry maps manifest -> Consul meta/tags.

Consul client is mocked (no real Consul agent needed)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from isa_common.plugin import PluginManifest, PluginServiceRegistry

SERVICE_MANIFEST = {
    "id": "sn_erp",
    "name": "SN ERP Service",
    "version": "1.2.0",
    "kind": "service",
    "tenant": "customer-sn",
    "scopes": ["data.read", "data.write"],
    "capabilities": {"routes": ["/orders"]},
    "service": {"api_path": "/api/v1/plugins/erp", "port": 8300, "auth_required": True},
}


@pytest.fixture
def mock_consul():
    with patch("isa_common.consul_client.consul.Consul") as m:
        yield m


class TestPluginServiceRegistry:
    def test_manifest_maps_to_consul_meta(self, mock_consul):
        reg = PluginServiceRegistry(PluginManifest.model_validate(SERVICE_MANIFEST))
        meta = reg.consul_registry.meta
        assert meta["plugin_id"] == "sn_erp"
        assert meta["plugin_kind"] == "service"
        assert meta["plugin_version"] == "1.2.0"
        assert meta["tenant"] == "customer-sn"
        assert meta["api_path"] == "/api/v1/plugins/erp"  # drives APISIX route
        assert meta["auth_required"] == "true"
        assert meta["plugin_scopes"] == "data.read,data.write"
        assert json.loads(meta["plugin_capabilities"]) == {"routes": ["/orders"]}

    def test_tags_carry_plugin_identity(self, mock_consul):
        reg = PluginServiceRegistry(PluginManifest.model_validate(SERVICE_MANIFEST))
        tags = reg.consul_registry.tags
        assert "plugin" in tags
        assert "kind:service" in tags
        assert "tenant:customer-sn" in tags

    def test_auth_required_false_serializes(self, mock_consul):
        man = {
            **SERVICE_MANIFEST,
            "service": {**SERVICE_MANIFEST["service"], "auth_required": False},
        }
        reg = PluginServiceRegistry(PluginManifest.model_validate(man))
        assert reg.consul_registry.meta["auth_required"] == "false"

    def test_service_name_and_port_from_manifest(self, mock_consul):
        reg = PluginServiceRegistry(PluginManifest.model_validate(SERVICE_MANIFEST))
        assert reg.consul_registry.service_name == "sn_erp"
        assert reg.consul_registry.service_port == 8300

    def test_register_delegates_to_consul(self, mock_consul):
        reg = PluginServiceRegistry(PluginManifest.model_validate(SERVICE_MANIFEST))
        reg._registry = MagicMock()
        reg._registry.register.return_value = True
        assert reg.register() is True
        reg._registry.register.assert_called_once()

    def test_non_service_kind_rejected(self, mock_consul):
        agent = {"id": "isa_maestro", "name": "Maestro", "version": "0.3.0", "kind": "agent"}
        with pytest.raises(ValueError, match="kind=service"):
            PluginServiceRegistry(PluginManifest.model_validate(agent))
