"""L1 unit tests — edition flags contract (ADR 0006). Pure logic, env-driven."""

import pytest

from isa_common.edition import EditionConfig, EditionType, _parse_bool

# Env vars this module reads — cleared before each test so cases are isolated.
EDITION_ENV_VARS = [
    "ISA_EDITION",
    "ISA_BIGDATA_ENABLED",
    "ISA_METERING_ENABLED",
    "ISA_CHARGING_ENABLED",
    "ISA_MULTI_TENANT",
]


@pytest.fixture(autouse=True)
def clean_edition_env(monkeypatch):
    for var in EDITION_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class TestEditionDefaults:
    def test_saas_matrix(self, monkeypatch):
        monkeypatch.setenv("ISA_EDITION", "saas")
        c = EditionConfig.from_env()
        assert c.edition is EditionType.SAAS
        assert c.bigdata_enabled is False
        assert c.metering_enabled is True
        assert c.charging_enabled is True
        assert c.multi_tenant is True

    def test_on_prem_full_matrix(self, monkeypatch):
        monkeypatch.setenv("ISA_EDITION", "on-prem-full")
        c = EditionConfig.from_env()
        assert c.edition is EditionType.ON_PREM_FULL
        assert c.bigdata_enabled is True
        assert c.metering_enabled is True
        assert c.charging_enabled is False
        assert c.multi_tenant is False

    def test_on_prem_lite_matrix(self, monkeypatch):
        monkeypatch.setenv("ISA_EDITION", "on-prem-lite")
        c = EditionConfig.from_env()
        assert c.edition is EditionType.ON_PREM_LITE
        assert c.bigdata_enabled is False
        assert c.metering_enabled is True
        assert c.charging_enabled is False
        assert c.multi_tenant is False


class TestEditionSelection:
    def test_default_is_on_prem_lite(self):
        c = EditionConfig.from_env()
        assert c.edition is EditionType.ON_PREM_LITE

    @pytest.mark.parametrize("raw", ["", "   ", "enterprise", "SAAS-PLUS", "garbage"])
    def test_unknown_or_blank_falls_back_to_lite(self, monkeypatch, raw):
        monkeypatch.setenv("ISA_EDITION", raw)
        c = EditionConfig.from_env()
        assert c.edition is EditionType.ON_PREM_LITE

    @pytest.mark.parametrize("raw", ["saas", "SAAS", "  SaaS  "])
    def test_edition_parse_is_case_and_space_insensitive(self, monkeypatch, raw):
        monkeypatch.setenv("ISA_EDITION", raw)
        assert EditionConfig.from_env().edition is EditionType.SAAS


class TestPerFlagOverrides:
    def test_override_wins_over_edition_default(self, monkeypatch):
        # saas defaults charging on / bigdata off — flip both via env.
        monkeypatch.setenv("ISA_EDITION", "saas")
        monkeypatch.setenv("ISA_CHARGING_ENABLED", "false")
        monkeypatch.setenv("ISA_BIGDATA_ENABLED", "true")
        c = EditionConfig.from_env()
        assert c.charging_enabled is False
        assert c.bigdata_enabled is True
        # untouched flags keep the saas default
        assert c.multi_tenant is True
        assert c.metering_enabled is True

    def test_unset_override_keeps_edition_default(self, monkeypatch):
        monkeypatch.setenv("ISA_EDITION", "on-prem-full")
        c = EditionConfig.from_env()
        assert c.bigdata_enabled is True  # edition default, no override set

    def test_override_can_enable_on_lite(self, monkeypatch):
        monkeypatch.setenv("ISA_EDITION", "on-prem-lite")
        monkeypatch.setenv("ISA_MULTI_TENANT", "yes")
        monkeypatch.setenv("ISA_CHARGING_ENABLED", "1")
        c = EditionConfig.from_env()
        assert c.multi_tenant is True
        assert c.charging_enabled is True


class TestParseBool:
    @pytest.mark.parametrize("value", ["true", "True", "1", "yes", "  YES  "])
    def test_truthy(self, value):
        assert _parse_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "  NO  "])
    def test_falsy(self, value):
        assert _parse_bool(value) is False

    @pytest.mark.parametrize("value", [None, "", "   ", "maybe", "2", "on"])
    def test_none_for_unset_or_unrecognised(self, value):
        assert _parse_bool(value) is None


def test_frozen_dataclass_is_immutable():
    c = EditionConfig.from_env()
    with pytest.raises(Exception):
        c.charging_enabled = True  # type: ignore[misc]
