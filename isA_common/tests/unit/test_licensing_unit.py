"""L1 unit tests — license startup gate (ADR 0008 §3).

This module covers the startup gate surface ONLY, which has no FastAPI
dependency:
  - startup gate: raises on EXPIRED/INVALID/UNLICENSED when enforce=true,
    proceeds (VALID/GRACE) and is a no-op when enforce=false.

The runtime middleware tests (which require FastAPI + TestClient) live in
``test_licensing_middleware.py`` so this module collects and runs in CI even
though ``fastapi`` is not an isA_common dependency (the licensing middleware
imports it lazily).

No infrastructure required: the license status is patched via get_license.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from isa_common.license import LicenseConfig, LicenseStatus
from isa_common.licensing import LicenseError, setup_licensing

LICENSE_ENV_VARS = ["ISA_LICENSE_ENFORCE", "ISA_LICENSE_FILE", "ISA_LICENSE_PUBKEY"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in LICENSE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


def _lic(status: LicenseStatus) -> LicenseConfig:
    """A LicenseConfig whose expires_at/grace_days are consistent with `status`.

    The runtime middleware now re-derives status via current_status() (H1), so the
    config must carry an expires_at that actually yields `status` — a perpetual
    (expires_at=None) config would always resolve to VALID.
    """
    now = datetime.now(timezone.utc)
    expires_at = None
    grace_days = 0
    if status is LicenseStatus.VALID:
        expires_at = now + timedelta(days=365)
    elif status is LicenseStatus.GRACE:
        expires_at = now - timedelta(days=5)
        grace_days = 30
    elif status is LicenseStatus.EXPIRED:
        expires_at = now - timedelta(days=40)
        grace_days = 30
    # INVALID / UNLICENSED are terminal; expires_at is irrelevant (current_status
    # returns them unchanged).
    return LicenseConfig(
        status=status,
        customer_id="cust",
        edition="on-prem-full",
        expires_at=expires_at,
        grace_days=grace_days,
        entitled_modules=frozenset(),
        quota_tier=None,
        seats=1,
    )


def _patch_status(status: LicenseStatus):
    """Patch the get_license singleton seen by the licensing module."""
    return patch("isa_common.licensing.get_license", return_value=_lic(status))


# ============================================================================
# (a) Startup gate — hard check (ADR 0008 §3)
# ============================================================================


class TestStartupGate:
    @pytest.mark.parametrize("status", [LicenseStatus.EXPIRED, LicenseStatus.INVALID])
    def test_raises_on_expired_or_invalid_when_enforce_true(self, status):
        app = MagicMock()
        with _patch_status(status):
            with pytest.raises(LicenseError):
                setup_licensing(app, enforce=True, enable_middleware=False)

    def test_raises_on_unlicensed_when_enforce_true(self):
        app = MagicMock()
        with _patch_status(LicenseStatus.UNLICENSED):
            with pytest.raises(LicenseError):
                setup_licensing(app, enforce=True, enable_middleware=False)

    @pytest.mark.parametrize("status", [LicenseStatus.VALID, LicenseStatus.GRACE])
    def test_proceeds_on_valid_or_grace_when_enforce_true(self, status):
        app = MagicMock()
        with _patch_status(status):
            result = setup_licensing(app, enforce=True, enable_middleware=False)
        assert result is status

    @pytest.mark.parametrize(
        "status",
        [
            LicenseStatus.EXPIRED,
            LicenseStatus.INVALID,
            LicenseStatus.UNLICENSED,
            LicenseStatus.VALID,
            LicenseStatus.GRACE,
        ],
    )
    def test_never_raises_when_enforce_false(self, status):
        """Enforcement off (SaaS/lite default) → startup gate is a no-op."""
        app = MagicMock()
        with _patch_status(status):
            result = setup_licensing(app, enforce=False, enable_middleware=False)
        assert result is status

    def test_enforce_reads_env_var_true(self, monkeypatch):
        monkeypatch.setenv("ISA_LICENSE_ENFORCE", "true")
        app = MagicMock()
        with _patch_status(LicenseStatus.EXPIRED):
            with pytest.raises(LicenseError):
                setup_licensing(app, enable_middleware=False)

    def test_enforce_env_default_is_off(self):
        """No ISA_LICENSE_ENFORCE set → enforcement off, no raise on EXPIRED."""
        app = MagicMock()
        with _patch_status(LicenseStatus.EXPIRED):
            result = setup_licensing(app, enable_middleware=False)
        assert result is LicenseStatus.EXPIRED

    def test_grace_logs_warning_when_enforce_true(self, caplog):
        app = MagicMock()
        with _patch_status(LicenseStatus.GRACE):
            with caplog.at_level("WARNING", logger="isa_common.licensing"):
                setup_licensing(app, enforce=True, enable_middleware=False)
        assert any("GRACE" in r.message for r in caplog.records)


# ============================================================================
# Export surface (no FastAPI required — just imports isa_common)
# ============================================================================


def test_exports_from_package_root():
    import isa_common

    assert hasattr(isa_common, "setup_licensing")
    assert hasattr(isa_common, "add_license_middleware")
    assert hasattr(isa_common, "LicenseError")
