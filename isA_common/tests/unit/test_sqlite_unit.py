"""Unit tests for AsyncSQLiteClient — #119."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# L1 — Pure helper functions (no I/O)
# ============================================================================


class TestConvertPgPlaceholders:
    """_convert_pg_placeholders converts $N to ?."""

    def test_single_placeholder(self):
        from isa_common.async_sqlite_client import _convert_pg_placeholders
        assert _convert_pg_placeholders("SELECT * FROM t WHERE id = $1") == \
            "SELECT * FROM t WHERE id = ?"

    def test_multiple_placeholders(self):
        from isa_common.async_sqlite_client import _convert_pg_placeholders
        result = _convert_pg_placeholders(
            "INSERT INTO t (a, b, c) VALUES ($1, $2, $3)"
        )
        assert result == "INSERT INTO t (a, b, c) VALUES (?, ?, ?)"

    def test_no_placeholders(self):
        from isa_common.async_sqlite_client import _convert_pg_placeholders
        sql = "SELECT * FROM t"
        assert _convert_pg_placeholders(sql) == sql


class TestConvertPgSyntax:
    """_convert_pg_syntax handles ILIKE → LIKE."""

    def test_ilike_to_like(self):
        from isa_common.async_sqlite_client import _convert_pg_syntax
        assert "LIKE" in _convert_pg_syntax("SELECT * FROM t WHERE name ILIKE '%foo%'")
        assert "ILIKE" not in _convert_pg_syntax("SELECT * FROM t WHERE name ILIKE '%foo%'")

    def test_preserves_regular_like(self):
        from isa_common.async_sqlite_client import _convert_pg_syntax
        sql = "SELECT * FROM t WHERE name LIKE '%foo%'"
        assert _convert_pg_syntax(sql) == sql


class TestSerializeValue:
    """_serialize_value converts dicts/lists to JSON strings."""

    def test_dict(self):
        from isa_common.async_sqlite_client import _serialize_value
        result = _serialize_value({"key": "value"})
        assert result == '{"key": "value"}'

    def test_list(self):
        from isa_common.async_sqlite_client import _serialize_value
        result = _serialize_value([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_scalar_passthrough(self):
        from isa_common.async_sqlite_client import _serialize_value
        assert _serialize_value(42) == 42
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(None) is None


class TestDeserializeRow:
    """_deserialize_row converts SQLite rows to dicts with JSON parsing."""

    def test_basic_row(self):
        from isa_common.async_sqlite_client import _deserialize_row
        row = ("alice", 30)
        description = [("name",), ("age",)]
        result = _deserialize_row(row, description)
        assert result == {"name": "alice", "age": 30}

    def test_json_string_value(self):
        from isa_common.async_sqlite_client import _deserialize_row
        row = ('{"key": "value"}',)
        description = [("data",)]
        result = _deserialize_row(row, description)
        assert result == {"data": {"key": "value"}}

    def test_json_array_value(self):
        from isa_common.async_sqlite_client import _deserialize_row
        row = ('[1, 2, 3]',)
        description = [("tags",)]
        result = _deserialize_row(row, description)
        assert result == {"tags": [1, 2, 3]}

    def test_non_json_string(self):
        from isa_common.async_sqlite_client import _deserialize_row
        row = ("hello world",)
        description = [("name",)]
        result = _deserialize_row(row, description)
        assert result == {"name": "hello world"}


# ============================================================================
# L2 — Component tests (mocked aiosqlite)
# ============================================================================


class TestSQLiteClientInit:
    """AsyncSQLiteClient initialization."""

    def test_default_init(self, tmp_path):
        from isa_common import AsyncSQLiteClient
        client = AsyncSQLiteClient(
            database="test.db", db_path=str(tmp_path), lazy_connect=True
        )
        assert client._database == "test.db"
        assert client._db_file == tmp_path / "test.db"

    def test_default_database_name(self, tmp_path):
        from isa_common import AsyncSQLiteClient
        client = AsyncSQLiteClient(db_path=str(tmp_path), lazy_connect=True)
        assert client._database == "isa_mcp.db"


class TestSQLiteClientDisconnect:
    """_disconnect closes connection."""

    async def test_disconnect_closes_conn(self, sqlite_client):
        mock_conn = AsyncMock()
        sqlite_client._conn = mock_conn
        await sqlite_client._disconnect()
        mock_conn.close.assert_awaited_once()
        assert sqlite_client._conn is None

    async def test_disconnect_noop_when_no_conn(self, sqlite_client):
        sqlite_client._conn = None
        await sqlite_client._disconnect()  # Should not raise


class TestSQLiteClientQuery:
    """query() executes SELECT and returns rows."""

    async def test_query_returns_rows(self, sqlite_client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall = AsyncMock(return_value=[("alice", 30)])
        mock_cursor.description = [("name",), ("age",)]
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        sqlite_client._conn.execute = MagicMock(return_value=mock_cursor)

        result = await sqlite_client.query("SELECT * FROM users WHERE id = $1", [1])
        assert result == [{"name": "alice", "age": 30}]

    async def test_query_empty_result(self, sqlite_client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_cursor.description = [("name",)]
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        sqlite_client._conn.execute = MagicMock(return_value=mock_cursor)

        result = await sqlite_client.query("SELECT * FROM users")
        assert result == []

    async def test_query_with_schema(self, sqlite_client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_cursor.description = [("id",)]
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        sqlite_client._conn.execute = MagicMock(return_value=mock_cursor)

        await sqlite_client.query("SELECT * FROM myschema.users", schema="myschema")
        # Verify the SQL was converted: myschema.users -> myschema_users
        call_args = sqlite_client._conn.execute.call_args
        assert "myschema_" in call_args[0][0]


class TestSQLiteClientExecute:
    """execute() runs INSERT/UPDATE/DELETE."""

    async def test_execute_returns_rowcount(self, sqlite_client):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        sqlite_client._conn.execute = MagicMock(return_value=mock_cursor)
        sqlite_client._conn.commit = AsyncMock()

        result = await sqlite_client.execute(
            "DELETE FROM users WHERE active = $1", [False]
        )
        assert result == 3


class TestSQLiteClientInsertInto:
    """insert_into() batch inserts rows."""

    async def test_insert_empty_rows(self, sqlite_client):
        result = await sqlite_client.insert_into("users", [])
        assert result == 0

    async def test_insert_rows(self, sqlite_client):
        sqlite_client._conn.execute = AsyncMock()
        sqlite_client._conn.commit = AsyncMock()

        rows = [{"name": "alice"}, {"name": "bob"}]
        result = await sqlite_client.insert_into("users", rows)
        assert result == 2


class TestSQLiteClientHealthCheck:
    """health_check() returns status dict."""

    async def test_health_check_healthy(self, sqlite_client):
        mock_cursor = MagicMock()
        mock_cursor.fetchone = AsyncMock(return_value=("3.40.0",))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        sqlite_client._conn.execute = MagicMock(return_value=mock_cursor)
        # Mock _db_file existence
        sqlite_client._db_file = MagicMock()
        sqlite_client._db_file.exists.return_value = True
        sqlite_client._db_file.stat.return_value = MagicMock(st_size=4096)

        result = await sqlite_client.health_check()
        assert result["healthy"] is True
        assert result["version"] == "3.40.0"


class TestSQLiteClientExecuteScript:
    """execute_script() runs multi-statement SQL."""

    async def test_execute_script_converts_types(self, sqlite_client):
        sqlite_client._conn.executescript = AsyncMock()

        script = "CREATE TABLE t (id SERIAL, data JSONB, ts TIMESTAMPTZ)"
        result = await sqlite_client.execute_script(script)
        assert result is True

        called_sql = sqlite_client._conn.executescript.call_args[0][0]
        assert "INTEGER" in called_sql
        assert "TEXT" in called_sql
        assert "SERIAL" not in called_sql
        assert "JSONB" not in called_sql
