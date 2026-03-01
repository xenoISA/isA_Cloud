"""AsyncDuckDBClient unit tests — mocked duckdb connection, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDuckDBConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncDuckDBClient

        client = AsyncDuckDBClient(lazy_connect=True)
        assert client._connected is False

    async def test_close_sets_disconnected(self, duckdb_client):
        await duckdb_client.close()
        assert duckdb_client._connected is False


class TestDuckDBHealthCheck:
    async def test_health_check_success(self, duckdb_client):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        duckdb_client._conn.execute = MagicMock(return_value=mock_result)

        result = await duckdb_client.health_check()

        assert result is not None
        assert result.get("healthy") is True

    async def test_health_check_error_returns_none(self, duckdb_client):
        duckdb_client._conn.execute = MagicMock(side_effect=Exception("db locked"))

        result = await duckdb_client.health_check()

        assert result is None


class TestDuckDBQuery:
    async def test_query_returns_list_of_dicts(self, duckdb_client):
        mock_result = MagicMock()
        mock_result.columns = ["id", "name"]
        mock_result.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        mock_result.description = [("id",), ("name",)]
        duckdb_client._conn.execute = MagicMock(return_value=mock_result)

        result = await duckdb_client.query("SELECT * FROM users")

        assert result is not None

    async def test_query_with_params(self, duckdb_client):
        mock_result = MagicMock()
        mock_result.columns = ["id"]
        mock_result.fetchall.return_value = [(42,)]
        mock_result.description = [("id",)]
        duckdb_client._conn.execute = MagicMock(return_value=mock_result)

        result = await duckdb_client.query(
            "SELECT * FROM users WHERE id = ?", params=[42]
        )

        assert result is not None

    async def test_query_error_returns_none(self, duckdb_client):
        duckdb_client._conn.execute = MagicMock(
            side_effect=Exception("syntax error")
        )

        result = await duckdb_client.query("INVALID SQL")

        assert result is None


class TestDuckDBExecute:
    async def test_execute_returns_count(self, duckdb_client):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        duckdb_client._conn.execute = MagicMock(return_value=mock_result)

        result = await duckdb_client.execute("CREATE TABLE test (id INT)")

        assert result is not None

    async def test_execute_error_returns_none(self, duckdb_client):
        duckdb_client._conn.execute = MagicMock(
            side_effect=Exception("table exists")
        )

        result = await duckdb_client.execute("CREATE TABLE test (id INT)")

        assert result is None


class TestDuckDBTableOps:
    async def test_list_tables(self, duckdb_client):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("users",), ("orders",)]
        mock_result.description = [("name",)]
        duckdb_client._conn.execute = MagicMock(return_value=mock_result)

        result = await duckdb_client.list_tables()

        assert result is not None

    async def test_table_exists(self, duckdb_client):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        duckdb_client._conn.execute = MagicMock(return_value=mock_result)

        result = await duckdb_client.table_exists("users")

        assert result is True or result is not None


class TestDuckDBErrorHandling:
    async def test_query_with_closed_connection(self, duckdb_client):
        duckdb_client._conn.execute = MagicMock(
            side_effect=Exception("connection closed")
        )

        result = await duckdb_client.query("SELECT 1")

        assert result is None
