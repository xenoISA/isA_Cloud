"""AsyncQdrantClient unit tests — mocked qdrant-client, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestQdrantConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncQdrantClient

        client = AsyncQdrantClient(host="localhost", port=6333, lazy_connect=True)
        assert client._connected is False

    async def test_close_sets_disconnected(self, qdrant_client):
        await qdrant_client.close()
        assert qdrant_client._connected is False


class TestQdrantHealthCheck:
    async def test_health_check_success(self, qdrant_client):
        qdrant_client._client.get_collections = AsyncMock(
            return_value=MagicMock(collections=[])
        )

        result = await qdrant_client.health_check()

        assert result is not None
        assert result.get("healthy") is True

    async def test_health_check_error_returns_none(self, qdrant_client):
        qdrant_client._client.get_collections = AsyncMock(
            side_effect=Exception("connection refused")
        )

        result = await qdrant_client.health_check()

        assert result is None


class TestQdrantCollections:
    async def test_create_collection(self, qdrant_client):
        qdrant_client._client.create_collection = AsyncMock(return_value=True)

        result = await qdrant_client.create_collection("test_collection", vector_size=768)

        assert result is not None
        qdrant_client._client.create_collection.assert_awaited_once()

    async def test_list_collections(self, qdrant_client):
        mock_col1 = MagicMock()
        mock_col1.name = "collection_1"
        mock_col2 = MagicMock()
        mock_col2.name = "collection_2"
        qdrant_client._client.get_collections = AsyncMock(
            return_value=MagicMock(collections=[mock_col1, mock_col2])
        )

        result = await qdrant_client.list_collections()

        assert result is not None

    async def test_delete_collection(self, qdrant_client):
        qdrant_client._client.delete_collection = AsyncMock(return_value=True)

        result = await qdrant_client.delete_collection("test_collection")

        assert result is True or result is not None


class TestQdrantPointOps:
    async def test_upsert_points(self, qdrant_client):
        qdrant_client._client.upsert = AsyncMock(return_value=MagicMock(status="completed"))

        result = await qdrant_client.upsert_points(
            "test_collection",
            points=[{
                "id": "point_1",
                "vector": [0.1] * 768,
                "payload": {"text": "hello"},
            }]
        )

        assert result is not None

    async def test_search(self, qdrant_client):
        # Qdrant search() uses _client.query_points() internally
        mock_point = MagicMock()
        mock_point.id = "point_1"
        mock_point.score = 0.95
        mock_point.payload = {"text": "hello"}
        mock_point.vector = None

        mock_response = MagicMock()
        mock_response.points = [mock_point]
        qdrant_client._client.query_points = AsyncMock(return_value=mock_response)

        result = await qdrant_client.search(
            "test_collection",
            vector=[0.1] * 768,
            limit=5,
        )

        assert result is not None
        qdrant_client._client.query_points.assert_awaited_once()

    async def test_search_error_returns_none(self, qdrant_client):
        qdrant_client._client.query_points = AsyncMock(
            side_effect=Exception("collection not found")
        )

        result = await qdrant_client.search(
            "nonexistent", vector=[0.1] * 768, limit=5
        )

        assert result is None


class TestQdrantErrorHandling:
    async def test_create_collection_error_returns_none(self, qdrant_client):
        qdrant_client._client.create_collection = AsyncMock(
            side_effect=Exception("already exists")
        )

        result = await qdrant_client.create_collection("existing", vector_size=768)

        assert result is None

    async def test_upsert_error_returns_none(self, qdrant_client):
        qdrant_client._client.upsert = AsyncMock(
            side_effect=Exception("dimension mismatch")
        )

        result = await qdrant_client.upsert_points(
            "test_collection",
            points=[{"id": "p1", "vector": [0.1], "payload": {}}]
        )

        assert result is None
