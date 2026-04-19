"""AsyncFalkorClient unit tests — mocked falkordb driver, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestFalkorConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncFalkorClient

        client = AsyncFalkorClient(host="localhost", port=6379, lazy_connect=True)
        assert client._connected is False

    async def test_close_sets_disconnected(self, falkor_client):
        await falkor_client.close()
        assert falkor_client._connected is False

    def test_default_graph_name_from_env(self, monkeypatch):
        from isa_common import AsyncFalkorClient

        monkeypatch.setenv("FALKOR_GRAPH", "custom_graph")
        client = AsyncFalkorClient(host="localhost", port=6379, lazy_connect=True)
        assert client._graph_name == "custom_graph"


class TestFalkorHealthCheck:
    async def test_health_check_success(self, falkor_client):
        result = await falkor_client.health_check()

        assert result is not None
        assert result["healthy"] is True
        assert result["graph"] == "test_graph"

    async def test_health_check_error_returns_none(self, falkor_client):
        falkor_client._db.connection.ping = AsyncMock(side_effect=Exception("connection refused"))

        result = await falkor_client.health_check()

        assert result is None


class TestFalkorQuery:
    async def test_query_passes_params(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = [["alice"]]
        mock_result.header = [[1, "name"]]
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        rows = await falkor_client.query(
            "MATCH (n:User {id: $id}) RETURN n.name AS name",
            params={"id": 42},
        )

        assert rows == [{"name": "alice"}]
        call_kwargs = falkor_client._graph.query.await_args.kwargs
        assert call_kwargs["params"] == {"id": 42}

    async def test_query_routes_read_only(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.ro_query = AsyncMock(return_value=mock_result)

        await falkor_client.query("MATCH (n) RETURN n", read_only=True)

        falkor_client._graph.ro_query.assert_awaited_once()
        falkor_client._graph.query.assert_not_called()

    async def test_query_normalizes_node_objects(self, falkor_client):
        node = MagicMock()
        node.id = 1
        node.labels = ["User"]
        node.properties = {"name": "alice"}
        mock_result = MagicMock()
        mock_result.result_set = [[node]]
        mock_result.header = [[1, "n"]]
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        rows = await falkor_client.query("MATCH (n:User) RETURN n")

        assert rows == [
            {"n": {"id": 1, "labels": ["User"], "properties": {"name": "alice"}}}
        ]

    async def test_query_returns_none_on_unrecoverable_error(self, falkor_client):
        falkor_client._graph.query = AsyncMock(side_effect=ValueError("syntax error"))

        result = await falkor_client.query("INVALID")

        assert result is None

    async def test_query_retries_on_transient_then_succeeds(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = [[1]]
        mock_result.header = [[1, "v"]]
        falkor_client._retry_min_wait = 0.0
        falkor_client._retry_max_wait = 0.0
        falkor_client._graph.query = AsyncMock(
            side_effect=[ConnectionError("connection reset by peer"), mock_result]
        )

        rows = await falkor_client.query("RETURN 1 AS v")

        assert rows == [{"v": 1}]
        assert falkor_client._graph.query.await_count == 2


class TestFalkorVectorQuery:
    async def test_query_vector_builds_cypher(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.ro_query = AsyncMock(return_value=mock_result)

        await falkor_client.query_vector(
            label="Skill", attribute="embedding", vector=[0.1, 0.2, 0.3], k=5
        )

        cypher = falkor_client._graph.ro_query.await_args.args[0]
        params = falkor_client._graph.ro_query.await_args.kwargs["params"]
        assert "db.idx.vector.queryNodes" in cypher
        assert params == {
            "label": "Skill",
            "attribute": "embedding",
            "k": 5,
            "vector": [0.1, 0.2, 0.3],
        }


class TestFalkorBulkCreate:
    async def test_bulk_create_uses_unwind(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        total = await falkor_client.bulk_create_nodes("Skill", rows)

        assert total == 2
        cypher = falkor_client._graph.query.await_args.args[0]
        assert "UNWIND $rows" in cypher
        assert "CREATE (n:Skill)" in cypher

    async def test_bulk_create_with_merge(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        rows = [{"id": "x", "name": "a"}]
        await falkor_client.bulk_create_nodes("Skill", rows, merge_on="id")

        cypher = falkor_client._graph.query.await_args.args[0]
        assert "MERGE (n:Skill { id: row.id })" in cypher
        assert "SET n += row" in cypher

    async def test_bulk_create_rejects_invalid_label(self, falkor_client):
        with pytest.raises(ValueError):
            await falkor_client.bulk_create_nodes("Bad Label", [{"x": 1}])

    async def test_bulk_create_rejects_invalid_merge_on(self, falkor_client):
        with pytest.raises(ValueError):
            await falkor_client.bulk_create_nodes("Skill", [{"x": 1}], merge_on="bad name")

    async def test_bulk_create_empty_returns_zero(self, falkor_client):
        result = await falkor_client.bulk_create_nodes("Skill", [])
        assert result == 0

    async def test_bulk_create_batches(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        rows = [{"id": i} for i in range(7)]
        total = await falkor_client.bulk_create_nodes("Skill", rows, batch_size=3)

        assert total == 7
        # 7 rows in batches of 3 -> ceil(7/3) = 3 calls
        assert falkor_client._graph.query.await_count == 3


class TestFalkorCreateIndex:
    async def test_create_vector_index(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        ok = await falkor_client.create_index(
            "Skill", "embedding", kind="vector", dim=384, metric="cosine"
        )

        assert ok is True
        cypher = falkor_client._graph.query.await_args.args[0]
        assert "CREATE VECTOR INDEX FOR (n:Skill) ON (n.embedding)" in cypher
        assert "dimension: 384" in cypher
        assert "similarityFunction: 'cosine'" in cypher

    async def test_create_range_index(self, falkor_client):
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_result.header = []
        falkor_client._graph.query = AsyncMock(return_value=mock_result)

        ok = await falkor_client.create_index("Skill", "id", kind="range")

        assert ok is True
        cypher = falkor_client._graph.query.await_args.args[0]
        assert "CREATE INDEX FOR (n:Skill) ON (n.id)" in cypher

    async def test_vector_index_requires_dim(self, falkor_client):
        result = await falkor_client.create_index("Skill", "embedding", kind="vector")
        assert result is None

    async def test_invalid_label_raises(self, falkor_client):
        with pytest.raises(ValueError):
            await falkor_client.create_index("Bad Label", "embedding", kind="range")


class TestFalkorListGraphs:
    async def test_list_graphs(self, falkor_client):
        result = await falkor_client.list_graphs()
        assert result == ["test_graph"]

    async def test_list_graphs_returns_empty_on_error(self, falkor_client):
        falkor_client._db.list_graphs = AsyncMock(side_effect=Exception("nope"))
        result = await falkor_client.list_graphs()
        assert result == []
