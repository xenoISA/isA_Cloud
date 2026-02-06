#!/usr/bin/env python3
"""
Async MQTT Native Client
High-performance async MQTT client using aiomqtt.

This client connects directly to MQTT broker using the aiomqtt library,
providing full support for all MQTT operations including:
- Publish/Subscribe messaging
- QoS levels (0, 1, 2)
- Retained messages
- Topic wildcards (+, #)
- Session management
"""

import os
import asyncio
import json
import uuid
from typing import List, Dict, Optional, AsyncIterator, Any
from datetime import datetime

import aiomqtt

from .async_base_client import AsyncBaseClient


class AsyncMQTTClient(AsyncBaseClient):
    """
    Async MQTT client using native aiomqtt driver.

    Provides direct connection to MQTT broker with full feature support including
    publish/subscribe, QoS levels, and retained messages.
    """

    # Class-level configuration
    SERVICE_NAME = "MQTT"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 1883
    ENV_PREFIX = "MQTT"
    TENANT_SEPARATOR = "/"  # org/user/topic

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize async MQTT client with native driver.

        Args:
            username: MQTT username (default: from MQTT_USER env)
            password: MQTT password (default: from MQTT_PASSWORD env)
            client_id: Client ID (default: auto-generated)
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._username = username or os.getenv('MQTT_USER')
        self._password = password or os.getenv('MQTT_PASSWORD')
        self._client_id = client_id or f"isa-mqtt-{uuid.uuid4().hex[:8]}"

        self._client: Optional[aiomqtt.Client] = None
        self._sessions: Dict[str, Dict] = {}
        self._devices: Dict[str, Dict] = {}
        self._subscriptions: Dict[str, Dict] = {}
        self._message_counts: Dict[str, int] = {'sent': 0, 'received': 0}

    def _get_topic_prefix(self) -> str:
        """Get topic prefix for multi-tenant isolation (MQTT uses '/' separator)."""
        return f"{self.organization_id}/{self.user_id}/"

    def _prefix_topic(self, topic: str) -> str:
        """Add prefix to topic for isolation."""
        prefix = self._get_topic_prefix()
        if topic.startswith(prefix):
            return topic
        return f"{prefix}{topic}"

    async def _connect(self) -> None:
        """MQTT uses context manager for connections, just log ready state."""
        self._logger.info(f"MQTT client ready for {self._host}:{self._port}")

    async def _disconnect(self) -> None:
        """Close MQTT connection state."""
        self._sessions.clear()

    def _get_client_config(self) -> Dict:
        """Get common client configuration."""
        config = {
            'hostname': self._host,
            'port': self._port,
            'identifier': self._client_id,
        }
        if self._username:
            config['username'] = self._username
        if self._password:
            config['password'] = self._password
        return config

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Health check."""
        try:
            config = self._get_client_config()
            async with aiomqtt.Client(**config) as client:
                return {
                    'healthy': True,
                    'broker_status': 'connected',
                    'active_connections': len(self._sessions),
                    'message': 'MQTT broker is reachable'
                }

        except Exception as e:
            return {
                'healthy': False,
                'broker_status': 'disconnected',
                'active_connections': 0,
                'message': str(e)
            }

    # ============================================
    # Connection Management
    # ============================================

    async def mqtt_connect(self, client_id: str, username: str = '',
                          password: str = '') -> Optional[Dict]:
        """Connect to MQTT service."""
        try:
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = {
                'client_id': client_id,
                'username': username,
                'connected_at': datetime.utcnow().isoformat(),
                'messages_sent': 0,
                'messages_received': 0
            }

            return {
                'success': True,
                'session_id': session_id,
                'message': f'Connected as {client_id}'
            }

        except Exception as e:
            return self.handle_error(e, "connect")

    async def disconnect(self, session_id: str) -> Optional[Dict]:
        """Disconnect from MQTT service."""
        try:
            if session_id in self._sessions:
                del self._sessions[session_id]

            return {'success': True, 'message': 'Disconnected'}

        except Exception as e:
            return self.handle_error(e, "disconnect")

    async def get_connection_status(self, session_id: str) -> Optional[Dict]:
        """Get connection status."""
        try:
            session = self._sessions.get(session_id, {})

            return {
                'connected': session_id in self._sessions,
                'connected_at': session.get('connected_at', ''),
                'messages_sent': session.get('messages_sent', 0),
                'messages_received': session.get('messages_received', 0)
            }

        except Exception as e:
            return self.handle_error(e, "get connection status")

    # ============================================
    # Publishing
    # ============================================

    async def publish(self, session_id: str, topic: str, payload: bytes,
                     qos: int = 1, retained: bool = False) -> Optional[Dict]:
        """Publish message."""
        try:
            config = self._get_client_config()
            async with aiomqtt.Client(**config) as client:
                await client.publish(
                    topic,
                    payload,
                    qos=qos,
                    retain=retained
                )

            # Update session stats
            if session_id in self._sessions:
                self._sessions[session_id]['messages_sent'] += 1

            message_id = str(uuid.uuid4())
            return {'success': True, 'message_id': message_id}

        except Exception as e:
            return self.handle_error(e, "publish")

    async def publish_batch(self, session_id: str,
                           messages: List[Dict]) -> Optional[Dict]:
        """
        Publish multiple messages in batch.

        Args:
            session_id: Session ID
            messages: List of dicts with keys: topic, payload, qos, retained
        """
        try:
            config = self._get_client_config()
            published = 0
            message_ids = []
            errors = []

            async with aiomqtt.Client(**config) as client:
                for msg in messages:
                    try:
                        await client.publish(
                            msg.get('topic'),
                            msg.get('payload', b''),
                            qos=msg.get('qos', 1),
                            retain=msg.get('retained', False)
                        )
                        message_ids.append(str(uuid.uuid4()))
                        published += 1
                    except Exception as e:
                        errors.append(str(e))

            # Update session stats
            if session_id in self._sessions:
                self._sessions[session_id]['messages_sent'] += published

            return {
                'success': True,
                'published_count': published,
                'failed_count': len(errors),
                'message_ids': message_ids,
                'errors': errors
            }

        except Exception as e:
            return self.handle_error(e, "publish batch")

    async def publish_json(self, session_id: str, topic: str, data: Dict,
                          qos: int = 1, retained: bool = False) -> Optional[Dict]:
        """Publish JSON message."""
        try:
            payload = json.dumps(data).encode('utf-8')
            return await self.publish(session_id, topic, payload, qos, retained)

        except Exception as e:
            return self.handle_error(e, "publish JSON")

    # ============================================
    # Subscriptions (Async Streaming)
    # ============================================

    async def subscribe(self, session_id: str, topic_filter: str,
                       qos: int = 1) -> AsyncIterator[Dict]:
        """
        Subscribe to topic (async streaming).

        Args:
            session_id: Session ID
            topic_filter: Topic filter (supports wildcards +, #)
            qos: QoS level

        Yields:
            Message dictionaries
        """
        try:
            config = self._get_client_config()
            async with aiomqtt.Client(**config) as client:
                await client.subscribe(topic_filter, qos=qos)

                async for message in client.messages:
                    # Update session stats
                    if session_id in self._sessions:
                        self._sessions[session_id]['messages_received'] += 1

                    yield {
                        'topic': str(message.topic),
                        'payload': message.payload,
                        'qos': message.qos,
                        'retained': message.retain,
                        'timestamp': datetime.utcnow().isoformat()
                    }

        except Exception as e:
            self.handle_error(e, "subscribe")

    async def subscribe_multiple(self, session_id: str,
                                subscriptions: List[Dict]) -> AsyncIterator[Dict]:
        """
        Subscribe to multiple topics (async streaming).

        Args:
            session_id: Session ID
            subscriptions: List of dicts with keys: topic_filter, qos

        Yields:
            Message dictionaries
        """
        try:
            config = self._get_client_config()
            async with aiomqtt.Client(**config) as client:
                for sub in subscriptions:
                    await client.subscribe(
                        sub.get('topic_filter'),
                        qos=sub.get('qos', 1)
                    )

                async for message in client.messages:
                    if session_id in self._sessions:
                        self._sessions[session_id]['messages_received'] += 1

                    yield {
                        'topic': str(message.topic),
                        'payload': message.payload,
                        'qos': message.qos,
                        'retained': message.retain,
                        'timestamp': datetime.utcnow().isoformat()
                    }

        except Exception as e:
            self.handle_error(e, "subscribe multiple")

    async def unsubscribe(self, session_id: str,
                         topic_filters: List[str]) -> Optional[int]:
        """Unsubscribe from topics."""
        try:
            # aiomqtt handles unsubscribe when context exits
            # Track subscriptions for reporting
            count = 0
            for topic in topic_filters:
                key = f"{session_id}:{topic}"
                if key in self._subscriptions:
                    del self._subscriptions[key]
                    count += 1

            return count

        except Exception as e:
            return self.handle_error(e, "unsubscribe")

    async def list_subscriptions(self, session_id: str) -> List[Dict]:
        """List active subscriptions."""
        try:
            subs = []
            for key, sub in self._subscriptions.items():
                if key.startswith(f"{session_id}:"):
                    subs.append(sub)
            return subs

        except Exception as e:
            return self.handle_error(e, "list subscriptions") or []

    # ============================================
    # Device Management
    # ============================================

    async def register_device(self, device_id: str, device_name: str,
                             device_type: str = 'sensor',
                             metadata: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """Register IoT device."""
        try:
            self._devices[device_id] = {
                'device_id': device_id,
                'device_name': device_name,
                'device_type': device_type,
                'status': 1,  # online
                'registered_at': datetime.utcnow().isoformat(),
                'last_seen': datetime.utcnow().isoformat(),
                'metadata': metadata or {},
                'subscribed_topics': [],
                'messages_sent': 0,
                'messages_received': 0
            }

            return {
                'success': True,
                'device': self._devices[device_id],
                'message': f'Device {device_id} registered'
            }

        except Exception as e:
            return self.handle_error(e, "register device")

    async def unregister_device(self, device_id: str) -> bool:
        """Unregister device."""
        try:
            if device_id in self._devices:
                del self._devices[device_id]
                return True
            return False

        except Exception as e:
            self.handle_error(e, "unregister device")
            return False

    async def list_devices(self, status: Optional[int] = None,
                          page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """List registered devices."""
        try:
            devices = list(self._devices.values())

            if status is not None:
                devices = [d for d in devices if d.get('status') == status]

            start = (page - 1) * page_size
            end = start + page_size
            paged_devices = devices[start:end]

            return {
                'devices': paged_devices,
                'total_count': len(devices),
                'page': page,
                'page_size': page_size
            }

        except Exception as e:
            return self.handle_error(e, "list devices")

    async def get_device_info(self, device_id: str) -> Optional[Dict]:
        """Get device information."""
        try:
            return self._devices.get(device_id)

        except Exception as e:
            return self.handle_error(e, "get device info")

    async def update_device_status(self, device_id: str, status: int,
                                  metadata: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """Update device status."""
        try:
            if device_id in self._devices:
                self._devices[device_id]['status'] = status
                self._devices[device_id]['last_seen'] = datetime.utcnow().isoformat()
                if metadata:
                    self._devices[device_id]['metadata'].update(metadata)

                return {'success': True, 'device': self._devices[device_id]}
            return None

        except Exception as e:
            return self.handle_error(e, "update device status")

    # ============================================
    # Topic Management
    # ============================================

    async def get_topic_info(self, topic: str) -> Optional[Dict]:
        """Get topic information."""
        try:
            # Topic info is tracked at the broker level
            # Return basic structure
            return {
                'topic': topic,
                'subscriber_count': 0,
                'message_count': 0,
                'last_message_time': '',
                'has_retained_message': False
            }

        except Exception as e:
            return self.handle_error(e, "get topic info")

    async def list_topics(self, prefix: str = '', page: int = 1,
                         page_size: int = 50) -> Optional[Dict]:
        """List topics."""
        try:
            # Topics are dynamic in MQTT - return tracked topics
            return {
                'topics': [],
                'total_count': 0
            }

        except Exception as e:
            return self.handle_error(e, "list topics")

    async def validate_topic(self, topic: str,
                            allow_wildcards: bool = False) -> Optional[Dict]:
        """Validate topic name."""
        try:
            # Basic MQTT topic validation
            valid = True
            message = 'Valid topic'

            if not topic:
                valid = False
                message = 'Topic cannot be empty'
            elif topic.startswith('/'):
                valid = False
                message = 'Topic should not start with /'
            elif not allow_wildcards and ('+' in topic or '#' in topic):
                valid = False
                message = 'Wildcards not allowed'
            elif '#' in topic and not topic.endswith('#'):
                valid = False
                message = '# wildcard must be at the end'

            return {'valid': valid, 'message': message}

        except Exception as e:
            return self.handle_error(e, "validate topic")

    # ============================================
    # Retained Messages
    # ============================================

    async def set_retained_message(self, topic: str, payload: bytes,
                                  qos: int = 1) -> bool:
        """Set retained message."""
        try:
            config = self._get_client_config()
            async with aiomqtt.Client(**config) as client:
                await client.publish(topic, payload, qos=qos, retain=True)
            return True

        except Exception as e:
            self.handle_error(e, "set retained message")
            return False

    async def get_retained_message(self, topic: str) -> Optional[Dict]:
        """Get retained message."""
        try:
            # Subscribe briefly to get retained message
            config = self._get_client_config()
            result = {'found': False}

            async with aiomqtt.Client(**config) as client:
                await client.subscribe(topic, qos=1)

                # Wait briefly for retained message
                try:
                    async with asyncio.timeout(1.0):
                        async for message in client.messages:
                            if message.retain:
                                result = {
                                    'found': True,
                                    'topic': str(message.topic),
                                    'payload': message.payload,
                                    'qos': message.qos,
                                    'timestamp': datetime.utcnow().isoformat()
                                }
                            break
                except asyncio.TimeoutError:
                    pass

            return result

        except Exception as e:
            return self.handle_error(e, "get retained message")

    async def delete_retained_message(self, topic: str) -> bool:
        """Delete retained message."""
        try:
            # Send empty message to clear retained
            config = self._get_client_config()
            async with aiomqtt.Client(**config) as client:
                await client.publish(topic, b'', qos=1, retain=True)
            return True

        except Exception as e:
            self.handle_error(e, "delete retained message")
            return False

    # ============================================
    # Statistics & Monitoring
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get statistics."""
        try:
            online_devices = len([d for d in self._devices.values() if d.get('status') == 1])

            return {
                'total_devices': len(self._devices),
                'online_devices': online_devices,
                'total_topics': 0,
                'total_subscriptions': len(self._subscriptions),
                'messages_sent_today': self._message_counts.get('sent', 0),
                'messages_received_today': self._message_counts.get('received', 0),
                'active_sessions': len(self._sessions)
            }

        except Exception as e:
            return self.handle_error(e, "get statistics")

    async def get_device_metrics(self, device_id: str,
                                start_time=None, end_time=None) -> Optional[Dict]:
        """Get device metrics."""
        try:
            device = self._devices.get(device_id, {})

            return {
                'device_id': device_id,
                'messages_sent': device.get('messages_sent', 0),
                'messages_received': device.get('messages_received', 0),
                'bytes_sent': 0,
                'bytes_received': 0,
                'message_rate': [],
                'error_rate': []
            }

        except Exception as e:
            return self.handle_error(e, "get device metrics")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def publish_many_concurrent(self, session_id: str,
                                     messages: List[Dict]) -> List[Optional[Dict]]:
        """Publish multiple messages concurrently."""
        tasks = [
            self.publish(
                session_id,
                msg.get('topic'),
                msg.get('payload', b''),
                msg.get('qos', 1),
                msg.get('retained', False)
            )
            for msg in messages
        ]
        return await asyncio.gather(*tasks)

    async def register_devices_concurrent(self,
                                         devices: List[Dict]) -> List[Optional[Dict]]:
        """Register multiple devices concurrently."""
        tasks = [
            self.register_device(
                d.get('device_id'),
                d.get('device_name'),
                d.get('device_type', 'sensor'),
                d.get('metadata')
            )
            for d in devices
        ]
        return await asyncio.gather(*tasks)


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncMQTTClient(
            host='localhost',
            port=1883,
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Connect
            session = await client.mqtt_connect('test-client')
            session_id = session['session_id']
            print(f"Session: {session}")

            # Publish
            result = await client.publish(session_id, 'test/topic', b'Hello MQTT!')
            print(f"Publish: {result}")

            # Get stats
            stats = await client.get_statistics()
            print(f"Stats: {stats}")

            # Disconnect
            await client.disconnect(session_id)

    asyncio.run(main())
