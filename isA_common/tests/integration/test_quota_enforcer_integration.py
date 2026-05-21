"""QuotaEnforcer integration tests — requires a running Redis instance.

Exercises the full enforce path against a real Redis: atomic Lua consume,
fixed-window counters with TTL, concurrency-gauge acquire/release, partial
consumption on mid-operation exhaustion, and concurrency safety.

Story xenoISA/isA_Console#643 (epic #639).

Run with:
    REDIS_PORT=6379 python -m pytest \\
        isA_common/tests/integration/test_quota_enforcer_integration.py -v
"""

import asyncio
import os
import socket
import uuid

import pytest
import pytest_asyncio

from isa_common.quota_enforcer import (
    UNLIMITED,
    QuotaEnforcer,
    QuotaExceededError,
    QuotaType,
    TierQuota,
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")


def redis_available() -> bool:
    """Check whether Redis is reachable on the configured host/port."""
    try:
        sock = socket.create_connection((REDIS_HOST, REDIS_PORT), timeout=2)
        sock.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_redis,
    pytest.mark.skipif(
        not redis_available(),
        reason=f"Redis not available at {REDIS_HOST}:{REDIS_PORT}",
    ),
]


@pytest_asyncio.fixture
async def redis_client():
    """Real AsyncRedisClient connected to local Redis."""
    from isa_common import AsyncRedisClient

    client = AsyncRedisClient(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        user_id="quota-itest",
        organization_id="quota-itest-org",
    )
    await client._ensure_connected()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def enforcer(redis_client):
    """A QuotaEnforcer with a per-run unique key prefix (no cross-test bleed)."""
    prefix = f"quota-itest-{uuid.uuid4().hex[:8]}"
    yield QuotaEnforcer(redis_client, key_prefix=prefix)
    # Cleanup — drop every key this run created.
    async for key in redis_client._client.scan_iter(match=f"{prefix}:*"):
        await redis_client._client.delete(key)


def _free_tier() -> TierQuota:
    return TierQuota(
        tier="free",
        tokens_per_hour=10_000,
        gpu_minutes_per_day=5,
        ray_workers=2,
        mcp_calls_per_day=20,
    )


def _enterprise_tier() -> TierQuota:
    return TierQuota(
        tier="enterprise",
        tokens_per_hour=UNLIMITED,
        gpu_minutes_per_day=UNLIMITED,
        ray_workers=UNLIMITED,
        mcp_calls_per_day=UNLIMITED,
    )


# ============================================================================
# Windowed quota — consume, block, TTL
# ============================================================================


