"""Unit tests for #123 — verify ThreadPoolExecutor shutdown is graceful."""
import ast
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PKG_ROOT = Path(__file__).resolve().parents[2] / "isa_common"


class TestNoWaitFalseShutdown:
    """No client should use shutdown(wait=False)."""

    FILES_TO_CHECK = [
        _PKG_ROOT / "async_duckdb_client.py",
        _PKG_ROOT / "async_chroma_client.py",
        _PKG_ROOT / "async_local_storage_client.py",
    ]

    @pytest.mark.parametrize("filepath", FILES_TO_CHECK, ids=lambda p: p.name)
    def test_no_shutdown_wait_false(self, filepath):
        """Files must not use shutdown(wait=False) which orphans threads."""
        source = filepath.read_text()
        assert "shutdown(wait=False)" not in source, (
            f"{filepath.name} still uses shutdown(wait=False)"
        )

    @pytest.mark.parametrize("filepath", FILES_TO_CHECK, ids=lambda p: p.name)
    def test_uses_graceful_shutdown(self, filepath):
        """Files should use shutdown(wait=True, cancel_futures=True)."""
        source = filepath.read_text()
        if "shutdown" in source:
            assert "shutdown(wait=True" in source, (
                f"{filepath.name} should use shutdown(wait=True, ...)"
            )


class TestDuckDBExecutorShutdown:
    """DuckDB client executor shutdown is graceful."""

    async def test_disconnect_shuts_down_executor(self):
        from isa_common import AsyncDuckDBClient

        client = AsyncDuckDBClient(lazy_connect=True)
        client._conn = MagicMock()
        client._executor = MagicMock()
        client._connected = True

        await client._disconnect()

        client._executor.shutdown.assert_called_once_with(
            wait=True, cancel_futures=True
        )


class TestChromaExecutorShutdown:
    """ChromaDB client executor shutdown is graceful."""

    async def test_disconnect_shuts_down_executor(self):
        from isa_common import AsyncChromaClient

        client = AsyncChromaClient(
            persist_directory="/tmp/test_chroma",
            lazy_connect=True,
        )
        client._client = MagicMock()
        mock_executor = MagicMock()
        client._executor = mock_executor
        client._connected = True

        await client._disconnect()

        # _disconnect sets _executor = None after shutdown, so check the original mock
        mock_executor.shutdown.assert_called_once_with(
            wait=True, cancel_futures=True
        )


class TestLocalStorageExecutorShutdown:
    """LocalStorage client executor shutdown is graceful."""

    async def test_disconnect_shuts_down_executor(self):
        from isa_common import AsyncLocalStorageClient

        client = AsyncLocalStorageClient(
            base_path="/tmp/test_storage",
            lazy_connect=True,
        )
        mock_executor = MagicMock()
        client._executor = mock_executor
        client._connected = True

        await client._disconnect()

        # _disconnect sets _executor = None after shutdown, so check the original mock
        mock_executor.shutdown.assert_called_once_with(
            wait=True, cancel_futures=True
        )
