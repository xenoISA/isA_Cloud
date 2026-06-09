"""L1 unit tests — license enforcement wiring (ADR 0008 §3).

Two surfaces, two failure modes:
  (a) startup gate: raises on EXPIRED/INVALID/UNLICENSED when enforce=true,
      proceeds (VALID/GRACE) and is a no-op when enforce=false.
  (b) runtime middleware: fail-open — EXPIRED emits an over_license signal but
      NEVER blocks the request. Uses a fake async redis + a FastAPI TestClient.

No infrastructure required: the license status is patched via get_license, and
Redis is a hand-rolled fake injected through the public parameter.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from isa_common.license import LicenseConfig, LicenseStatus
from isa_common.licensing import (
    LicenseError,
    LicenseRuntimeMiddleware,
    add_license_middleware,
    setup_licensing,
)

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


class FakeRedis:
    """Minimal async redis double — get / setex over an in-memory dict."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.setex_calls = []

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value


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
# (b) Runtime middleware — fail-open (ADR 0008 §3)
# ============================================================================


def _app_with_middleware(redis_client):
    app = FastAPI()
    add_license_middleware(app, redis_client=redis_client)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


class TestRuntimeMiddlewareFailOpen:
    def test_expired_does_not_block_request(self):
        """EXPIRED at runtime → request still returns 200 (fail-open)."""
        fake = FakeRedis()
        app = _app_with_middleware(fake)
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_expired_emits_over_license_signal(self, caplog):
        fake = FakeRedis()
        app = _app_with_middleware(fake)
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            with caplog.at_level("WARNING", logger="isa_common.licensing"):
                client.get("/ping")
        assert any("over_license=true" in r.message for r in caplog.records)
        assert any(getattr(r, "over_license", False) for r in caplog.records)

    def test_grace_emits_over_license_signal(self, caplog):
        """GRACE is metered too (ADR 0008 §3) — over_license on GRACE AND EXPIRED."""
        fake = FakeRedis()
        app = _app_with_middleware(fake)
        with _patch_status(LicenseStatus.GRACE):
            client = TestClient(app)
            with caplog.at_level("WARNING", logger="isa_common.licensing"):
                resp = client.get("/ping")
        assert resp.status_code == 200
        assert any("over_license=true" in r.message for r in caplog.records)
        assert any(
            getattr(r, "license_status", None) == LicenseStatus.GRACE.value
            for r in caplog.records
        )

    def test_valid_does_not_block_or_warn(self, caplog):
        fake = FakeRedis()
        app = _app_with_middleware(fake)
        with _patch_status(LicenseStatus.VALID):
            client = TestClient(app)
            with caplog.at_level("WARNING", logger="isa_common.licensing"):
                resp = client.get("/ping")
        assert resp.status_code == 200
        assert not any("over_license" in r.message for r in caplog.records)

    def test_status_cached_to_redis_on_miss(self):
        """The resolved runtime status is written to Redis with a 1h TTL."""
        from isa_common.licensing import (
            LICENSE_STATUS_CACHE_KEY,
            LICENSE_STATUS_CACHE_TTL,
        )

        fake = FakeRedis()
        app = _app_with_middleware(fake)
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            client.get("/ping")
        assert fake.setex_calls
        key, ttl, value = fake.setex_calls[0]
        assert key == LICENSE_STATUS_CACHE_KEY
        assert ttl == LICENSE_STATUS_CACHE_TTL
        assert value == LicenseStatus.EXPIRED.value

    def test_real_client_shaped_double_cache_write_happens(self):
        """A double shaped like the REAL AsyncRedisClient (set(ttl_seconds=) +
        set_with_ttl, NO setex) must actually be written — the old `set(..., ex=)`
        path raised a swallowed TypeError and never cached (H1).
        """
        from isa_common.licensing import (
            LICENSE_STATUS_CACHE_KEY,
            LICENSE_STATUS_CACHE_TTL,
        )

        class RealShapedRedis:
            """Mirrors AsyncRedisClient: set(key, value, ttl_seconds=0),
            set_with_ttl(key, value, ttl_seconds), get — and crucially NO setex."""

            def __init__(self):
                self.store = {}
                self.set_calls = []
                self.set_with_ttl_calls = []

            async def get(self, key):
                return self.store.get(key)

            async def set(self, key, value, ttl_seconds=0):
                # Reject the broken `ex=` kwarg the same way the real client would
                # (its signature has no `ex` param → TypeError).
                self.set_calls.append((key, value, ttl_seconds))
                self.store[key] = value
                return True

            async def set_with_ttl(self, key, value, ttl_seconds):
                self.set_with_ttl_calls.append((key, value, ttl_seconds))
                self.store[key] = value
                return True

        real = RealShapedRedis()
        assert not hasattr(real, "setex")
        app = _app_with_middleware(real)
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            resp = client.get("/ping")
        assert resp.status_code == 200
        # The write actually happened via set_with_ttl (preferred real-client API).
        assert real.set_with_ttl_calls == [
            (LICENSE_STATUS_CACHE_KEY, LicenseStatus.EXPIRED.value, LICENSE_STATUS_CACHE_TTL)
        ]
        assert real.store.get(LICENSE_STATUS_CACHE_KEY) == LicenseStatus.EXPIRED.value

    def test_real_client_without_set_with_ttl_uses_set_ttl_seconds(self):
        """If only set(key, value, ttl_seconds=) exists, the write uses it (no ex=)."""
        from isa_common.licensing import (
            LICENSE_STATUS_CACHE_KEY,
            LICENSE_STATUS_CACHE_TTL,
        )

        class SetOnlyRedis:
            def __init__(self):
                self.store = {}
                self.set_calls = []

            async def get(self, key):
                return self.store.get(key)

            async def set(self, key, value, ttl_seconds=0):
                self.set_calls.append((key, value, ttl_seconds))
                self.store[key] = value
                return True

        real = SetOnlyRedis()
        assert not hasattr(real, "setex")
        assert not hasattr(real, "set_with_ttl")
        app = _app_with_middleware(real)
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            client.get("/ping")
        assert real.set_calls == [
            (LICENSE_STATUS_CACHE_KEY, LicenseStatus.EXPIRED.value, LICENSE_STATUS_CACHE_TTL)
        ]

    def test_runtime_status_rederived_not_trusted_from_cache(self, caplog):
        """Freshness does NOT depend on the cache: a stale cached VALID is ignored —
        the expiry decision uses the freshly-derived current_status() (H1)."""
        from isa_common.licensing import LICENSE_STATUS_CACHE_KEY

        # Cache says VALID (stale), but the live license is EXPIRED.
        fake = FakeRedis(initial={LICENSE_STATUS_CACHE_KEY: LicenseStatus.VALID.value})
        app = _app_with_middleware(fake)
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            with caplog.at_level("WARNING", logger="isa_common.licensing"):
                resp = client.get("/ping")
        assert resp.status_code == 200
        # over_license emitted because the FRESH status is EXPIRED (cache was stale).
        assert any(getattr(r, "over_license", False) for r in caplog.records)

    def test_fail_open_when_redis_errors(self):
        """A redis that raises must not block the request."""

        class BrokenRedis:
            async def get(self, key):
                raise RuntimeError("redis down")

            async def setex(self, key, ttl, value):
                raise RuntimeError("redis down")

        app = _app_with_middleware(BrokenRedis())
        with _patch_status(LicenseStatus.EXPIRED):
            client = TestClient(app)
            resp = client.get("/ping")
        assert resp.status_code == 200

    def test_setup_licensing_installs_middleware(self):
        """setup_licensing(enable_middleware=True) wires the fail-open path end-to-end."""
        app = FastAPI()

        @app.get("/ping")
        def ping():
            return {"ok": True}

        fake = FakeRedis()
        with _patch_status(LicenseStatus.EXPIRED):
            # enforce off so the startup gate does not raise; middleware still installed
            setup_licensing(app, enforce=False, redis_client=fake)
            client = TestClient(app)
            resp = client.get("/ping")
        assert resp.status_code == 200
        assert fake.setex_calls  # middleware ran and cached


# ============================================================================
# Export surface
# ============================================================================


def test_exports_from_package_root():
    import isa_common

    assert hasattr(isa_common, "setup_licensing")
    assert hasattr(isa_common, "add_license_middleware")
    assert hasattr(isa_common, "LicenseError")


def test_middleware_class_directly_callable():
    """LicenseRuntimeMiddleware is usable standalone with an injected fake."""
    import asyncio

    fake = FakeRedis()
    mw = LicenseRuntimeMiddleware(redis_client=fake)

    async def call_next(req):
        return "RESPONSE"

    with _patch_status(LicenseStatus.EXPIRED):
        result = asyncio.run(mw(MagicMock(), call_next))
    assert result == "RESPONSE"
