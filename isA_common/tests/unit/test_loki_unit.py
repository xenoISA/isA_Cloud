"""AsyncLokiClient unit tests — mocked aiohttp session, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestLokiConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncLokiClient

        client = AsyncLokiClient(host="localhost", port=3100, lazy_connect=True)
        assert client._connected is False
        assert client._session is None

    async def test_close_sets_disconnected(self, loki_client):
        loki_client._session.close = AsyncMock()
        await loki_client.close()
        assert loki_client._connected is False

    async def test_base_url(self, loki_client):
        assert loki_client._base_url == "http://localhost:3100"

    async def test_headers_without_tenant(self):
        from isa_common import AsyncLokiClient

        client = AsyncLokiClient(host="localhost", port=3100)
        headers = client._headers()
        assert headers == {"Content-Type": "application/json"}
        assert "X-Scope-OrgID" not in headers

    async def test_headers_with_tenant(self):
        from isa_common import AsyncLokiClient

        client = AsyncLokiClient(host="localhost", port=3100, tenant_id="my-org")
        headers = client._headers()
        assert headers["X-Scope-OrgID"] == "my-org"


class TestLokiHealthCheck:
    async def test_health_check_success(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        result = await loki_client.health_check()

        assert result is not None
        assert result["healthy"] is True
        assert result["loki_status"] == "ready"

    async def test_health_check_not_ready(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        result = await loki_client.health_check()

        assert result["healthy"] is False
        assert result["loki_status"] == "not_ready"

    async def test_health_check_on_error_returns_none(self, loki_client):
        loki_client._session.get = MagicMock(side_effect=ConnectionError("refused"))

        result = await loki_client.health_check()

        assert result is None


class TestLokiPushLog:
    async def test_push_log_adds_to_batch(self, loki_client):
        result = await loki_client.push_log("test message", labels={"level": "INFO"})

        assert result is True
        assert len(loki_client._batch) == 1
        entry = loki_client._batch[0]
        assert entry["labels"]["app"] == "test-service"
        assert entry["labels"]["level"] == "INFO"
        assert entry["values"][0][1] == "test message"

    async def test_push_log_uses_default_labels(self, loki_client):
        await loki_client.push_log("hello")

        entry = loki_client._batch[0]
        assert entry["labels"]["app"] == "test-service"
        assert entry["labels"]["env"] == "test"

    async def test_push_log_flushes_at_batch_size(self, loki_client):
        loki_client._batch_size = 2

        mock_resp = AsyncMock()
        mock_resp.status = 204
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.post = MagicMock(return_value=mock_resp)

        await loki_client.push_log("msg1")
        assert len(loki_client._batch) == 1

        await loki_client.push_log("msg2")
        # After hitting batch_size, batch should be flushed
        assert len(loki_client._batch) == 0

    async def test_push_log_with_custom_timestamp(self, loki_client):
        ts = 1700000000000000000
        await loki_client.push_log("timestamped", timestamp_ns=ts)

        entry = loki_client._batch[0]
        assert entry["values"][0][0] == str(ts)


class TestLokiPushBatch:
    async def test_push_batch_success(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 204
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.post = MagicMock(return_value=mock_resp)

        entries = [
            {"labels": {"level": "INFO"}, "message": "msg1"},
            {"labels": {"level": "ERROR"}, "message": "msg2"},
        ]

        result = await loki_client.push_batch(entries)

        assert result is True
        loki_client._session.post.assert_called_once()

    async def test_push_batch_failure(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="internal error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.post = MagicMock(return_value=mock_resp)

        result = await loki_client.push_batch([{"labels": {}, "message": "fail"}])

        assert result is False

    async def test_push_batch_groups_by_labels(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 204
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.post = MagicMock(return_value=mock_resp)

        entries = [
            {"labels": {"level": "INFO"}, "message": "msg1"},
            {"labels": {"level": "INFO"}, "message": "msg2"},
            {"labels": {"level": "ERROR"}, "message": "msg3"},
        ]

        await loki_client.push_batch(entries)

        call_args = loki_client._session.post.call_args
        payload = call_args[1]["json"]
        # INFO + ERROR streams, plus default labels merged, so 2 unique label combos
        assert len(payload["streams"]) == 2

    async def test_push_batch_connection_error(self, loki_client):
        loki_client._session.post = MagicMock(side_effect=ConnectionError("refused"))

        result = await loki_client.push_batch([{"labels": {}, "message": "fail"}])

        assert result is False


class TestLokiQuery:
    async def test_query_success(self, loki_client):
        mock_data = {"status": "success", "data": {"result": []}}
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        result = await loki_client.query('{app="test-service"}')

        assert result is not None
        assert result["status"] == "success"

    async def test_query_with_time_range(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"status": "success"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        await loki_client.query(
            '{app="test-service"}',
            start="2024-01-01T00:00:00Z",
            end="2024-01-02T00:00:00Z",
            limit=50,
        )

        call_args = loki_client._session.get.call_args
        params = call_args[1]["params"]
        assert params["start"] == "2024-01-01T00:00:00Z"
        assert params["end"] == "2024-01-02T00:00:00Z"
        assert params["limit"] == "50"

    async def test_query_error_returns_none(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.text = AsyncMock(return_value="bad query")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        result = await loki_client.query("invalid")

        assert result is None


class TestLokiLabels:
    async def test_get_labels_success(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"data": ["app", "env", "level"]})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        result = await loki_client.get_labels()

        assert result == ["app", "env", "level"]

    async def test_get_label_values_success(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"data": ["isa-agent", "isa-model"]})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.get = MagicMock(return_value=mock_resp)

        result = await loki_client.get_label_values("app")

        assert result == ["isa-agent", "isa-model"]

    async def test_get_labels_error_returns_none(self, loki_client):
        loki_client._session.get = MagicMock(side_effect=Exception("timeout"))

        result = await loki_client.get_labels()

        assert result is None


class TestLokiFlush:
    async def test_manual_flush_empty_batch(self, loki_client):
        result = await loki_client.flush()
        assert result is True

    async def test_manual_flush_pushes_batch(self, loki_client):
        mock_resp = AsyncMock()
        mock_resp.status = 204
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        loki_client._session.post = MagicMock(return_value=mock_resp)

        await loki_client.push_log("msg1")
        await loki_client.push_log("msg2")
        assert len(loki_client._batch) == 2

        result = await loki_client.flush()

        assert result is True
        assert len(loki_client._batch) == 0
        loki_client._session.post.assert_called_once()


class TestLokiConfig:
    def test_loki_config_defaults(self):
        from isa_common import LokiConfig

        config = LokiConfig(host="localhost", port=3100)
        assert config.tenant_id == ""
        assert config.batch_size == 100
        assert config.flush_interval == 1.0

    def test_loki_config_from_env(self, monkeypatch):
        from isa_common import LokiConfig

        monkeypatch.setenv("LOKI_HOST", "loki-server")
        monkeypatch.setenv("LOKI_PORT", "3200")
        monkeypatch.setenv("LOKI_TENANT_ID", "org-42")
        monkeypatch.setenv("LOKI_BATCH_SIZE", "200")
        monkeypatch.setenv("LOKI_FLUSH_INTERVAL", "2.5")

        config = LokiConfig.from_env()

        assert config.host == "loki-server"
        assert config.port == 3200
        assert config.tenant_id == "org-42"
        assert config.batch_size == 200
        assert config.flush_interval == 2.5
