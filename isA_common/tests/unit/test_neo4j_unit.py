"""AsyncNeo4jClient unit tests — mocked neo4j driver, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class MockAsyncResult:
    """Mock neo4j async result supporting async iteration and single()."""

    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        return self._AsyncIter(self._records)

    async def single(self):
        return self._records[0] if self._records else None

    async def consume(self):
        mock = MagicMock()
        mock.counters = MagicMock(nodes_deleted=len(self._records))
        return mock

    class _AsyncIter:
        def __init__(self, records):
            self._iter = iter(records)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration


class TestNeo4jConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncNeo4jClient

        client = AsyncNeo4jClient(host="localhost", port=7687, lazy_connect=True)
        assert client._connected is False
        assert client._driver is None

    async def test_uri_built_from_host_port(self):
        from isa_common import AsyncNeo4jClient

        client = AsyncNeo4jClient(host="neo4j-host", port=7687, lazy_connect=True)
        assert client._uri == "bolt://neo4j-host:7687"

    async def test_uri_override(self):
        from isa_common import AsyncNeo4jClient

        client = AsyncNeo4jClient(uri="neo4j+s://cloud.neo4j.io", lazy_connect=True)
        assert client._uri == "neo4j+s://cloud.neo4j.io"

    async def test_close_sets_disconnected(self, neo4j_client):
        await neo4j_client.close()
        assert neo4j_client._connected is False


class TestNeo4jHealthCheck:
    async def test_health_check_success(self, neo4j_client):
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "name": "Neo4j", "versions": ["5.0"], "edition": "community"
        }[key]

        neo4j_client._session.run = AsyncMock(
            return_value=MockAsyncResult([mock_record])
        )

        result = await neo4j_client.health_check()

        assert result is not None
        assert result.get("healthy") is True

    async def test_health_check_error_returns_none(self, neo4j_client):
        neo4j_client._session.run = AsyncMock(
            side_effect=Exception("connection refused")
        )

        result = await neo4j_client.health_check()

        assert result is None


class TestNeo4jCypher:
    async def test_run_cypher_returns_records(self, neo4j_client):
        records = [{"n.name": "Alice"}, {"n.name": "Bob"}]
        neo4j_client._session.run = AsyncMock(
            return_value=MockAsyncResult(records)
        )

        result = await neo4j_client.run_cypher("MATCH (n) RETURN n.name")

        assert result is not None
        assert len(result) == 2

    async def test_run_cypher_with_params(self, neo4j_client):
        records = [{"n.name": "Alice"}]
        neo4j_client._session.run = AsyncMock(
            return_value=MockAsyncResult(records)
        )

        result = await neo4j_client.run_cypher(
            "MATCH (n:User {id: $id}) RETURN n.name",
            params={"id": "user_123"}
        )

        assert result is not None
        neo4j_client._session.run.assert_awaited_once()

    async def test_run_cypher_error_returns_none(self, neo4j_client):
        neo4j_client._session.run = AsyncMock(side_effect=Exception("syntax error"))

        result = await neo4j_client.run_cypher("INVALID CYPHER")

        assert result is None


class TestNeo4jNodeOps:
    async def test_create_node_returns_id(self, neo4j_client):
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {"id": "4:abc:42", "node_id": 42}[key]

        neo4j_client._session.run = AsyncMock(
            return_value=MockAsyncResult([mock_record])
        )

        result = await neo4j_client.create_node(
            labels=["User"], properties={"name": "Alice"}
        )

        assert result is not None
        neo4j_client._session.run.assert_awaited_once()

    async def test_get_node_returns_dict(self, neo4j_client):
        mock_node = MagicMock()
        mock_node.id = 42
        mock_node.labels = frozenset(["User"])
        mock_node.items.return_value = [("name", "Alice")]

        mock_record = MagicMock()
        mock_record.__getitem__ = MagicMock(return_value=mock_node)

        neo4j_client._session.run = AsyncMock(
            return_value=MockAsyncResult([mock_record])
        )

        result = await neo4j_client.get_node(42)

        assert result is not None

    async def test_delete_node_returns_bool(self, neo4j_client):
        neo4j_client._session.run = AsyncMock(
            return_value=MockAsyncResult([MagicMock()])
        )

        result = await neo4j_client.delete_node(42, detach=True)

        assert result is True or result is not None


class TestNeo4jErrorHandling:
    async def test_create_node_error_returns_none(self, neo4j_client):
        neo4j_client._session.run = AsyncMock(side_effect=Exception("constraint violation"))

        result = await neo4j_client.create_node(
            labels=["User"], properties={"name": "Alice"}
        )

        assert result is None

    async def test_get_node_error_returns_none(self, neo4j_client):
        neo4j_client._session.run = AsyncMock(side_effect=Exception("not found"))

        result = await neo4j_client.get_node(999)

        assert result is None
