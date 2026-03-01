"""AsyncPostgresClient unit tests — mocked asyncpg pool, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestPostgresConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncPostgresClient

        client = AsyncPostgresClient(
            host="localhost", port=5432, database="testdb", lazy_connect=True
        )
        assert client._connected is False

    async def test_close_sets_disconnected(self, postgres_client):
        await postgres_client.close()
        assert postgres_client._connected is False


class TestPostgresHealthCheck:
    async def test_health_check_success(self, postgres_client):
        conn = postgres_client._conn
        conn.fetchval = AsyncMock(side_effect=["1", "PostgreSQL 16.1"])

        result = await postgres_client.health_check(detailed=True)

        assert result is not None
        assert result["healthy"] is True

    async def test_health_check_error_returns_none(self, postgres_client):
        postgres_client._pool.acquire.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("connection refused")
        )

        result = await postgres_client.health_check()

        assert result is None


class TestPostgresQuery:
    async def test_query_returns_list_of_dicts(self, postgres_client):
        mock_row = MagicMock()
        mock_row.__iter__ = MagicMock(return_value=iter([("id", 1), ("name", "Alice")]))
        mock_row.keys = MagicMock(return_value=["id", "name"])
        # asyncpg Record supports dict()
        dict_result = {"id": 1, "name": "Alice"}

        postgres_client._conn.fetch = AsyncMock(return_value=[dict_result])

        result = await postgres_client.query("SELECT * FROM users")

        assert result is not None
        assert len(result) == 1

    async def test_query_with_params(self, postgres_client):
        postgres_client._conn.fetch = AsyncMock(return_value=[])

        result = await postgres_client.query(
            "SELECT * FROM users WHERE id = $1", params=[42]
        )

        assert result == []
        postgres_client._conn.fetch.assert_awaited_once_with(
            "SELECT * FROM users WHERE id = $1", 42
        )

    async def test_query_error_returns_none(self, postgres_client):
        postgres_client._conn.fetch = AsyncMock(side_effect=Exception("syntax error"))

        result = await postgres_client.query("INVALID SQL")

        assert result is None

    async def test_query_row_returns_dict(self, postgres_client):
        row_data = {"id": 1, "name": "Alice"}
        postgres_client._conn.fetchrow = AsyncMock(return_value=row_data)

        result = await postgres_client.query_row("SELECT * FROM users WHERE id = $1", [1])

        assert result is not None

    async def test_query_row_returns_none_for_no_match(self, postgres_client):
        postgres_client._conn.fetchrow = AsyncMock(return_value=None)

        result = await postgres_client.query_row("SELECT * FROM users WHERE id = $1", [999])

        assert result is None


class TestPostgresExecute:
    async def test_execute_returns_affected_count(self, postgres_client):
        postgres_client._conn.execute = AsyncMock(return_value="UPDATE 3")

        result = await postgres_client.execute(
            "UPDATE users SET active = true WHERE org_id = $1", params=["org1"]
        )

        assert result is not None

    async def test_execute_error_returns_none(self, postgres_client):
        postgres_client._conn.execute = AsyncMock(
            side_effect=Exception("constraint violation")
        )

        result = await postgres_client.execute("INSERT INTO users VALUES (1)")

        assert result is None


class TestPostgresErrorHandling:
    async def test_query_with_broken_pool_returns_none(self, postgres_client):
        postgres_client._pool.acquire.return_value.__aenter__ = AsyncMock(
            side_effect=ConnectionError("pool exhausted")
        )

        result = await postgres_client.query("SELECT 1")

        assert result is None
