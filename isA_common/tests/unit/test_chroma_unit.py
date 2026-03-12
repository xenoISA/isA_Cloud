"""Unit tests for AsyncChromaClient — #119."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# L1 — Pure helper functions
# ============================================================================


class TestFlattenPayload:
    """_flatten_payload converts nested dicts for ChromaDB metadata."""

    def _make_client(self, tmp_path):
        from isa_common import AsyncChromaClient
        return AsyncChromaClient(
            persist_directory=str(tmp_path), lazy_connect=True
        )

    def test_primitives_pass_through(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._flatten_payload({"name": "test", "count": 42, "active": True})
        assert result == {"name": "test", "count": 42, "active": True}

    def test_dict_serialized_as_json(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._flatten_payload({"nested": {"a": 1}})
        assert result["nested"] == '{"a": 1}'

    def test_list_serialized_as_json(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._flatten_payload({"tags": ["a", "b"]})
        assert result["tags"] == '["a", "b"]'

    def test_none_becomes_empty_string(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._flatten_payload({"field": None})
        assert result["field"] == ""


class TestUnflattenPayload:
    """_unflatten_payload parses JSON strings back to dicts/lists."""

    def _make_client(self, tmp_path):
        from isa_common import AsyncChromaClient
        return AsyncChromaClient(
            persist_directory=str(tmp_path), lazy_connect=True
        )

    def test_json_dict_parsed(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._unflatten_payload({"nested": '{"a": 1}'})
        assert result["nested"] == {"a": 1}

    def test_json_list_parsed(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._unflatten_payload({"tags": '["a", "b"]'})
        assert result["tags"] == ["a", "b"]

    def test_plain_string_preserved(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._unflatten_payload({"name": "hello"})
        assert result["name"] == "hello"

    def test_non_string_preserved(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._unflatten_payload({"count": 42})
        assert result["count"] == 42

    def test_roundtrip(self, tmp_path):
        client = self._make_client(tmp_path)
        original = {"name": "test", "tags": ["a", "b"], "meta": {"k": "v"}, "count": 5}
        flat = client._flatten_payload(original)
        restored = client._unflatten_payload(flat)
        assert restored == original


class TestBuildWhereClause:
    """_build_where_clause converts Qdrant-style filters to ChromaDB."""

    def _make_client(self, tmp_path):
        from isa_common import AsyncChromaClient
        return AsyncChromaClient(
            persist_directory=str(tmp_path), lazy_connect=True
        )

    def test_single_must_keyword(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._build_where_clause({
            "must": [{"field": "type", "match": {"keyword": "tool"}}]
        })
        assert result == {"type": {"$eq": "tool"}}

    def test_multiple_must_uses_and(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._build_where_clause({
            "must": [
                {"field": "type", "match": {"keyword": "tool"}},
                {"field": "active", "match": {"boolean": True}},
            ]
        })
        assert "$and" in result

    def test_range_condition(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._build_where_clause({
            "must": [{"field": "score", "range": {"gte": 0.5, "lt": 1.0}}]
        })
        assert result == {"score": {"$gte": 0.5, "$lt": 1.0}}

    def test_empty_must_returns_none(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._build_where_clause({"must": []})
        assert result is None

    def test_no_must_key_returns_none(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client._build_where_clause({})
        assert result is None


class TestParseSearchResults:
    """_parse_search_results converts ChromaDB results to Qdrant format."""

    def _make_client(self, tmp_path):
        from isa_common import AsyncChromaClient
        return AsyncChromaClient(
            persist_directory=str(tmp_path), lazy_connect=True
        )

    def test_basic_parse(self, tmp_path):
        client = self._make_client(tmp_path)
        results = {
            "ids": [["id1", "id2"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{"name": "a"}, {"name": "b"}]],
        }
        parsed = client._parse_search_results(results, None, True, False)
        assert len(parsed) == 2
        assert parsed[0]["id"] == "id1"
        assert parsed[0]["score"] == pytest.approx(0.9)
        assert parsed[0]["payload"] == {"name": "a"}

    def test_score_threshold_filters(self, tmp_path):
        client = self._make_client(tmp_path)
        results = {
            "ids": [["id1", "id2"]],
            "distances": [[0.1, 0.9]],
            "metadatas": [[{"name": "a"}, {"name": "b"}]],
        }
        parsed = client._parse_search_results(results, 0.5, True, False)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "id1"

    def test_empty_results(self, tmp_path):
        client = self._make_client(tmp_path)
        results = {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        parsed = client._parse_search_results(results, None, True, False)
        assert parsed == []


# ============================================================================
# L2 — Component tests (mocked chromadb backend)
# ============================================================================


class TestChromaClientDisconnect:
    """_disconnect cleans up client and executor."""

    async def test_disconnect_shuts_down_executor(self, chroma_client):
        mock_executor = MagicMock()
        chroma_client._executor = mock_executor
        await chroma_client._disconnect()
        mock_executor.shutdown.assert_called_once_with(
            wait=True, cancel_futures=True
        )
        assert chroma_client._client is None
        assert chroma_client._executor is None


class TestChromaClientCollections:
    """Collection management operations."""

    async def test_create_collection(self, chroma_client):
        chroma_client._client.get_or_create_collection = MagicMock()

        result = await chroma_client.create_collection("test_col", vector_size=128)
        assert result is True

    async def test_list_collections(self, chroma_client):
        mock_col1 = MagicMock()
        mock_col1.name = "col1"
        mock_col2 = MagicMock()
        mock_col2.name = "col2"
        chroma_client._client.list_collections = MagicMock(
            return_value=[mock_col1, mock_col2]
        )

        result = await chroma_client.list_collections()
        assert result == ["col1", "col2"]

    async def test_delete_collection(self, chroma_client):
        chroma_client._client.delete_collection = MagicMock()

        result = await chroma_client.delete_collection("test_col")
        assert result is True
        chroma_client._client.delete_collection.assert_called_with("test_col")

    async def test_get_collection_info(self, chroma_client):
        mock_col = MagicMock()
        mock_col.count.return_value = 42
        mock_col.metadata = {"hnsw:space": "cosine"}
        chroma_client._client.get_collection = MagicMock(return_value=mock_col)

        info = await chroma_client.get_collection_info("test_col")
        assert info["points_count"] == 42
        assert info["status"] == "ready"


class TestChromaClientPointOps:
    """Point upsert/delete/count operations."""

    async def test_upsert_points(self, chroma_client):
        mock_col = MagicMock()
        mock_col.upsert = MagicMock()
        chroma_client._client.get_or_create_collection = MagicMock(return_value=mock_col)

        points = [
            {"id": 1, "vector": [0.1] * 4, "payload": {"name": "a"}},
            {"id": 2, "vector": [0.2] * 4, "payload": {"name": "b"}},
        ]
        result = await chroma_client.upsert_points("col", points)
        assert result == "success"
        mock_col.upsert.assert_called_once()

    async def test_delete_points(self, chroma_client):
        mock_col = MagicMock()
        mock_col.delete = MagicMock()
        chroma_client._client.get_collection = MagicMock(return_value=mock_col)

        result = await chroma_client.delete_points("col", [1, 2])
        assert result == "success"
        mock_col.delete.assert_called_once_with(ids=["1", "2"])

    async def test_count_points(self, chroma_client):
        mock_col = MagicMock()
        mock_col.count.return_value = 10
        chroma_client._client.get_collection = MagicMock(return_value=mock_col)

        count = await chroma_client.count_points("col")
        assert count == 10


class TestChromaIndexOps:
    """Index management is a no-op for ChromaDB."""

    async def test_create_field_index_noop(self, chroma_client):
        result = await chroma_client.create_field_index("col", "field")
        assert result == "success"

    async def test_delete_field_index_noop(self, chroma_client):
        result = await chroma_client.delete_field_index("col", "field")
        assert result == "success"
