"""
Unit tests for IdempotencyChecker — all three backends.

L1 Unit: memory backend (pure logic, no I/O)
L2 Component: redis and postgres backends (mocked clients)
"""

import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from isa_common.events.base_event_subscriber import IdempotencyChecker


# =============================================================================
# L1 Unit — Memory backend (no I/O)
# =============================================================================

class TestIdempotencyMemoryBackend:
    """Tests for the in-memory idempotency backend."""

    def setup_method(self):
        self.checker = IdempotencyChecker(storage_backend="memory")

    @pytest.mark.asyncio
    async def test_new_event_not_processed(self):
        assert await self.checker.is_processed("evt-001") is False

    @pytest.mark.asyncio
    async def test_mark_then_check(self):
        await self.checker.mark_processed("evt-001")
        assert await self.checker.is_processed("evt-001") is True

    @pytest.mark.asyncio
    async def test_different_events_independent(self):
        await self.checker.mark_processed("evt-001")
        assert await self.checker.is_processed("evt-002") is False

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """When cache exceeds max size, oldest entry is evicted."""
        self.checker._max_cache_size = 3
        await self.checker.mark_processed("evt-001")
        await self.checker.mark_processed("evt-002")
        await self.checker.mark_processed("evt-003")
        # This should evict evt-001
        await self.checker.mark_processed("evt-004")
        assert await self.checker.is_processed("evt-001") is False
        assert await self.checker.is_processed("evt-002") is True
        assert await self.checker.is_processed("evt-004") is True

    @pytest.mark.asyncio
    async def test_mark_stores_utc_timestamp(self):
        await self.checker.mark_processed("evt-001")
        ts = self.checker._memory_cache["evt-001"]
        assert ts.tzinfo is not None  # timezone-aware
        assert ts.tzinfo == timezone.utc

    @pytest.mark.asyncio
    async def test_unknown_backend_returns_false(self):
        checker = IdempotencyChecker(storage_backend="unknown")
        assert await checker.is_processed("evt-001") is False


# =============================================================================
# L2 Component — Redis backend (mocked client)
# =============================================================================

class TestIdempotencyRedisBackend:
    """Tests for the Redis idempotency backend with mocked AsyncRedisClient."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        self.mock_redis = AsyncMock()
        self.checker = IdempotencyChecker(
            storage_backend="redis",
            redis_client=self.mock_redis,
            ttl_seconds=3600,
        )

    @pytest.mark.asyncio
    async def test_is_processed_calls_exists(self):
        self.mock_redis.exists.return_value = True
        result = await self.checker.is_processed("evt-001")
        assert result is True
        self.mock_redis.exists.assert_awaited_once_with("isa:idempotency:evt-001")

    @pytest.mark.asyncio
    async def test_not_processed_returns_false(self):
        self.mock_redis.exists.return_value = False
        result = await self.checker.is_processed("evt-001")
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_processed_sets_with_ttl(self):
        await self.checker.mark_processed("evt-001", result={"ok": True})
        self.mock_redis.set.assert_awaited_once()
        call_args = self.mock_redis.set.call_args
        key = call_args[0][0]
        value = call_args[0][1]
        ttl = call_args[1]["ex"]

        assert key == "isa:idempotency:evt-001"
        assert ttl == 3600
        parsed = json.loads(value)
        assert "processed_at" in parsed

    @pytest.mark.asyncio
    async def test_mark_processed_without_result(self):
        await self.checker.mark_processed("evt-001")
        call_args = self.mock_redis.set.call_args
        value = json.loads(call_args[0][1])
        assert value["result"] is None


# =============================================================================
# L2 Component — PostgreSQL backend (mocked client)
# =============================================================================

class TestIdempotencyPostgresBackend:
    """Tests for the PostgreSQL idempotency backend with mocked AsyncPostgresClient."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        self.mock_pg = AsyncMock()
        self.checker = IdempotencyChecker(
            storage_backend="postgres",
            postgres_client=self.mock_pg,
        )

    @pytest.mark.asyncio
    async def test_ensure_table_created_on_first_call(self):
        self.mock_pg.query_one.return_value = None
        await self.checker.is_processed("evt-001")
        # Should have called execute twice: CREATE TABLE + CREATE INDEX
        assert self.mock_pg.execute.await_count == 2
        create_call = self.mock_pg.execute.call_args_list[0][0][0]
        assert "CREATE TABLE IF NOT EXISTS event_idempotency" in create_call

    @pytest.mark.asyncio
    async def test_table_only_created_once(self):
        self.mock_pg.query_one.return_value = None
        await self.checker.is_processed("evt-001")
        await self.checker.is_processed("evt-002")
        # CREATE TABLE + CREATE INDEX only on first call
        # Then two query_one calls
        assert self.mock_pg.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_is_processed_true_when_row_exists(self):
        self.mock_pg.query_one.return_value = {"1": 1}
        result = await self.checker.is_processed("evt-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_processed_false_when_no_row(self):
        self.mock_pg.query_one.return_value = None
        result = await self.checker.is_processed("evt-001")
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_processed_inserts_row(self):
        # First call triggers table creation (2 execute calls)
        # mark_processed triggers a 3rd execute call
        await self.checker.mark_processed("evt-001", result={"status": "ok"})
        # 2 (table creation) + 1 (insert)
        assert self.mock_pg.execute.await_count == 3
        insert_call = self.mock_pg.execute.call_args_list[2]
        sql = insert_call[0][0]
        assert "INSERT INTO event_idempotency" in sql
        assert "ON CONFLICT (event_id) DO NOTHING" in sql
        event_id = insert_call[0][1]
        assert event_id == "evt-001"

    @pytest.mark.asyncio
    async def test_mark_processed_with_none_result(self):
        await self.checker.mark_processed("evt-001")
        insert_call = self.mock_pg.execute.call_args_list[2]
        result_json = insert_call[0][3]
        assert result_json is None
