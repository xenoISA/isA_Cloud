#!/usr/bin/env python3
"""
Async FalkorDB Client - Integration Tests

Requires a running FalkorDB instance. Skipped automatically when unreachable.
Run locally:
    docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
    HOST=localhost PORT=6379 pytest tests/falkor/test_async_falkor.py
"""

import os
import socket
import uuid

import pytest
import pytest_asyncio

from isa_common import AsyncFalkorClient


HOST = os.environ.get("FALKOR_HOST", os.environ.get("HOST", "localhost"))
PORT = int(os.environ.get("FALKOR_PORT", os.environ.get("PORT", "6379")))


def _falkor_reachable() -> bool:
    """Check that the host:port answers AND speaks FalkorDB (not plain Redis)."""
    try:
        with socket.create_connection((HOST, PORT), timeout=1.0):
            pass
    except OSError:
        return False

    try:
        import asyncio

        async def _probe() -> bool:
            from falkordb.asyncio import FalkorDB

            db = FalkorDB(
                host=HOST,
                port=PORT,
                username=os.environ.get("FALKOR_USERNAME"),
                password=os.environ.get("FALKOR_PASSWORD"),
            )
            try:
                await db.list_graphs()
                return True
            finally:
                close = getattr(db.connection, "aclose", None) or getattr(
                    db.connection, "close", None
                )
                if close:
                    res = close()
                    if hasattr(res, "__await__"):
                        await res

        return asyncio.run(_probe())
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _falkor_reachable(),
        reason=f"FalkorDB module not available at {HOST}:{PORT} (or auth required)",
    ),
]


@pytest_asyncio.fixture
async def client():
    graph_name = f"test_{uuid.uuid4().hex[:8]}"
    c = AsyncFalkorClient(host=HOST, port=PORT, graph=graph_name, lazy_connect=True)
    yield c
    try:
        await c.drop_graph()
    finally:
        await c.close()


class TestFalkorIntegration:
    async def test_health_check(self, client):
        result = await client.health_check()
        assert result is not None
        assert result["healthy"] is True

    async def test_query_returns_value(self, client):
        rows = await client.query("RETURN 1 AS v")
        assert rows == [{"v": 1}]

    async def test_create_node_and_read_back(self, client):
        await client.query(
            "CREATE (n:Skill {id: $id, name: $name})",
            params={"id": "calendar-management", "name": "Calendar Management"},
        )
        rows = await client.query(
            "MATCH (n:Skill {id: $id}) RETURN n.name AS name",
            params={"id": "calendar-management"},
        )
        assert rows == [{"name": "Calendar Management"}]

    async def test_bulk_create_with_merge_is_idempotent(self, client):
        rows_in = [
            {"id": "skill-a", "name": "Skill A"},
            {"id": "skill-b", "name": "Skill B"},
        ]
        await client.bulk_create_nodes("Skill", rows_in, merge_on="id")
        await client.bulk_create_nodes("Skill", rows_in, merge_on="id")

        rows = await client.query("MATCH (n:Skill) RETURN count(n) AS c")
        assert rows[0]["c"] == 2

    async def test_vector_index_round_trip(self, client):
        ok = await client.create_index(
            "Doc", "embedding", kind="vector", dim=4, metric="cosine"
        )
        assert ok is True

        await client.query(
            "CREATE (:Doc {id: 'a', embedding: vecf32([1.0, 0.0, 0.0, 0.0])})"
        )
        await client.query(
            "CREATE (:Doc {id: 'b', embedding: vecf32([0.0, 1.0, 0.0, 0.0])})"
        )

        results = await client.query_vector(
            "Doc", "embedding", vector=[1.0, 0.0, 0.0, 0.0], k=2
        )
        assert results is not None
        assert len(results) >= 1
        top = results[0]
        assert top["node"]["properties"]["id"] == "a"
