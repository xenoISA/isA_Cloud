"""L1 unit tests — plugin manifest contract (ADR 0006). Pure validation, no I/O."""

import pytest

from isa_common.plugin import (
    PluginKind,
    PluginManifest,
    ServiceBinding,
    load_manifest,
)

VALID_SERVICE = {
    "id": "sn_erp",
    "name": "SN ERP Service",
    "version": "1.2.0",
    "kind": "service",
    "tenant": "customer-sn",
    "scopes": ["data.read", "data.write"],
    "dependencies": ["sn_auth>=1.0"],
    "capabilities": {"routes": ["/orders", "/inventory"]},
    "service": {"api_path": "/api/v1/plugins/erp", "port": 8300, "auth_required": True},
}


class TestPluginManifest:
    def test_valid_service_manifest(self):
        m = PluginManifest.model_validate(VALID_SERVICE)
        assert m.id == "sn_erp"
        assert m.kind is PluginKind.SERVICE
        assert m.tenant == "customer-sn"
        assert m.service is not None
        assert m.service.port == 8300

    def test_load_manifest_from_dict(self):
        m = load_manifest(VALID_SERVICE)
        assert isinstance(m, PluginManifest)
        assert m.id == "sn_erp"

    def test_defaults(self):
        m = PluginManifest.model_validate(
            {"id": "x", "name": "X", "version": "0.1.0", "kind": "tool"}
        )
        assert m.tenant == "platform"
        assert m.scopes == []
        assert m.dependencies == []
        assert m.capabilities == {}
        assert m.service is None

    @pytest.mark.parametrize("bad_id", ["SN_ERP", "sn-erp", "sn erp", "", "Erp"])
    def test_id_must_be_lowercase_underscore(self, bad_id):
        bad = {**VALID_SERVICE, "id": bad_id}
        with pytest.raises(ValueError):
            PluginManifest.model_validate(bad)

    def test_service_kind_requires_binding(self):
        bad = {k: v for k, v in VALID_SERVICE.items() if k != "service"}
        with pytest.raises(ValueError):
            PluginManifest.model_validate(bad)

    def test_non_service_kind_needs_no_binding(self):
        m = PluginManifest.model_validate(
            {"id": "isa_maestro", "name": "Maestro", "version": "0.3.0", "kind": "agent"}
        )
        assert m.service is None
        assert m.kind is PluginKind.AGENT

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError):
            PluginManifest.model_validate({**VALID_SERVICE, "kind": "wormhole"})


class TestServiceBinding:
    def test_api_path_must_have_leading_slash(self):
        with pytest.raises(ValueError):
            ServiceBinding(api_path="api/v1/x", port=8300)

    def test_api_path_trailing_slash_stripped(self):
        b = ServiceBinding(api_path="/api/v1/x/", port=8300)
        assert b.api_path == "/api/v1/x"

    @pytest.mark.parametrize("port", [0, 70000, -1])
    def test_port_range(self, port):
        with pytest.raises(ValueError):
            ServiceBinding(api_path="/x", port=port)

    def test_health_check_type_validated(self):
        with pytest.raises(ValueError):
            ServiceBinding(api_path="/x", port=8300, health_check_type="ping")
        assert (
            ServiceBinding(api_path="/x", port=8300, health_check_type="http").health_check_type
            == "http"
        )


def test_load_manifest_from_yaml_file(tmp_path):
    import yaml

    p = tmp_path / "plugin.yaml"
    p.write_text(yaml.safe_dump(VALID_SERVICE))
    m = load_manifest(p)
    assert m.id == "sn_erp"
    assert m.service.api_path == "/api/v1/plugins/erp"