class TestWindowedQuotaIntegration:
    async def test_consume_accumulates_across_calls(self, enforcer):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()

        d1 = await enforcer.check_and_consume(
            tier,
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=3000,
        )
        d2 = await enforcer.check_and_consume(
            tier,
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=4000,
        )
        assert d1.allowed and d2.allowed
        assert d1.used == 3000
        assert d2.used == 7000

    async def test_blocks_once_quota_is_exhausted(self, enforcer):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()

        for _ in range(20):
            d = await enforcer.check_and_consume(
                tier,
                org,
                QuotaType.MCP_CALLS_PER_DAY,
                amount=1,
            )
            assert d.allowed

        blocked = await enforcer.check_and_consume(
            tier,
            org,
            QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        assert blocked.allowed is False
        assert blocked.used == 20  # 21st call not consumed
        assert "upgrade" in blocked.message.lower()
        assert blocked.retry_after_seconds > 0

    async def test_counter_key_has_window_ttl(self, enforcer, redis_client):
        org = f"org-{uuid.uuid4().hex[:8]}"
        await enforcer.check_and_consume(
            _free_tier(),
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=100,
        )
        key = enforcer._key(org, QuotaType.TOKENS_PER_HOUR)
        ttl = await redis_client._client.ttl(key)
        # Hourly window — TTL set, within the 1h bound.
        assert 0 < ttl <= 3600

    async def test_enforce_raises_quota_exceeded(self, enforcer):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()

        await enforcer.check_and_consume(
            tier,
            org,
            QuotaType.MCP_CALLS_PER_DAY,
            amount=20,
        )
        with pytest.raises(QuotaExceededError) as exc:
            await enforcer.enforce(
                tier,
                org,
                QuotaType.MCP_CALLS_PER_DAY,
                amount=1,
            )
        assert exc.value.tier == "free"
        assert exc.value.retry_after_seconds > 0


# ============================================================================
# Concurrency safety — atomic Lua under parallel load
# ============================================================================


class TestConcurrencySafetyIntegration:
    async def test_parallel_consume_never_oversubscribes(self, enforcer):
        """50 parallel single-unit consumes against a 20-call quota must
        grant exactly 20 — the atomic Lua script prevents oversubscription."""
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()

        results = await asyncio.gather(
            *[
                enforcer.check_and_consume(
                    tier,
                    org,
                    QuotaType.MCP_CALLS_PER_DAY,
                    amount=1,
                )
                for _ in range(50)
            ]
        )
        granted = sum(1 for r in results if r.allowed)
        assert granted == 20  # exactly the quota, never more


# ============================================================================
# Ray workers — concurrency gauge acquire/release
# ============================================================================


class TestRayWorkerGaugeIntegration:
    async def test_acquire_then_release_frees_the_slot(self, enforcer):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()  # ray_workers = 2

        a1 = await enforcer.check_and_consume(tier, org, QuotaType.RAY_WORKERS, 1)
        a2 = await enforcer.check_and_consume(tier, org, QuotaType.RAY_WORKERS, 1)
        a3 = await enforcer.check_and_consume(tier, org, QuotaType.RAY_WORKERS, 1)
        assert a1.allowed and a2.allowed
        assert a3.allowed is False  # gauge full at 2

        released = await enforcer.release(tier, org, QuotaType.RAY_WORKERS, 1)
        assert released is True

        a4 = await enforcer.check_and_consume(tier, org, QuotaType.RAY_WORKERS, 1)
        assert a4.allowed is True  # slot freed up

    async def test_double_release_clamps_at_zero(self, enforcer, redis_client):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()

        await enforcer.check_and_consume(tier, org, QuotaType.RAY_WORKERS, 1)
        await enforcer.release(tier, org, QuotaType.RAY_WORKERS, 1)
        await enforcer.release(tier, org, QuotaType.RAY_WORKERS, 1)  # double

        key = enforcer._key(org, QuotaType.RAY_WORKERS)
        gauge = await redis_client._client.get(key)
        assert int(gauge or 0) == 0  # clamped, never negative


# ============================================================================
# Partial consumption — graceful mid-operation exhaustion
# ============================================================================


class TestPartialConsumptionIntegration:
    async def test_partial_grant_when_quota_runs_out_mid_operation(self, enforcer):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _free_tier()  # tokens_per_hour = 10_000

        # Consume most of the quota.
        await enforcer.check_and_consume(
            tier,
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=9_700,
        )
        # Now request more than the 300 of remaining headroom.
        result = await enforcer.consume_partial(
            tier,
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=1_000,
        )
        assert result.granted == 300
        assert result.partial is True
        assert result.exhausted is True

        # A follow-up partial consume grants nothing — fully exhausted.
        again = await enforcer.consume_partial(
            tier,
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert again.granted == 0
        assert again.exhausted is True


# ============================================================================
# Enterprise / unlimited — no-op
# ============================================================================


class TestEnterpriseNoopIntegration:
    async def test_enterprise_never_blocks_and_writes_no_counter(
        self,
        enforcer,
        redis_client,
    ):
        org = f"org-{uuid.uuid4().hex[:8]}"
        tier = _enterprise_tier()

        decision = await enforcer.enforce(
            tier,
            org,
            QuotaType.TOKENS_PER_HOUR,
            amount=10**9,
        )
        assert decision.allowed is True
        assert decision.unlimited is True

        key = enforcer._key(org, QuotaType.TOKENS_PER_HOUR)
        assert await redis_client._client.get(key) is None  # nothing written
