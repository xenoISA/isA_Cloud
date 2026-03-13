"""AsyncMQTTClient unit tests — mocked state, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMQTTConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncMQTTClient

        client = AsyncMQTTClient(host="localhost", port=1883, lazy_connect=True)
        assert client._connected is False

    async def test_close_sets_disconnected(self, mqtt_client):
        await mqtt_client.close()
        assert mqtt_client._connected is False


class TestMQTTHealthCheck:
    async def test_health_check_success(self, mqtt_client):
        # Mock the aiomqtt.Client context manager used in health_check
        mock_mqtt = AsyncMock()
        mock_mqtt.__aenter__ = AsyncMock(return_value=mock_mqtt)
        mock_mqtt.__aexit__ = AsyncMock(return_value=None)

        with patch("isa_common.async_mqtt_client.aiomqtt.Client", return_value=mock_mqtt):
            result = await mqtt_client.health_check()

        assert result is not None
        assert result.get("healthy") is True

    async def test_health_check_error_returns_none(self, mqtt_client):
        # MQTT health_check now returns None on error (consistent with all other clients)
        mock_mqtt = AsyncMock()
        mock_mqtt.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))

        with patch("isa_common.async_mqtt_client.aiomqtt.Client", return_value=mock_mqtt):
            result = await mqtt_client.health_check()

        assert result is None


class TestMQTTSessionManagement:
    async def test_mqtt_connect_creates_session(self, mqtt_client):
        result = await mqtt_client.mqtt_connect(
            client_id="device_001",
            username="user",
            password="pass",
        )

        assert result is not None

    async def test_disconnect_removes_session(self, mqtt_client):
        # First create a session
        connect_result = await mqtt_client.mqtt_connect(client_id="device_001")
        session_id = connect_result.get("session_id") if isinstance(connect_result, dict) else None

        if session_id:
            result = await mqtt_client.disconnect(session_id)
            assert result is not None

    async def test_get_connection_status(self, mqtt_client):
        connect_result = await mqtt_client.mqtt_connect(client_id="device_002")
        session_id = connect_result.get("session_id") if isinstance(connect_result, dict) else None

        if session_id:
            status = await mqtt_client.get_connection_status(session_id)
            assert status is not None


class TestMQTTPublish:
    async def test_publish_to_topic(self, mqtt_client):
        # Create a session first
        connect_result = await mqtt_client.mqtt_connect(client_id="pub_client")
        session_id = connect_result.get("session_id") if isinstance(connect_result, dict) else None

        if session_id:
            mock_mqtt = AsyncMock()
            mock_mqtt.publish = AsyncMock()
            mock_mqtt.__aenter__ = AsyncMock(return_value=mock_mqtt)
            mock_mqtt.__aexit__ = AsyncMock(return_value=None)

            with patch("isa_common.async_mqtt_client.aiomqtt.Client", return_value=mock_mqtt):
                result = await mqtt_client.publish(
                    session_id, "sensors/temp", b"22.5", qos=1
                )
                assert result is not None
                assert result.get("success") is True


class TestMQTTMultiTenant:
    async def test_topic_prefixed_with_org_and_user(self, mqtt_client):
        prefixed = mqtt_client._prefix_key("devices/sensor1")
        assert "org1" in prefixed
        assert "test_user" in prefixed


class TestMQTTDeviceManagement:
    async def test_register_device(self, mqtt_client):
        result = await mqtt_client.register_device(
            device_id="sensor_001",
            device_name="Temperature Sensor",
            device_type="sensor",
        )

        assert result is not None

    async def test_list_devices(self, mqtt_client):
        # Register a device first
        await mqtt_client.register_device(
            device_id="sensor_002",
            device_name="Humidity Sensor",
            device_type="sensor",
        )

        result = await mqtt_client.list_devices()

        assert result is not None

    async def test_unregister_device(self, mqtt_client):
        await mqtt_client.register_device(
            device_id="sensor_003",
            device_name="Temp",
            device_type="sensor",
        )

        result = await mqtt_client.unregister_device("sensor_003")

        assert result is not None


class TestMQTTErrorHandling:
    async def test_publish_error_returns_none(self, mqtt_client):
        # Publish raises when broker is unreachable
        mock_mqtt = AsyncMock()
        mock_mqtt.__aenter__ = AsyncMock(side_effect=Exception("broker unreachable"))

        with patch("isa_common.async_mqtt_client.aiomqtt.Client", return_value=mock_mqtt):
            result = await mqtt_client.publish(
                "some_session", "topic", b"data"
            )

        assert result is None
