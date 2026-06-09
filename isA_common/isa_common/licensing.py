#!/usr/bin/env python3
"""
License enforcement wiring for isA services (ADR 0008 §3).

The runtime *half* of the offline license contract. `license.py` (#365) answers
"what is the license?" — this module answers "what does a FastAPI service DO with
it?", split into two enforcement surfaces with deliberately different failure modes:

- **Startup (hard).** `setup_licensing(app)` mirrors `setup_observability(app, ...)`:
  a one-liner called next to the observability setup at service start. When
  `ISA_LICENSE_ENFORCE=true` and `get_license().status` is EXPIRED or INVALID it
  RAISES — the pod crash-loops and the bad install is visible in the cluster.
  VALID/GRACE proceed (GRACE logs a loud warning); UNLICENSED proceeds only when
  enforcement is off. With enforcement off (SaaS/lite default) this is a no-op.

- **Runtime (fail-open).** An optional ASGI/HTTP middleware re-derives the CURRENT
  license status per request via `get_license().current_status()`. The signature is
  verified exactly ONCE (via the lazy `get_license()` singleton at boot); the
  per-request `current_status()` is a cheap datetime compare against `expires_at` +
  `grace_days`, so a license that EXPIRES while the pod stays up is observed
  immediately (H1) instead of freezing the boot status. On GRACE or EXPIRED it warns
  + emits an `over_license` metering signal but NEVER 403s — fail-open. The 1h Redis
  cache is an OPTIONAL optimization to skip recomputation across pods; freshness no
  longer depends on it (the cached enum is only a hint — the expiry decision always
  uses the freshly-derived `current_status()`). Rationale (ADR 0008 §3): the startup
  gate already stops an expired install from *restarting*; killing live traffic
  mid-shift on a clock-edge is a worse failure than a few hours of over-run that
  showback records anyway.

Usage:
    from isa_common import setup_licensing

    app = FastAPI()
    setup_observability(app, service_name="isA_user", version="1.0.0")
    setup_licensing(app)  # startup gate + (optionally) fail-open runtime middleware
"""

import logging
import os
from typing import Optional

from .license import LicenseStatus, get_license

logger = logging.getLogger("isa_common.licensing")

# Env var name (set per-profile in Helm values, see ADR 0008 §6). Off (unset) on
# SaaS/lite → today's behavior; "true" only on on-prem-full / SN.
ISA_LICENSE_ENFORCE = "ISA_LICENSE_ENFORCE"

# Redis key + TTL for the cached runtime status (ADR 0008 §3: cache, don't re-verify).
LICENSE_STATUS_CACHE_KEY = "isa:license:status"
LICENSE_STATUS_CACHE_TTL = 3600  # 1 hour, per ADR 0008 §3


