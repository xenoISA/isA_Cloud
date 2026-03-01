"""AsyncMinIOClient unit tests — mocked aioboto3 session, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMinIOConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncMinIOClient

        client = AsyncMinIOClient(host="localhost", port=9000, lazy_connect=True)
        assert client._connected is False

    async def test_close_sets_disconnected(self, minio_client):
        await minio_client.close()
        assert minio_client._connected is False


class TestMinIOHealthCheck:
    async def test_health_check_success(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.list_buckets = AsyncMock(return_value={"Buckets": []})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.health_check()

        assert result is not None
        assert result.get("healthy") is True

    async def test_health_check_error_returns_none(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.health_check()

        assert result is None


class TestMinIOBucketOps:
    async def test_create_bucket(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.create_bucket = AsyncMock(return_value={})
        mock_s3.head_bucket = AsyncMock(side_effect=Exception("not found"))
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.create_bucket("test-bucket")

        assert result is not None

    async def test_list_buckets(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.list_buckets = AsyncMock(return_value={
            "Buckets": [
                {"Name": "user-test_user-bucket1"},
                {"Name": "user-test_user-bucket2"},
                {"Name": "other-user-bucket"},
            ]
        })
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.list_buckets()

        assert result is not None


class TestMinIOObjectOps:
    async def test_upload_object(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.upload_object(
            "test-bucket", "test.txt", b"hello world"
        )

        assert result is not None

    async def test_get_object(self, minio_client):
        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=b"file contents")

        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.get_object("test-bucket", "test.txt")

        assert result is not None

    async def test_delete_object(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.delete_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.delete_object("test-bucket", "test.txt")

        assert result is True or result is not None


class TestMinIOErrorHandling:
    async def test_upload_error_returns_none(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(side_effect=Exception("access denied"))
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.upload_object(
            "test-bucket", "test.txt", b"data"
        )

        assert result is None

    async def test_get_nonexistent_object_returns_none(self, minio_client):
        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(side_effect=Exception("NoSuchKey"))
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=None)
        minio_client._session.client = MagicMock(return_value=mock_s3)

        result = await minio_client.get_object("test-bucket", "missing.txt")

        assert result is None
