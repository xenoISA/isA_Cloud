#!/usr/bin/env python3
"""
Quota Enforcer — per-org/tenant resource limit enforcement.

Story xenoISA/isA_Console#643, epic #639 (Product Positioning — SaaS vs
Enterprise).

The SaaS editions differ by *configuration, not code*: the active
``product_spec`` (defined in isA_Data, story #640) maps each tier
(Free / Pro / Enterprise) to four quota values:

==========================  =========  ==========================
canonical key               window     resource
==========================  =========  ==========================
``tokens_per_hour``         1 hour     LLM tokens consumed
``gpu_minutes_per_day``     1 day      GPU compute minutes
``ray_workers``             —          concurrent Ray workers (gauge)
``mcp_calls_per_day``       1 day      MCP tool invocations
==========================  =========  ==========================

A quota value of ``-1`` means *unlimited* (the Enterprise tier) and makes
enforcement a no-op for that quota.

Quota-usage state lives in Redis. Windowed quotas use a fixed-window counter
keyed by org + quota + window-bucket with a TTL equal to the window length —
this is cheap, self-expiring, and multi-region eventual-consistency safe
(each region increments its own replica and replication reconciles). Ray
workers are tracked as a concurrency gauge that callers explicitly
``release`` when a worker exits.

Design notes
------------
- Decoupled from the isA_Data ORM: callers pass a :class:`TierQuota` value
  object. :meth:`TierQuota.from_product_spec_tier` bridges an ORM row.
- Atomic check-and-consume is a single Redis Lua ``EVAL`` so concurrent
  requests within a region cannot oversubscribe a quota.
- Redis failures degrade gracefully (``fail_open``) rather than hard-crash
  the request path; the decision is flagged ``degraded``.
- Mid-operation exhaustion is handled by :meth:`QuotaEnforcer.consume_partial`,
  which grants whatever headroom remains so a long-running operation can stop
  with a partial result instead of crashing.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Union

logger = logging.getLogger("isa_common.quota_enforcer")

# A quota value of -1 means unlimited (matches isA_Data ProductSpecTier.UNLIMITED).
UNLIMITED: int = -1


# =============================================================================
# Quota types
# =============================================================================


class QuotaType(str, Enum):
    """The four enforceable quotas, keyed by their product_spec column name.

    Values match the ``product_spec_tiers`` columns so a caller can look a
    quota up by the same canonical key the schema uses.
    """

    TOKENS_PER_HOUR = "tokens_per_hour"
    GPU_MINUTES_PER_DAY = "gpu_minutes_per_day"
    RAY_WORKERS = "ray_workers"
    MCP_CALLS_PER_DAY = "mcp_calls_per_day"

    @property
    def window_seconds(self) -> int:
        """Length of the rolling window for a windowed quota.

        Returns ``0`` for concurrency gauges (Ray workers), which are not
        windowed — they go up on acquire and down on release.
        """
        if self is QuotaType.TOKENS_PER_HOUR:
            return 3600
        if self in (QuotaType.GPU_MINUTES_PER_DAY, QuotaType.MCP_CALLS_PER_DAY):
            return 86400
        return 0  # RAY_WORKERS — concurrency gauge

    @property
    def is_concurrency(self) -> bool:
        """True for gauge-style quotas (acquire/release), False for windowed."""
        return self is QuotaType.RAY_WORKERS

    @property
    def reset_label(self) -> str:
        """Human-readable description of when a windowed quota resets."""
        if self is QuotaType.TOKENS_PER_HOUR:
            return "the next hourly window"
        if self in (QuotaType.GPU_MINUTES_PER_DAY, QuotaType.MCP_CALLS_PER_DAY):
            return "the next daily window"
        return "a worker slot is released"


def _coerce_quota_type(quota_type: Union[QuotaType, str]) -> QuotaType:
    """Accept either a QuotaType or its canonical string key."""
    if isinstance(quota_type, QuotaType):
        return quota_type
    try:
        return QuotaType(quota_type)
    except ValueError as exc:
        raise KeyError(f"Unknown quota key: {quota_type}") from exc


# =============================================================================
# TierQuota — the product_spec contract surface
# =============================================================================


@dataclass(frozen=True)
class TierQuota:
    """The quota values for a single tier of the active product_spec.

    Mirrors the relevant surface of ``isA_Data`` ``ProductSpecTier`` so the
    enforcer never imports the ORM. A value of :data:`UNLIMITED` (``-1``)
    disables that quota.
    """

    tier: str
    tokens_per_hour: int
    gpu_minutes_per_day: int
    ray_workers: int
    mcp_calls_per_day: int

    def quota(self, key: Union[QuotaType, str]) -> int:
        """Return a quota value by its canonical key.

        Mirrors ``ProductSpecTier.quota(key)`` — callers depend on the
        canonical key, not column attribute names.
        """
        qt = _coerce_quota_type(key)
        return getattr(self, qt.value)

    def is_unlimited(self, key: Union[QuotaType, str]) -> bool:
        """True when the named quota is unlimited (``-1``)."""
        return self.quota(key) == UNLIMITED

    @classmethod
    def from_product_spec_tier(cls, orm_tier) -> "TierQuota":
        """Build a :class:`TierQuota` from an isA_Data ``ProductSpecTier`` row.

        Accepts any object exposing ``tier`` (an enum with ``.value`` or a
        plain string) plus the four quota integer attributes.
        """
        tier_attr = getattr(orm_tier, "tier")
        tier_name = getattr(tier_attr, "value", tier_attr)
        return cls(
            tier=str(tier_name),
            tokens_per_hour=int(orm_tier.tokens_per_hour),
            gpu_minutes_per_day=int(orm_tier.gpu_minutes_per_day),
            ray_workers=int(orm_tier.ray_workers),
            mcp_calls_per_day=int(orm_tier.mcp_calls_per_day),
        )


# =============================================================================
# Decision / result value objects
# =============================================================================


@dataclass
class QuotaDecision:
    """The outcome of a quota check or consume."""

    allowed: bool
    quota_type: QuotaType
    tier: str
    limit: int
    used: int
    requested: int
    unlimited: bool = False
    degraded: bool = False
    message: str = ""
    retry_after_seconds: Optional[int] = None

    @property
    def remaining(self) -> int:
        """Headroom left in the window (0 for an unlimited quota)."""
        if self.unlimited:
            return -1
        return max(0, self.limit - self.used)


@dataclass
class PartialConsumption:
    """The outcome of :meth:`QuotaEnforcer.consume_partial`.

    Lets a long-running operation stop gracefully on a partial result instead
    of crashing when a quota is exhausted mid-flight.
    """

    quota_type: QuotaType
    tier: str
    requested: int
    granted: int
    limit: int
    used: int
    degraded: bool = False

    @property
    def partial(self) -> bool:
        """True when fewer units were granted than requested."""
        return self.granted < self.requested

    @property
    def exhausted(self) -> bool:
        """True when the quota has no headroom left after this consume."""
        if self.limit == UNLIMITED:
            return False
        return self.used >= self.limit


# =============================================================================
# Exception
# =============================================================================


class QuotaExceededError(Exception):
    """Raised by :meth:`QuotaEnforcer.enforce` when a request is blocked.

    Carries enough structured context for an API layer to translate it into a
    429-style response with a ``Retry-After`` header.
    """

    def __init__(self, decision: QuotaDecision):
        self.decision = decision
        self.quota_type = decision.quota_type
        self.tier = decision.tier
        self.limit = decision.limit
        self.used = decision.used
        self.retry_after_seconds = decision.retry_after_seconds or 0
        super().__init__(decision.message)


# =============================================================================
# QuotaEnforcer
# =============================================================================

# Atomic check-and-consume for a windowed quota.
#   KEYS[1] = counter key
#   ARGV[1] = amount, ARGV[2] = limit, ARGV[3] = window TTL seconds
#   returns {allowed, new_total, limit}
_LUA_WINDOWED_CONSUME = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
if current + amount > limit then
    return {0, current, limit}
end
local total = redis.call('INCRBY', KEYS[1], amount)
if total == amount then
    redis.call('EXPIRE', KEYS[1], ttl)
end
return {1, total, limit}
"""

