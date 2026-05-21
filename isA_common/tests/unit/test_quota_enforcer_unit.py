"""Unit tests for the quota_enforcer — mocked Redis client, no infrastructure.

Covers story xenoISA/isA_Console#643 (epic #639, Product Positioning).

The enforcer gates per-org/tenant resource consumption against the active
product_spec tier quotas (token/hr, GPU minutes/day, Ray workers, MCP
calls/day). Quota state lives in Redis; a quota value of ``-1`` (Enterprise
tier) means unlimited and short-circuits to a no-op.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from isa_common.quota_enforcer import (
    UNLIMITED,
    QuotaEnforcer,
    QuotaExceededError,
    QuotaType,
    TierQuota,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def redis_client():
    """AsyncRedisClient with a mocked redis driver."""
    from isa_common import AsyncRedisClient

    client = AsyncRedisClient(
        host="localhost",
        port=6379,
        user_id="test_user",
        organization_id="org1",
        lazy_connect=True,
    )
    client._client = AsyncMock()
    client._pool = AsyncMock()
    client._connected = True
    yield client
    client._connected = False


def _free_tier() -> TierQuota:
    """Free tier — small, finite quotas across all four resources."""
    return TierQuota(
        tier="free",
        tokens_per_hour=10_000,
        gpu_minutes_per_day=5,
        ray_workers=1,
        mcp_calls_per_day=100,
    )


def _pro_tier() -> TierQuota:
    """Pro tier — larger finite quotas."""
    return TierQuota(
        tier="pro",
        tokens_per_hour=1_000_000,
        gpu_minutes_per_day=120,
        ray_workers=8,
        mcp_calls_per_day=10_000,
    )


def _enterprise_tier() -> TierQuota:
    """Enterprise tier — every quota unlimited (-1)."""
    return TierQuota(
        tier="enterprise",
        tokens_per_hour=UNLIMITED,
        gpu_minutes_per_day=UNLIMITED,
        ray_workers=UNLIMITED,
        mcp_calls_per_day=UNLIMITED,
    )


# ============================================================================
# TierQuota — the product_spec contract surface
# ============================================================================


class TestTierQuota:
    def test_quota_lookup_by_canonical_key(self):
        tier = _free_tier()
        assert tier.quota(QuotaType.TOKENS_PER_HOUR) == 10_000
        assert tier.quota(QuotaType.GPU_MINUTES_PER_DAY) == 5
        assert tier.quota(QuotaType.RAY_WORKERS) == 1
        assert tier.quota(QuotaType.MCP_CALLS_PER_DAY) == 100

    def test_quota_lookup_accepts_string_key(self):
        """Mirrors ProductSpecTier.quota(key) which accepts a string."""
        tier = _free_tier()
        assert tier.quota("tokens_per_hour") == 10_000

    def test_quota_unknown_key_raises_keyerror(self):
        tier = _free_tier()
        with pytest.raises(KeyError):
            tier.quota("disk_gb")

    def test_is_unlimited_true_for_minus_one(self):
        tier = _enterprise_tier()
        assert tier.is_unlimited(QuotaType.TOKENS_PER_HOUR) is True
        assert tier.is_unlimited(QuotaType.RAY_WORKERS) is True

    def test_is_unlimited_false_for_finite_quota(self):
        tier = _free_tier()
        assert tier.is_unlimited(QuotaType.TOKENS_PER_HOUR) is False

    def test_from_product_spec_tier_maps_orm_row(self):
        """Bridge from an isA_Data ProductSpecTier-shaped object."""

        class FakeORMTier:
            tier = type("E", (), {"value": "pro"})()
            tokens_per_hour = 1_000_000
            gpu_minutes_per_day = 120
            ray_workers = 8
            mcp_calls_per_day = 10_000

        tier = TierQuota.from_product_spec_tier(FakeORMTier())
        assert tier.tier == "pro"
        assert tier.quota(QuotaType.TOKENS_PER_HOUR) == 1_000_000
        assert tier.quota(QuotaType.RAY_WORKERS) == 8


# ============================================================================
# QuotaType — window semantics
# ============================================================================


class TestQuotaType:
    def test_per_hour_window_is_3600s(self):
        assert QuotaType.TOKENS_PER_HOUR.window_seconds == 3600

    def test_per_day_window_is_86400s(self):
        assert QuotaType.GPU_MINUTES_PER_DAY.window_seconds == 86400
        assert QuotaType.MCP_CALLS_PER_DAY.window_seconds == 86400

    def test_ray_workers_is_concurrency_gauge_not_windowed(self):
        """Ray workers is a concurrent gauge, not a rolling window."""
        assert QuotaType.RAY_WORKERS.window_seconds == 0
        assert QuotaType.RAY_WORKERS.is_concurrency is True

    def test_windowed_types_are_not_concurrency(self):
        assert QuotaType.TOKENS_PER_HOUR.is_concurrency is False


# ============================================================================
# Enterprise / unlimited — no-op path
# ============================================================================


class TestUnlimitedNoop:
    async def test_enterprise_check_allows_without_touching_redis(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_enterprise_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=10**12,
        )
        assert decision.allowed is True
        assert decision.unlimited is True
        redis_client._client.incrby.assert_not_called()
        redis_client._client.get.assert_not_called()

    async def test_enterprise_consume_is_noop(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check_and_consume(
            tier=_enterprise_tier(),
            organization_id="org1",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=5_000,
        )
        assert decision.allowed is True
        assert decision.unlimited is True
        redis_client._client.incrby.assert_not_called()

    async def test_single_unlimited_quota_is_noop_even_on_free_named_tier(self, redis_client):
        """A -1 on any individual quota disables only that quota."""
        tier = TierQuota(
            tier="pro",
            tokens_per_hour=UNLIMITED,  # this one unlimited
            gpu_minutes_per_day=120,
            ray_workers=8,
            mcp_calls_per_day=10_000,
        )
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=tier,
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=10**9,
        )
        assert decision.allowed is True
        assert decision.unlimited is True


# ============================================================================
# check() — read-only gate against windowed quotas
# ============================================================================


class TestWindowedCheck:
    async def test_allows_when_under_quota(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="2000")
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is True
        assert decision.used == 2000
        assert decision.limit == 10_000
        assert decision.remaining == 8000

    async def test_allows_when_no_prior_usage(self, redis_client):
        redis_client._client.get = AsyncMock(return_value=None)
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        assert decision.allowed is True
        assert decision.used == 0

    async def test_blocks_when_request_would_exceed_quota(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="9800")
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is False
        assert decision.remaining == 200

    async def test_allows_request_that_exactly_hits_the_limit(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="9500")
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is True  # 9500 + 500 == 10000

    async def test_blocks_when_already_at_limit(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="100")
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        assert decision.allowed is False


# ============================================================================
# QuotaDecision — clear blocking message
# ============================================================================


class TestQuotaDecisionMessage:
    async def test_blocked_decision_message_names_the_resource(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="100")
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        assert "mcp_calls_per_day" in decision.message
        assert "free" in decision.message

    async def test_blocked_decision_message_has_reset_window(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="100")
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        # daily window — message should mention when it resets
        assert "reset" in decision.message.lower()
        assert decision.retry_after_seconds is not None
        assert decision.retry_after_seconds > 0

    async def test_blocked_decision_message_has_upgrade_hint(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="10000")
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1,
        )
        assert "upgrade" in decision.message.lower()

    async def test_enterprise_tier_gets_no_upgrade_hint(self, redis_client):
        """Top tier has nothing to upgrade to — but it never blocks anyway."""
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_enterprise_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1,
        )
        assert decision.allowed is True

    async def test_allowed_decision_has_empty_retry_after(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="0")
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_pro_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1,
        )
        assert decision.allowed is True
        assert decision.retry_after_seconds is None


# ============================================================================
# check_and_consume() — atomic gate + record
# ============================================================================


class TestCheckAndConsume:
    async def test_consume_increments_counter_when_allowed(self, redis_client):
        # Lua eval returns [allowed, new_total, limit] from the atomic script
        redis_client._client.eval = AsyncMock(return_value=[1, 600, 10_000])
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check_and_consume(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is True
        assert decision.used == 600
        redis_client._client.eval.assert_awaited_once()

    async def test_consume_does_not_increment_when_blocked(self, redis_client):
        # script reports blocked: allowed=0, current usage unchanged
        redis_client._client.eval = AsyncMock(return_value=[0, 9900, 10_000])
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check_and_consume(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is False
        assert decision.used == 9900  # NOT 10400 — not consumed

    async def test_consume_uses_org_scoped_key(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[1, 1, 100])
        enforcer = QuotaEnforcer(redis_client)

        await enforcer.check_and_consume(
            tier=_free_tier(),
            organization_id="acme-corp",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        # the Redis key passed to the Lua script must scope by org
        call_args = redis_client._client.eval.call_args
        key_args = call_args.args
        joined = " ".join(str(a) for a in key_args)
        assert "acme-corp" in joined
        assert "mcp_calls_per_day" in joined


# ============================================================================
# enforce() — raises on block
# ============================================================================


class TestEnforceRaises:
    async def test_enforce_raises_quota_exceeded_when_blocked(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[0, 100, 100])
        enforcer = QuotaEnforcer(redis_client)

        with pytest.raises(QuotaExceededError) as exc:
            await enforcer.enforce(
                tier=_free_tier(),
                organization_id="org1",
                quota_type=QuotaType.MCP_CALLS_PER_DAY,
                amount=1,
            )
        err = exc.value
        assert err.quota_type == QuotaType.MCP_CALLS_PER_DAY
        assert err.tier == "free"
        assert err.retry_after_seconds > 0
        assert "upgrade" in str(err).lower()

    async def test_enforce_returns_decision_when_allowed(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[1, 1, 100])
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.enforce(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.MCP_CALLS_PER_DAY,
            amount=1,
        )
        assert decision.allowed is True

    async def test_enforce_is_noop_for_enterprise(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.enforce(
            tier=_enterprise_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=10**9,
        )
        assert decision.allowed is True
        redis_client._client.eval.assert_not_called()


# ============================================================================
# Ray workers — concurrency gauge (not a rolling window)
# ============================================================================


class TestRayWorkerConcurrency:
    async def test_acquire_worker_slot_when_under_limit(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[1, 1, 1])
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check_and_consume(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.RAY_WORKERS,
            amount=1,
        )
        assert decision.allowed is True
        assert decision.used == 1

    async def test_acquire_worker_slot_blocked_at_limit(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[0, 1, 1])
        enforcer = QuotaEnforcer(redis_client)

        decision = await enforcer.check_and_consume(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.RAY_WORKERS,
            amount=1,
        )
        assert decision.allowed is False

    async def test_release_worker_slot_decrements(self, redis_client):
        redis_client._client.decrby = AsyncMock(return_value=0)
        enforcer = QuotaEnforcer(redis_client)

        released = await enforcer.release(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.RAY_WORKERS,
            amount=1,
        )
        assert released is True
        redis_client._client.decrby.assert_awaited_once()

    async def test_release_never_goes_negative(self, redis_client):
        """A double-release must clamp the gauge at 0, not go negative."""
        redis_client._client.decrby = AsyncMock(return_value=-2)
        redis_client._client.set = AsyncMock(return_value=True)
        enforcer = QuotaEnforcer(redis_client)

        await enforcer.release(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.RAY_WORKERS,
            amount=1,
        )
        # clamped back to 0
        redis_client._client.set.assert_awaited()

    async def test_release_is_noop_for_windowed_quota(self, redis_client):
        """Releasing a token/hr quota makes no sense — windowed quotas decay."""
        enforcer = QuotaEnforcer(redis_client)
        released = await enforcer.release(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=100,
        )
        assert released is False
        redis_client._client.decrby.assert_not_called()

    async def test_release_is_noop_for_enterprise(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        released = await enforcer.release(
            tier=_enterprise_tier(),
            organization_id="org1",
            quota_type=QuotaType.RAY_WORKERS,
            amount=1,
        )
        assert released is True
        redis_client._client.decrby.assert_not_called()


# ============================================================================
# Mid-operation exhaustion — graceful partial result
# ============================================================================


class TestPartialConsumption:
    async def test_consume_partial_returns_granted_amount_when_short(self, redis_client):
        """When only part of the requested amount fits, grant what's available."""
        # script returns [allowed, granted, new_total, limit]
        redis_client._client.eval = AsyncMock(return_value=[1, 300, 10_000, 10_000])
        enforcer = QuotaEnforcer(redis_client)

        result = await enforcer.consume_partial(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1000,
        )
        assert result.granted == 300
        assert result.requested == 1000
        assert result.partial is True
        assert result.exhausted is True

    async def test_consume_partial_grants_full_when_room(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[1, 1000, 5000, 10_000])
        enforcer = QuotaEnforcer(redis_client)

        result = await enforcer.consume_partial(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1000,
        )
        assert result.granted == 1000
        assert result.partial is False
        assert result.exhausted is False

    async def test_consume_partial_grants_zero_when_fully_exhausted(self, redis_client):
        redis_client._client.eval = AsyncMock(return_value=[0, 0, 10_000, 10_000])
        enforcer = QuotaEnforcer(redis_client)

        result = await enforcer.consume_partial(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1000,
        )
        assert result.granted == 0
        assert result.exhausted is True
        assert result.partial is True

    async def test_consume_partial_unlimited_grants_full(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        result = await enforcer.consume_partial(
            tier=_enterprise_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=10**9,
        )
        assert result.granted == 10**9
        assert result.partial is False
        assert result.exhausted is False
        redis_client._client.eval.assert_not_called()


# ============================================================================
# Resilience — Redis failure must not hard-crash the request path
# ============================================================================


class TestRedisFailureResilience:
    async def test_check_fails_open_when_redis_unavailable(self, redis_client):
        """A Redis outage should not block all traffic — fail open, flagged."""
        redis_client._client.get = AsyncMock(side_effect=ConnectionError("down"))
        enforcer = QuotaEnforcer(redis_client, fail_open=True)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is True
        assert decision.degraded is True

    async def test_check_fails_closed_when_configured(self, redis_client):
        redis_client._client.get = AsyncMock(side_effect=ConnectionError("down"))
        enforcer = QuotaEnforcer(redis_client, fail_open=False)

        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=500,
        )
        assert decision.allowed is False
        assert decision.degraded is True

    async def test_consume_partial_degrades_gracefully_on_redis_error(self, redis_client):
        """Mid-operation Redis failure yields a partial result, not a crash."""
        redis_client._client.eval = AsyncMock(side_effect=ConnectionError("down"))
        enforcer = QuotaEnforcer(redis_client, fail_open=True)

        result = await enforcer.consume_partial(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=1000,
        )
        # fail-open: grants the request but flags degradation
        assert result.degraded is True
        assert result.granted == 1000

    async def test_release_swallows_redis_error(self, redis_client):
        redis_client._client.decrby = AsyncMock(side_effect=ConnectionError("down"))
        enforcer = QuotaEnforcer(redis_client)

        released = await enforcer.release(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.RAY_WORKERS,
            amount=1,
        )
        assert released is False  # could not release, but did not raise


