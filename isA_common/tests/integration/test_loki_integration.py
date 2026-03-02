"""
AsyncLokiClient integration tests — requires a running Loki instance.

Run with: LOKI_PORT=3101 python -m pytest isA_common/tests/integration/test_loki_integration.py -v
"""
import os
import time
import asyncio
import logging
import pytest
import pytest_asyncio

# Skip entire module if Loki is not reachable
LOKI_PORT = int(os.getenv("LOKI_PORT", "3101"))
LOKI_HOST = os.getenv("LOKI_HOST", "localhost")


def loki_available():
    """Check if Loki is reachable."""
    import socket
    try:
        sock = socket.create_connection((LOKI_HOST, LOKI_PORT), timeout=2)
        sock.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not loki_available(),
    reason=f"Loki not available at {LOKI_HOST}:{LOKI_PORT}",
)


@pytest_asyncio.fixture
async def client():
    """Real AsyncLokiClient connected to local Loki."""
    from isa_common import AsyncLokiClient

    c = AsyncLokiClient(
        host=LOKI_HOST,
        port=LOKI_PORT,
        default_labels={"app": "isa-integration-test", "env": "test"},
    )
    yield c
    await c.close()


class TestLokiHealthCheckIntegration:
    async def test_health_check_returns_healthy(self, client):
        result = await client.health_check()
        assert result is not None
        assert result["healthy"] is True
        assert result["loki_status"] == "ready"


class TestLokiPushIntegration:
    async def test_push_single_log(self, client):
        result = await client.push_log(
            "Integration test log entry",
            labels={"level": "INFO", "test_id": "push_single"},
        )
        assert result is True

        # Flush to send to Loki
        flush_ok = await client.flush()
        assert flush_ok is True

    async def test_push_batch(self, client):
        entries = [
            {
                "labels": {"level": "INFO", "test_id": "push_batch"},
                "message": f"Batch entry {i}",
            }
            for i in range(5)
        ]
        result = await client.push_batch(entries)
        assert result is True

    async def test_push_and_query_roundtrip(self, client):
        """Push a log, wait briefly, then query it back."""
        unique_id = f"roundtrip-{int(time.time() * 1000)}"
        message = f"Roundtrip test message {unique_id}"

        # Push
        await client.push_log(
            message,
            labels={"level": "INFO", "test_id": unique_id},
        )
        await client.flush()

        # Loki needs a moment to index
        await asyncio.sleep(2)

        # Query
        result = await client.query(
            f'{{app="isa-integration-test", test_id="{unique_id}"}}',
            limit=10,
        )
        assert result is not None
        assert result["status"] == "success"

        # Verify we got our log back
        streams = result.get("data", {}).get("result", [])
        assert len(streams) > 0, f"Expected at least 1 stream, got {len(streams)}"

        # Check the message content
        all_values = []
        for stream in streams:
            all_values.extend(stream.get("values", []))
        messages = [v[1] for v in all_values]
        assert any(unique_id in m for m in messages), (
            f"Expected message containing '{unique_id}' in {messages}"
        )


class TestLokiQueryIntegration:
    async def test_query_all_logs(self, client):
        result = await client.query('{app="isa-integration-test"}', limit=5)
        assert result is not None
        assert result["status"] == "success"

    async def test_query_nonexistent_label(self, client):
        result = await client.query('{app="nonexistent-service-xyz"}', limit=5)
        assert result is not None
        assert result["status"] == "success"
        streams = result.get("data", {}).get("result", [])
        assert len(streams) == 0


class TestLokiLabelsIntegration:
    async def test_get_labels(self, client):
        # First push something so labels exist
        await client.push_log("label test", labels={"level": "DEBUG"})
        await client.flush()
        await asyncio.sleep(1)

        labels = await client.get_labels()
        assert labels is not None
        assert isinstance(labels, list)
        # At minimum "app" should exist from our pushes
        assert "app" in labels

    async def test_get_label_values(self, client):
        await client.push_log("label value test", labels={"level": "WARN"})
        await client.flush()
        await asyncio.sleep(1)

        values = await client.get_label_values("app")
        assert values is not None
        assert isinstance(values, list)
        assert "isa-integration-test" in values


class TestLokiHandlerIntegration:
    async def test_setup_loki_logging_ships_logs(self, client):
        """Test the LokiHandler ships real logs via Python logging."""
        from isa_common.loki_handler import setup_loki_logging

        handler = setup_loki_logging(
            service_name="isa-handler-test",
            loki_url=f"http://{LOKI_HOST}:{LOKI_PORT}",
            level=logging.DEBUG,
        )

        # Get a logger and emit some messages
        logger = logging.getLogger("test.loki.handler")
        unique_marker = f"handler-{int(time.time() * 1000)}"
        logger.info(f"Handler integration test {unique_marker}")
        logger.warning(f"Handler warning test {unique_marker}")

        # Give the background thread time to flush
        await asyncio.sleep(4)

        # Clean up handler
        logging.getLogger().removeHandler(handler)
        handler.close()

        # Query Loki for the logs
        result = await client.query(
            f'{{app="isa-handler-test"}}',
            limit=20,
        )
        assert result is not None
        assert result["status"] == "success"

        streams = result.get("data", {}).get("result", [])
        all_messages = []
        for stream in streams:
            all_messages.extend([v[1] for v in stream.get("values", [])])

        assert any(unique_marker in m for m in all_messages), (
            f"Expected '{unique_marker}' in Loki logs. Got: {all_messages[:5]}"
        )


class TestGrafanaProvisioningIntegration:
    async def test_grafana_has_loki_datasource(self):
        """Verify Grafana auto-provisioned the Loki datasource."""
        import aiohttp

        grafana_port = int(os.getenv("GRAFANA_PORT", "3001"))
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://localhost:{grafana_port}/api/datasources",
                auth=aiohttp.BasicAuth("admin", "admin"),
            ) as resp:
                assert resp.status == 200
                datasources = await resp.json()
                loki_ds = [d for d in datasources if d["type"] == "loki"]
                assert len(loki_ds) > 0, f"No Loki datasource found. Got: {datasources}"
                assert loki_ds[0]["name"] == "Loki"

    async def test_grafana_has_dashboard(self):
        """Verify Grafana auto-loaded the isA Platform Logs dashboard."""
        import aiohttp

        grafana_port = int(os.getenv("GRAFANA_PORT", "3001"))
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://localhost:{grafana_port}/api/search?query=isA%20Platform%20Logs",
                auth=aiohttp.BasicAuth("admin", "admin"),
            ) as resp:
                assert resp.status == 200
                dashboards = await resp.json()
                assert len(dashboards) > 0, (
                    f"No 'isA Platform Logs' dashboard found. Got: {dashboards}"
                )