def _enforce_enabled(enforce: Optional[bool]) -> bool:
    """Resolve the enforce flag from an explicit arg or the ISA_LICENSE_ENFORCE env.

    The env default is false (unset) — enforcement is opt-in (ADR 0008 §3).
    """
    if enforce is not None:
        return enforce
    raw = os.getenv(ISA_LICENSE_ENFORCE, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class LicenseError(RuntimeError):
    """Raised at startup when enforcement is on and the license is EXPIRED/INVALID."""


def setup_licensing(
    app,
    *,
    enforce: Optional[bool] = None,
    enable_middleware: bool = True,
    redis_client: Optional[object] = None,
) -> LicenseStatus:
    """Wire license enforcement into a FastAPI/Starlette app (ADR 0008 §3).

    Mirrors `setup_observability(app, ...)`: a single call at service start. Runs
    the hard startup gate, then (optionally) installs the fail-open runtime
    middleware.

    Args:
        app: FastAPI or Starlette application instance.

    Keyword Args:
        enforce: Override for ISA_LICENSE_ENFORCE. None (default) reads the env;
            env default is false (enforcement opt-in).
        enable_middleware: Install the fail-open runtime middleware (default: True).
        redis_client: Optional async redis client used by the middleware to cache
            the resolved status (an optimization only — freshness comes from
            current_status()). Defaults to a lazily-created AsyncRedisClient.
            Injectable so tests can pass a fake.

    Returns:
        The resolved LicenseStatus from `get_license()` (handy for logging/tests).

    Raises:
        LicenseError: when enforcement is on and status is EXPIRED or INVALID.

    Example:
        from isa_common import setup_licensing
        app = FastAPI()
        setup_licensing(app)
    """
    enforce_on = _enforce_enabled(enforce)
    status = get_license().status

    # -------------------------------------------------------------------------
    # 1. Startup hard gate (ADR 0008 §3)
    # -------------------------------------------------------------------------
    if enforce_on:
        if status in (LicenseStatus.EXPIRED, LicenseStatus.INVALID):
            # Refuse to start — pod crash-loops, visible in the cluster.
            raise LicenseError(
                f"license enforcement is ON and license status is {status.value!r}: "
                "refusing to start (ADR 0008 §3). Swap in a valid signed license.json."
            )
        if status is LicenseStatus.UNLICENSED:
            raise LicenseError(
                "license enforcement is ON but no license is present (UNLICENSED): "
                "refusing to start (ADR 0008 §3). Set ISA_LICENSE_FILE."
            )
        if status is LicenseStatus.GRACE:
            logger.warning(
                "LICENSE IN GRACE WINDOW — service is starting but the license has "
                "EXPIRED and is within its grace_days. Renew the license now (ADR 0008 §3)."
            )
        else:  # VALID
            logger.info("License OK (status=%s); enforcement is ON.", status.value)
    else:
        logger.info(
            "License enforcement is OFF (ISA_LICENSE_ENFORCE unset/false); "
            "status=%s — startup gate skipped (ADR 0008 §3).",
            status.value,
        )

    # -------------------------------------------------------------------------
    # 2. Fail-open runtime middleware (ADR 0008 §3)
    # -------------------------------------------------------------------------
    if enable_middleware:
        try:
            add_license_middleware(app, redis_client=redis_client)
        except Exception as e:  # never let middleware wiring crash startup
            logger.warning("Failed to install license runtime middleware: %s", e)

    return status


def add_license_middleware(app, *, redis_client: Optional[object] = None) -> None:
    """Install the fail-open runtime license middleware on `app`.

    Exported separately from `setup_licensing` so a service can opt into ONLY the
    runtime check (e.g. a service that does its own startup gating).

    Args:
        app: FastAPI/Starlette app with `.add_middleware`.
        redis_client: Optional async redis client used to cache the resolved status
            (optimization only). Defaults to a lazily-created AsyncRedisClient.
            Injectable for tests.
    """
    from starlette.middleware.base import BaseHTTPMiddleware

    middleware = LicenseRuntimeMiddleware(redis_client=redis_client)

    async def _dispatch(request, call_next):
        return await middleware(request, call_next)

    app.add_middleware(BaseHTTPMiddleware, dispatch=_dispatch)


class LicenseRuntimeMiddleware:
    """Fail-open per-request license check (ADR 0008 §3).

    Per request it re-derives the CURRENT status via `get_license().current_status()`
    — a cheap datetime compare against the signature-verified `expires_at`/`grace_days`
    (the signature itself is verified ONCE, at boot, by the `get_license()` singleton).
    This is what fixes H1: a license that expires while the pod stays up is observed
    immediately instead of freezing the boot status. On GRACE or EXPIRED it warns +
    emits an `over_license` metering signal — but NEVER blocks the request (fail-open).

    The 1h Redis cache is an OPTIONAL optimization to record the resolved status
    across pods; correctness does NOT depend on it (the cached enum is a hint, not
    the expiry decision). The redis client is injectable so tests can pass a fake; a
    redis that is absent or erroring is simply skipped and the request still flows.
    """

    def __init__(self, *, redis_client: Optional[object] = None):
        self._redis = redis_client
        self._redis_init_failed = False

    def _get_redis(self):
        """Lazily build the default AsyncRedisClient (reusing isa_common's client).

        Matches the existing client pattern — we do not invent a new connection.
        """
        if self._redis is not None or self._redis_init_failed:
            return self._redis
        try:
            from .async_redis_client import AsyncRedisClient

            self._redis = AsyncRedisClient()
        except Exception as e:  # fail-open: no redis → fall back to direct read
            logger.debug("license middleware: no redis client available: %s", e)
            self._redis_init_failed = True
            self._redis = None
        return self._redis

    async def _write_cache(self, redis_client, status: LicenseStatus) -> None:
        """Best-effort write of the resolved status to Redis with a 1h TTL.

        Uses the REAL AsyncRedisClient API: `set_with_ttl(key, value, ttl_seconds)`
        if present, else `set(key, value, ttl_seconds=TTL)`. (`setex(key, ttl, value)`
        is only attempted first as a convenience for fakes that expose it — the real
        client does NOT, and the previous `set(..., ex=...)` call raised a swallowed
        TypeError, so the cache was never written in production.) Any failure is
        swallowed: the cache is an optimization, not a correctness dependency.
        """
        if redis_client is None:
            return
        try:
            if hasattr(redis_client, "setex"):
                await redis_client.setex(
                    LICENSE_STATUS_CACHE_KEY, LICENSE_STATUS_CACHE_TTL, status.value
                )
            elif hasattr(redis_client, "set_with_ttl"):
                await redis_client.set_with_ttl(
                    LICENSE_STATUS_CACHE_KEY, status.value, LICENSE_STATUS_CACHE_TTL
                )
            else:
                await redis_client.set(
                    LICENSE_STATUS_CACHE_KEY,
                    status.value,
                    ttl_seconds=LICENSE_STATUS_CACHE_TTL,
                )
        except Exception as e:
            logger.debug("license middleware: redis cache write failed: %s", e)

    async def _runtime_status(self) -> LicenseStatus:
        """Return the CURRENT license status, re-derived per request.

        Correctness comes from `get_license().current_status()` (a cheap datetime
        compare over the signature-verified fields) — NOT from Redis. The signature
        is verified once via the `get_license()` singleton; `current_status()` then
        re-evaluates VALID/GRACE/EXPIRED against the wall clock so expiry on a
        long-lived pod is observed immediately (H1).

        The Redis cache is written best-effort as a cross-pod hint, but the returned
        value is always the freshly-derived status.
        """
        status = get_license().current_status()
        # Best-effort cache write (optimization only — freshness is already correct).
        await self._write_cache(self._get_redis(), status)
        return status

    def _emit_over_license(self, status: LicenseStatus) -> None:
        """Emit the `over_license` metering signal (ADR 0008 §3).

        Wiring a full billing UsageEvent here is too heavy for a per-request hook:
        `BillingEventPublisher.publish_usage` (isa_common/events/billing_event_publisher.py)
        requires a NATS connection plus user/product/usage context that a generic
        license middleware does not have. So we emit a STRUCTURED log carrying
        `over_license=true`, which the always-on metering pipeline (edition-bom) can
        scrape into a usage event's flag.

        TODO(ADR 0008 §3): when a lightweight, context-free metering hook exists on
        isa_common.events, replace this structured log with a real
        `over_license`-flagged usage event.
        """
        logger.warning(
            "over_license signal: license status is %s at runtime — request "
            "allowed (fail-open). over_license=true",
            status.value,
            extra={"over_license": True, "license_status": status.value},
        )

    async def __call__(self, request, call_next):
        """ASGI dispatch: re-derive current status, emit on GRACE/EXPIRED, never block."""
        try:
            status = await self._runtime_status()
            if status in (LicenseStatus.GRACE, LicenseStatus.EXPIRED):
                self._emit_over_license(status)
        except Exception as e:
            # Absolutely never block traffic on a license-check error — fail-open.
            logger.debug("license middleware: status check error (ignored): %s", e)

        return await call_next(request)