# Atomic acquire for a concurrency gauge (Ray workers).
#   KEYS[1] = gauge key
#   ARGV[1] = amount, ARGV[2] = limit
#   returns {allowed, new_total, limit}
_LUA_GAUGE_ACQUIRE = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
if current + amount > limit then
    return {0, current, limit}
end
local total = redis.call('INCRBY', KEYS[1], amount)
return {1, total, limit}
"""

# Atomic partial consume — grant whatever headroom remains.
#   KEYS[1] = counter key
#   ARGV[1] = amount, ARGV[2] = limit, ARGV[3] = window TTL seconds
#   returns {allowed, granted, new_total, limit}
_LUA_PARTIAL_CONSUME = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local headroom = limit - current
if headroom < 0 then headroom = 0 end
local granted = amount
if granted > headroom then granted = headroom end
if granted <= 0 then
    return {0, 0, current, limit}
end
local total = redis.call('INCRBY', KEYS[1], granted)
if total == granted then
    redis.call('EXPIRE', KEYS[1], ttl)
end
return {1, granted, total, limit}
"""


class QuotaEnforcer:
    """Enforces per-org/tenant resource quotas backed by Redis.

    Usage::

        enforcer = QuotaEnforcer(redis_client)

        # Gate a request — raises QuotaExceededError if over quota.
        await enforcer.enforce(
            tier=active_tier, organization_id="acme",
            quota_type=QuotaType.MCP_CALLS_PER_DAY, amount=1,
        )

        # Acquire / release a Ray worker slot.
        decision = await enforcer.check_and_consume(
            tier=active_tier, organization_id="acme",
            quota_type=QuotaType.RAY_WORKERS, amount=1,
        )
        ...
        await enforcer.release(
            tier=active_tier, organization_id="acme",
            quota_type=QuotaType.RAY_WORKERS, amount=1,
        )

    Args:
        redis_client: an :class:`~isa_common.AsyncRedisClient` instance.
        key_prefix: Redis key namespace for quota counters.
        fail_open: when Redis is unavailable, allow the request (``True``,
            default — availability over strict enforcement) or block it
            (``False``). Either way the decision is flagged ``degraded``.
    """

    def __init__(
        self,
        redis_client,
        key_prefix: str = "quota",
        fail_open: bool = True,
    ):
        self._redis = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._fail_open = fail_open

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------

    def _window_bucket(self, quota_type: QuotaType, now: datetime) -> str:
        """A deterministic bucket id for the current window.

        Fixed-window counters keyed by the bucket id let two regions
        increment independently and reconcile under eventual consistency.
        """
        if quota_type is QuotaType.TOKENS_PER_HOUR:
            return now.strftime("%Y%m%d%H")
        if quota_type in (QuotaType.GPU_MINUTES_PER_DAY, QuotaType.MCP_CALLS_PER_DAY):
            return now.strftime("%Y%m%d")
        return "gauge"

    def _key(self, organization_id: str, quota_type: QuotaType) -> str:
        """Build the Redis key for an org's quota counter."""
        now = datetime.now(timezone.utc)
        bucket = self._window_bucket(quota_type, now)
        return f"{self._key_prefix}:{organization_id}:{quota_type.value}:{bucket}"

    @staticmethod
    def _seconds_until_window_reset(quota_type: QuotaType) -> int:
        """Seconds remaining until the current fixed window rolls over."""
        now = datetime.now(timezone.utc)
        if quota_type is QuotaType.TOKENS_PER_HOUR:
            elapsed = now.minute * 60 + now.second
            return max(1, 3600 - elapsed)
        if quota_type in (QuotaType.GPU_MINUTES_PER_DAY, QuotaType.MCP_CALLS_PER_DAY):
            elapsed = now.hour * 3600 + now.minute * 60 + now.second
            return max(1, 86400 - elapsed)
        return 0  # gauge — frees up when a slot is released, not on a timer

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(organization_id: str, amount: int) -> None:
        if not organization_id:
            raise ValueError("organization_id must be a non-empty string")
        if amount < 0:
            raise ValueError(f"amount must be >= 0, got {amount}")

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    @staticmethod
    def _upgrade_hint(tier: str) -> str:
        """An upgrade suggestion appropriate to the current tier."""
        nxt = {"free": "Pro", "pro": "Enterprise"}.get(tier.lower())
        if nxt:
            return f" Upgrade to the {nxt} tier for a higher limit."
        return ""

    def _blocked_message(
        self,
        quota_type: QuotaType,
        tier: str,
        limit: int,
        used: int,
        retry_after: Optional[int],
    ) -> str:
        """A clear block message with the reset window and an upgrade hint."""
        msg = (
            f"Quota exceeded for '{quota_type.value}' on the {tier} tier "
            f"({used}/{limit} used)."
        )
        if quota_type.is_concurrency:
            msg += " The limit frees up when a worker slot is released."
        else:
            reset = retry_after if retry_after is not None else 0
            msg += f" The quota resets at {quota_type.reset_label} (in ~{reset}s)."
        msg += self._upgrade_hint(tier)
        return msg

    # ------------------------------------------------------------------
    # check() — read-only gate
    # ------------------------------------------------------------------

    async def check(
        self,
        tier: TierQuota,
        organization_id: str,
        quota_type: Union[QuotaType, str],
        amount: int = 1,
    ) -> QuotaDecision:
        """Check whether ``amount`` units would fit without consuming them."""
        qt = _coerce_quota_type(quota_type)
        self._validate(organization_id, amount)
        limit = tier.quota(qt)

        if limit == UNLIMITED:
            return QuotaDecision(
                allowed=True,
                quota_type=qt,
                tier=tier.tier,
                limit=UNLIMITED,
                used=0,
                requested=amount,
                unlimited=True,
                message="Unlimited quota — enforcement disabled.",
            )

        # Use the raw driver (not AsyncRedisClient.get, which swallows errors
        # and returns None) so a genuine Redis outage is distinguishable from
        # an absent counter and can trigger the degraded path.
        try:
            raw = await self._redis._client.get(self._key(organization_id, qt))
            used = int(raw) if raw is not None else 0
        except Exception as exc:  # noqa: BLE001 — Redis outage must not crash
            logger.warning("quota check degraded (Redis error): %s", exc)
            return self._degraded_decision(qt, tier, limit, amount)

        allowed = used + amount <= limit
        retry_after = None if allowed else self._seconds_until_window_reset(qt)
        message = (
            ""
            if allowed
            else self._blocked_message(
                qt,
                tier.tier,
                limit,
                used,
                retry_after,
            )
        )
        return QuotaDecision(
            allowed=allowed,
            quota_type=qt,
            tier=tier.tier,
            limit=limit,
            used=used,
            requested=amount,
            message=message,
            retry_after_seconds=retry_after,
        )

    # ------------------------------------------------------------------
    # check_and_consume() — atomic gate + record
    # ------------------------------------------------------------------

    async def check_and_consume(
        self,
        tier: TierQuota,
        organization_id: str,
        quota_type: Union[QuotaType, str],
        amount: int = 1,
    ) -> QuotaDecision:
        """Atomically check and, if allowed, consume ``amount`` units.

        On a block, nothing is consumed. Backed by a single Redis Lua
        ``EVAL`` so concurrent requests cannot oversubscribe the quota.
        """
        qt = _coerce_quota_type(quota_type)
        self._validate(organization_id, amount)
        limit = tier.quota(qt)

        if limit == UNLIMITED:
            return QuotaDecision(
                allowed=True,
                quota_type=qt,
                tier=tier.tier,
                limit=UNLIMITED,
                used=0,
                requested=amount,
                unlimited=True,
                message="Unlimited quota — enforcement disabled.",
            )

        key = self._key(organization_id, qt)
        script = _LUA_GAUGE_ACQUIRE if qt.is_concurrency else _LUA_WINDOWED_CONSUME
        ttl = qt.window_seconds

        try:
            result = await self._redis._client.eval(
                script,
                1,
                key,
                amount,
                limit,
                ttl,
            )
            allowed = bool(result[0])
            used = int(result[1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("quota consume degraded (Redis error): %s", exc)
            return self._degraded_decision(qt, tier, limit, amount)

        retry_after = None if allowed else self._seconds_until_window_reset(qt)
        message = (
            ""
            if allowed
            else self._blocked_message(
                qt,
                tier.tier,
                limit,
                used,
                retry_after,
            )
        )
        return QuotaDecision(
            allowed=allowed,
            quota_type=qt,
            tier=tier.tier,
            limit=limit,
            used=used,
            requested=amount,
            message=message,
            retry_after_seconds=retry_after,
        )

    # ------------------------------------------------------------------
    # enforce() — raises on block
    # ------------------------------------------------------------------

    async def enforce(
        self,
        tier: TierQuota,
        organization_id: str,
        quota_type: Union[QuotaType, str],
        amount: int = 1,
    ) -> QuotaDecision:
        """Atomically consume the quota or raise :class:`QuotaExceededError`."""
        decision = await self.check_and_consume(
            tier,
            organization_id,
            quota_type,
            amount,
        )
        if not decision.allowed and not decision.degraded:
            raise QuotaExceededError(decision)
        return decision

    # ------------------------------------------------------------------
    # consume_partial() — graceful mid-operation exhaustion
    # ------------------------------------------------------------------

    async def consume_partial(
        self,
        tier: TierQuota,
        organization_id: str,
        quota_type: Union[QuotaType, str],
        amount: int = 1,
    ) -> PartialConsumption:
        """Consume up to ``amount`` units, granting whatever headroom remains.

        For long-running operations (e.g. token streaming) so the caller can
        stop with a partial result instead of crashing when the quota runs
        out mid-flight.
        """
        qt = _coerce_quota_type(quota_type)
        self._validate(organization_id, amount)
        limit = tier.quota(qt)

        if limit == UNLIMITED:
            return PartialConsumption(
                quota_type=qt,
                tier=tier.tier,
                requested=amount,
                granted=amount,
                limit=UNLIMITED,
                used=0,
            )

        key = self._key(organization_id, qt)
        ttl = qt.window_seconds or 86400

        try:
            result = await self._redis._client.eval(
                _LUA_PARTIAL_CONSUME,
                1,
                key,
                amount,
                limit,
                ttl,
            )
            granted = int(result[1])
            used = int(result[2])
        except Exception as exc:  # noqa: BLE001
            logger.warning("partial consume degraded (Redis error): %s", exc)
            granted = amount if self._fail_open else 0
            return PartialConsumption(
                quota_type=qt,
                tier=tier.tier,
                requested=amount,
                granted=granted,
                limit=limit,
                used=0,
                degraded=True,
            )

        return PartialConsumption(
            quota_type=qt,
            tier=tier.tier,
            requested=amount,
            granted=granted,
            limit=limit,
            used=used,
        )

    # ------------------------------------------------------------------
    # release() — return a concurrency-gauge slot
    # ------------------------------------------------------------------

    async def release(
        self,
        tier: TierQuota,
        organization_id: str,
        quota_type: Union[QuotaType, str],
        amount: int = 1,
    ) -> bool:
        """Release a concurrency-gauge slot (e.g. a finished Ray worker).

        A no-op for windowed quotas (they decay on their own TTL) and for
        unlimited tiers. Clamps the gauge at zero so a double-release cannot
        push it negative. Returns ``True`` when the slot was released (or
        nothing needed releasing), ``False`` on a Redis error.
        """
        qt = _coerce_quota_type(quota_type)
        self._validate(organization_id, amount)

        if not qt.is_concurrency:
            return False  # windowed quotas are not released, they expire

        if tier.is_unlimited(qt):
            return True  # nothing tracked for an unlimited tier

        key = self._key(organization_id, qt)
        try:
            remaining = await self._redis._client.decrby(key, amount)
            if remaining is not None and remaining < 0:
                # Double release — clamp the gauge back to zero.
                await self._redis._client.set(key, 0)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("quota release failed (Redis error): %s", exc)
            return False

    # ------------------------------------------------------------------
    # get_usage() — introspection
    # ------------------------------------------------------------------

    async def get_usage(
        self,
        tier: TierQuota,
        organization_id: str,
    ) -> Dict[QuotaType, QuotaDecision]:
        """Return current usage for all four quotas of an org.

        Each value is a :class:`QuotaDecision` with ``requested=0`` — a pure
        snapshot, nothing consumed.
        """
        self._validate(organization_id, 0)
        quota_types = list(QuotaType)
        keys = [self._key(organization_id, qt) for qt in quota_types]

        try:
            raw_values = await self._redis._client.mget(keys)
            if raw_values is None:
                raw_values = [None] * len(quota_types)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_usage degraded (Redis error): %s", exc)
            raw_values = [None] * len(quota_types)

        usage: Dict[QuotaType, QuotaDecision] = {}
        for qt, raw in zip(quota_types, raw_values):
            limit = tier.quota(qt)
            used = int(raw) if raw is not None else 0
            usage[qt] = QuotaDecision(
                allowed=limit == UNLIMITED or used <= limit,
                quota_type=qt,
                tier=tier.tier,
                limit=limit,
                used=used,
                requested=0,
                unlimited=limit == UNLIMITED,
            )
        return usage

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _degraded_decision(
        self,
        quota_type: QuotaType,
        tier: TierQuota,
        limit: int,
        amount: int,
    ) -> QuotaDecision:
        """Build a decision for when Redis is unavailable.

        ``fail_open`` allows the request, ``fail_closed`` blocks it; either
        way the decision is flagged ``degraded`` for downstream observability.
        """
        return QuotaDecision(
            allowed=self._fail_open,
            quota_type=quota_type,
            tier=tier.tier,
            limit=limit,
            used=0,
            requested=amount,
            degraded=True,
            message=(
                "Quota backend unavailable — "
                + (
                    "allowing request (fail-open)."
                    if self._fail_open
                    else "blocking request (fail-closed)."
                )
            ),
        )
