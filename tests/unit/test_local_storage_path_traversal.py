#!/usr/bin/env python3
"""
Unit tests for AsyncLocalStorageClient._get_object_path path traversal validation.

Covers: ../traversal, absolute paths, nested traversal, and legitimate paths.
Fixes #118.
"""

import os
import pytest
from pathlib import Path

from isa_common.async_local_storage_client import AsyncLocalStorageClient


@pytest.fixture
def client(tmp_path):
    """Create a client with a temp base path (no connection needed for path tests)."""
    return AsyncLocalStorageClient(base_path=str(tmp_path), user_id="testuser")


class TestGetObjectPathTraversal:
    """Path traversal must raise ValueError."""

    def test_simple_dotdot(self, client):
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "../escape")

    def test_dotdot_etc_passwd(self, client):
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "../../../etc/passwd")

    def test_nested_traversal_escapes_bucket(self, client):
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "subdir/../../..")

    def test_absolute_path(self, client):
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "/etc/passwd")

    def test_dotdot_at_start_and_middle(self, client):
        with pytest.raises(ValueError, match="path traversal"):
            client._get_object_path("bucket", "../other-bucket/secret.txt")


class TestGetObjectPathValid:
    """Legitimate paths must resolve correctly."""

    def test_simple_filename(self, client):
        path = client._get_object_path("bucket", "file.txt")
        assert path.name == "file.txt"
        assert "bucket" in str(path)

    def test_nested_subdirectory(self, client):
        path = client._get_object_path("bucket", "a/b/c/file.txt")
        assert path.name == "file.txt"
        assert "a/b/c" in str(path) or os.path.join("a", "b", "c") in str(path)

    def test_dotdot_that_stays_in_bucket(self, client):
        """subdir/../file.txt resolves to file.txt inside bucket — should be allowed."""
        path = client._get_object_path("bucket", "subdir/../file.txt")
        assert path.resolve().name == "file.txt"

    def test_path_with_dots_in_name(self, client):
        """Filenames with dots (not traversal) should work."""
        path = client._get_object_path("bucket", "archive.2024.01.tar.gz")
        assert path.name == "archive.2024.01.tar.gz"

    def test_hidden_file(self, client):
        path = client._get_object_path("bucket", ".hidden")
        assert path.name == ".hidden"