# ============================================================================
# Input validation
# ============================================================================


class TestValidation:
    async def test_negative_amount_rejected(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        with pytest.raises(ValueError):
            await enforcer.check(
                tier=_free_tier(),
                organization_id="org1",
                quota_type=QuotaType.TOKENS_PER_HOUR,
                amount=-5,
            )

    async def test_zero_amount_is_allowed_as_probe(self, redis_client):
        """A zero-amount check is a pure read of current usage."""
        redis_client._client.get = AsyncMock(return_value="5000")
        enforcer = QuotaEnforcer(redis_client)
        decision = await enforcer.check(
            tier=_free_tier(),
            organization_id="org1",
            quota_type=QuotaType.TOKENS_PER_HOUR,
            amount=0,
        )
        assert decision.allowed is True
        assert decision.used == 5000

    async def test_empty_organization_id_rejected(self, redis_client):
        enforcer = QuotaEnforcer(redis_client)
        with pytest.raises(ValueError):
            await enforcer.check(
                tier=_free_tier(),
                organization_id="",
                quota_type=QuotaType.TOKENS_PER_HOUR,
                amount=1,
            )


# ============================================================================
# Usage introspection
# ============================================================================


class TestUsageIntrospection:
    async def test_get_usage_returns_all_four_quotas(self, redis_client):
        redis_client._client.mget = AsyncMock(return_value=["3000", "2", "1", "40"])
        enforcer = QuotaEnforcer(redis_client)

        usage = await enforcer.get_usage(
            tier=_free_tier(),
            organization_id="org1",
        )
        assert usage[QuotaType.TOKENS_PER_HOUR].used == 3000
        assert usage[QuotaType.TOKENS_PER_HOUR].limit == 10_000
        assert usage[QuotaType.GPU_MINUTES_PER_DAY].used == 2
        assert usage[QuotaType.RAY_WORKERS].used == 1
        assert usage[QuotaType.MCP_CALLS_PER_DAY].used == 40

    async def test_get_usage_treats_missing_counters_as_zero(self, redis_client):
        redis_client._client.mget = AsyncMock(return_value=[None, None, None, None])
        enforcer = QuotaEnforcer(redis_client)

        usage = await enforcer.get_usage(
            tier=_free_tier(),
            organization_id="org1",
        )
        assert all(q.used == 0 for q in usage.values())
