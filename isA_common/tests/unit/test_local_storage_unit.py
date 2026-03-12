"""Unit tests for AsyncLocalStorageClient — #119."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# L1 — Path helpers (pure logic, no I/O)
# ============================================================================


class TestGetUserPath:
    """_get_user_path returns tenant-isolated path."""

    def test_with_user_id(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="test_user", lazy_connect=True
        )
        assert client._get_user_path() == tmp_path / "user-test-user"

    def test_without_user_id(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), lazy_connect=True
        )
        # Default user_id is "default", but _get_user_path adds "user-" prefix
        assert client._get_user_path() == tmp_path / "user-default"

    def test_sanitizes_user_id(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="auth0|USER_123", lazy_connect=True
        )
        path = client._get_user_path()
        assert "auth0-user-123" in str(path)
        assert "--" not in path.name
        assert "|" not in path.name


class TestGetBucketPath:
    """_get_bucket_path sanitizes and returns bucket directory."""

    def test_basic_bucket(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="u1", lazy_connect=True
        )
        path = client._get_bucket_path("my_bucket")
        assert path.name == "my-bucket"

    def test_sanitizes_double_hyphens(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="u1", lazy_connect=True
        )
        path = client._get_bucket_path("my__bucket")
        assert "--" not in path.name


class TestGetObjectPath:
    """_get_object_path validates against path traversal."""

    def test_valid_object_key(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="u1", lazy_connect=True
        )
        path = client._get_object_path("bucket", "dir/file.txt")
        assert "dir/file.txt" in str(path) or "dir" in str(path)

    def test_path_traversal_blocked(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="u1", lazy_connect=True
        )
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "../../etc/passwd")

    def test_path_traversal_dotdot_in_middle(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="u1", lazy_connect=True
        )
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "a/../../etc/passwd")


class TestGetMetadataPath:
    """_get_metadata_path returns sidecar .meta.json path."""

    def test_metadata_path(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        client = AsyncLocalStorageClient(
            base_path=str(tmp_path), user_id="u1", lazy_connect=True
        )
        obj_path = tmp_path / "file.txt"
        meta_path = client._get_metadata_path(obj_path)
        assert meta_path == tmp_path / "file.txt.meta.json"


# ============================================================================
# L2 — Component tests (real filesystem via tmp_path)
# ============================================================================


class TestLocalStorageConnect:
    """_connect creates base directory."""

    async def test_connect_creates_directory(self, tmp_path):
        from isa_common import AsyncLocalStorageClient
        base = tmp_path / "new_storage"
        client = AsyncLocalStorageClient(
            base_path=str(base), lazy_connect=True
        )
        client._connected = True
        await client._connect()
        assert base.exists()


class TestLocalStorageDisconnect:
    """_disconnect shuts down executor."""

    async def test_disconnect_shuts_down_executor(self, local_storage_client):
        mock_executor = MagicMock()
        local_storage_client._executor = mock_executor
        await local_storage_client._disconnect()
        mock_executor.shutdown.assert_called_once_with(
            wait=True, cancel_futures=True
        )
        assert local_storage_client._executor is None


class TestLocalStorageBucketOps:
    """Bucket create/exists/delete/list operations."""

    async def test_create_bucket(self, local_storage_client):
        result = await local_storage_client.create_bucket("test-bucket")
        assert result is True
        bucket_path = local_storage_client._get_bucket_path("test-bucket")
        assert bucket_path.exists()

    async def test_bucket_exists_true(self, local_storage_client):
        await local_storage_client.create_bucket("exists-bucket")
        result = await local_storage_client.bucket_exists("exists-bucket")
        assert result is True

    async def test_bucket_exists_false(self, local_storage_client):
        result = await local_storage_client.bucket_exists("nonexistent")
        assert result is False

    async def test_list_buckets_empty(self, local_storage_client):
        result = await local_storage_client.list_buckets()
        assert result == []

    async def test_list_buckets(self, local_storage_client):
        await local_storage_client.create_bucket("b1")
        await local_storage_client.create_bucket("b2")
        result = await local_storage_client.list_buckets()
        assert sorted(result) == ["b1", "b2"]

    async def test_delete_empty_bucket(self, local_storage_client):
        await local_storage_client.create_bucket("del-bucket")
        result = await local_storage_client.delete_bucket("del-bucket")
        assert result is True

    async def test_delete_nonexistent_bucket(self, local_storage_client):
        result = await local_storage_client.delete_bucket("no-such-bucket")
        assert result is True


class TestLocalStorageObjectOps:
    """Object put/get/delete/exists operations."""

    async def test_put_and_get_object(self, local_storage_client):
        data = b"Hello, World!"
        etag = await local_storage_client.put_object(
            "test-bucket", "hello.txt", data, content_type="text/plain"
        )
        assert etag is not None

        retrieved = await local_storage_client.get_object("test-bucket", "hello.txt")
        assert retrieved == data

    async def test_get_nonexistent_object(self, local_storage_client):
        await local_storage_client.create_bucket("empty-bucket")
        result = await local_storage_client.get_object("empty-bucket", "nope.txt")
        assert result is None

    async def test_object_exists(self, local_storage_client):
        await local_storage_client.put_object("bucket", "file.txt", b"data")
        assert await local_storage_client.object_exists("bucket", "file.txt") is True
        assert await local_storage_client.object_exists("bucket", "nope.txt") is False

    async def test_delete_object(self, local_storage_client):
        await local_storage_client.put_object("bucket", "file.txt", b"data")
        result = await local_storage_client.delete_object("bucket", "file.txt")
        assert result is True
        assert await local_storage_client.object_exists("bucket", "file.txt") is False

    async def test_get_object_info(self, local_storage_client):
        await local_storage_client.put_object(
            "bucket", "file.txt", b"data",
            content_type="text/plain", metadata={"author": "test"}
        )
        info = await local_storage_client.get_object_info("bucket", "file.txt")
        assert info is not None
        assert info["key"] == "file.txt"
        assert info["size"] == 4
        assert info["content_type"] == "text/plain"

    async def test_copy_object(self, local_storage_client):
        await local_storage_client.put_object("src", "file.txt", b"data")
        etag = await local_storage_client.copy_object("src", "file.txt", "dst", "copy.txt")
        assert etag is not None
        copied = await local_storage_client.get_object("dst", "copy.txt")
        assert copied == b"data"

    async def test_move_object(self, local_storage_client):
        await local_storage_client.put_object("src", "file.txt", b"data")
        etag = await local_storage_client.move_object("src", "file.txt", "dst", "moved.txt")
        assert etag is not None
        assert await local_storage_client.object_exists("src", "file.txt") is False
        assert await local_storage_client.get_object("dst", "moved.txt") == b"data"


class TestLocalStoragePresignedUrl:
    """get_presigned_url returns file:// URL."""

    async def test_presigned_url_for_existing_object(self, local_storage_client):
        await local_storage_client.put_object("bucket", "f.txt", b"x")
        url = await local_storage_client.get_presigned_url("bucket", "f.txt")
        assert url.startswith("file://")

    async def test_presigned_url_for_nonexistent_get(self, local_storage_client):
        await local_storage_client.create_bucket("bucket")
        url = await local_storage_client.get_presigned_url("bucket", "nope.txt")
        assert url is None

    async def test_presigned_url_put_method(self, local_storage_client):
        await local_storage_client.create_bucket("bucket")
        url = await local_storage_client.get_presigned_url(
            "bucket", "new.txt", method="PUT"
        )
        assert url.startswith("file://")
