#!/usr/bin/env python3
"""
Async MQTT gRPC Client
High-performance async MQTT client using grpc.aio

Performance Benefits:
- True async I/O for IoT messaging
- High-throughput concurrent publishing
- Non-blocking streaming subscriptions
- Efficient device management
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, AsyncIterator, Callable, TYPE_CHECKING
from google.protobuf.struct_pb2 import Struct
from .async_base_client import AsyncBaseGRPCClient
from .proto import mqtt_service_pb2, mqtt_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)


class AsyncMQTTClient(AsyncBaseGRPCClient):
    """Async MQTT gRPC client for high-throughput IoT messaging."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        lazy_connect: bool = True,
        enable_compression: bool = True,
        enable_retry: bool = True,
        consul_registry: Optional['ConsulRegistry'] = None,
        service_name_override: Optional[str] = None
    ):
        """
        Initialize async MQTT client.

        Args:
            host: Service address (optional)
            port: Service port (optional)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery
            service_name_override: Override service name for Consul lookup
        """
        super().__init__(
            host=host,
            port=port,
            user_id=user_id,
            lazy_connect=lazy_connect,
            enable_compression=enable_compression,
            enable_retry=enable_retry,
            consul_registry=consul_registry,
            service_name_override=service_name_override
        )
        self.organization_id = organization_id or 'default-org'

    def _create_stub(self):
        """Create MQTT service stub."""
        return mqtt_service_pb2_grpc.MQTTServiceStub(self.channel)

    def service_name(self) -> str:
        return "MQTT"

    def default_port(self) -> int:
        return 50053

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.MQTTHealthCheckRequest(deep_check=deep_check)
            response = await self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'broker_status': response.broker_status,
                'active_connections': response.active_connections,
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Connection Management
    # ============================================

    async def mqtt_connect(self, client_id: str, username: str = '',
                          password: str = '') -> Optional[Dict]:
        """Connect to MQTT service."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ConnectRequest(
                client_id=client_id,
                user_id=self.user_id,
                username=username,
                password=password
            )

            response = await self.stub.Connect(request)

            if response.success:
                return {
                    'success': True,
                    'session_id': response.session_id,
                    'message': response.message
                }
            return None

        except Exception as e:
            return self.handle_error(e, "connect")

    async def disconnect(self, session_id: str) -> Optional[Dict]:
        """Disconnect from MQTT service."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.DisconnectRequest(
                session_id=session_id,
                user_id=self.user_id
            )

            response = await self.stub.Disconnect(request)

            if response.success:
                return {'success': True, 'message': response.message}
            return None

        except Exception as e:
            return self.handle_error(e, "disconnect")

    async def get_connection_status(self, session_id: str) -> Optional[Dict]:
        """Get connection status."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ConnectionStatusRequest(
                session_id=session_id,
                user_id=self.user_id
            )

            response = await self.stub.GetConnectionStatus(request)

            return {
                'connected': response.connected,
                'connected_at': response.connected_at,
                'messages_sent': response.messages_sent,
                'messages_received': response.messages_received
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
            await self._ensure_connected()
            request = mqtt_service_pb2.PublishRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic=topic,
                payload=payload,
                qos=qos,
                retained=retained
            )

            response = await self.stub.Publish(request)

            if response.success:
                return {'success': True, 'message_id': response.message_id}
            return None

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
            await self._ensure_connected()

            publish_requests = []
            for msg in messages:
                pub_req = mqtt_service_pb2.PublishRequest(
                    user_id=self.user_id,
                    session_id=session_id,
                    topic=msg.get('topic'),
                    payload=msg.get('payload', b''),
                    qos=msg.get('qos', 1),
                    retained=msg.get('retained', False)
                )
                publish_requests.append(pub_req)

            request = mqtt_service_pb2.PublishBatchRequest(
                user_id=self.user_id,
                session_id=session_id,
                messages=publish_requests
            )

            response = await self.stub.PublishBatch(request)

            if response.success:
                return {
                    'success': True,
                    'published_count': response.published_count,
                    'failed_count': response.failed_count,
                    'message_ids': list(response.message_ids),
                    'errors': list(response.errors)
                }
            return None

        except Exception as e:
            return self.handle_error(e, "publish batch")

    async def publish_json(self, session_id: str, topic: str, data: Dict,
                          qos: int = 1, retained: bool = False) -> Optional[Dict]:
        """Publish JSON message."""
        try:
            await self._ensure_connected()

            struct_data = Struct()
            struct_data.update(data)

            request = mqtt_service_pb2.PublishJSONRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic=topic,
                data=struct_data,
                qos=qos,
                retained=retained
            )

            response = await self.stub.PublishJSON(request)

            if response.success:
                return {'success': True, 'message_id': response.message_id}
            return None

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
            await self._ensure_connected()
            request = mqtt_service_pb2.SubscribeRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic_filter=topic_filter,
                qos=qos
            )

            async for message in self.stub.Subscribe(request):
                yield {
                    'topic': message.topic,
                    'payload': message.payload,
                    'qos': message.qos,
                    'retained': message.retained,
                    'timestamp': message.timestamp
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
            await self._ensure_connected()

            topic_subs = []
            for sub in subscriptions:
                topic_sub = mqtt_service_pb2.TopicSubscription(
                    topic_filter=sub.get('topic_filter'),
                    qos=sub.get('qos', 1)
                )
                topic_subs.append(topic_sub)

            request = mqtt_service_pb2.SubscribeMultipleRequest(
                user_id=self.user_id,
                session_id=session_id,
                subscriptions=topic_subs
            )

            async for message in self.stub.SubscribeMultiple(request):
                yield {
                    'topic': message.topic,
                    'payload': message.payload,
                    'qos': message.qos,
                    'retained': message.retained,
                    'timestamp': message.timestamp
                }

        except Exception as e:
            self.handle_error(e, "subscribe multiple")

    async def unsubscribe(self, session_id: str,
                         topic_filters: List[str]) -> Optional[int]:
        """Unsubscribe from topics."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.UnsubscribeRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic_filters=topic_filters
            )

            response = await self.stub.Unsubscribe(request)

            if response.success:
                return response.unsubscribed_count
            return None

        except Exception as e:
            return self.handle_error(e, "unsubscribe")

    async def list_subscriptions(self, session_id: str) -> List[Dict]:
        """List active subscriptions."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ListSubscriptionsRequest(
                user_id=self.user_id,
                session_id=session_id
            )

            response = await self.stub.ListSubscriptions(request)

            subscriptions = []
            for sub in response.subscriptions:
                subscriptions.append({
                    'topic_filter': sub.topic_filter,
                    'qos': sub.qos
                })
            return subscriptions

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
            await self._ensure_connected()
            request = mqtt_service_pb2.RegisterDeviceRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                device_id=device_id,
                device_name=device_name,
                device_type=device_type,
                metadata=metadata or {}
            )

            response = await self.stub.RegisterDevice(request)

            if response.success:
                return {
                    'success': True,
                    'device': response.device,
                    'message': response.message
                }
            return None

        except Exception as e:
            return self.handle_error(e, "register device")

    async def unregister_device(self, device_id: str) -> bool:
        """Unregister device."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.UnregisterDeviceRequest(
                user_id=self.user_id,
                device_id=device_id
            )

            response = await self.stub.UnregisterDevice(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "unregister device")
            return False

    async def list_devices(self, status: Optional[int] = None,
                          page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """List registered devices."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ListDevicesRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                status=status or 0,
                page=page,
                page_size=page_size
            )

            response = await self.stub.ListDevices(request)

            devices = []
            for device in response.devices:
                devices.append({
                    'device_id': device.device_id,
                    'device_name': device.device_name,
                    'device_type': device.device_type,
                    'status': device.status,
                    'registered_at': device.registered_at,
                    'last_seen': device.last_seen
                })

            return {
                'devices': devices,
                'total_count': response.total_count,
                'page': response.page,
                'page_size': response.page_size
            }

        except Exception as e:
            return self.handle_error(e, "list devices")

    async def get_device_info(self, device_id: str) -> Optional[Dict]:
        """Get device information."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.GetDeviceInfoRequest(
                user_id=self.user_id,
                device_id=device_id
            )

            response = await self.stub.GetDeviceInfo(request)

            device = response.device
            return {
                'device_id': device.device_id,
                'device_name': device.device_name,
                'device_type': device.device_type,
                'status': device.status,
                'registered_at': device.registered_at,
                'last_seen': device.last_seen,
                'metadata': dict(device.metadata),
                'subscribed_topics': list(device.subscribed_topics),
                'messages_sent': device.messages_sent,
                'messages_received': device.messages_received
            }

        except Exception as e:
            return self.handle_error(e, "get device info")

    async def update_device_status(self, device_id: str, status: int,
                                  metadata: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """Update device status."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.UpdateDeviceStatusRequest(
                user_id=self.user_id,
                device_id=device_id,
                status=status,
                metadata=metadata or {}
            )

            response = await self.stub.UpdateDeviceStatus(request)

            if response.success:
                return {'success': True, 'device': response.device}
            return None

        except Exception as e:
            return self.handle_error(e, "update device status")

    # ============================================
    # Topic Management
    # ============================================

    async def get_topic_info(self, topic: str) -> Optional[Dict]:
        """Get topic information."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.GetTopicInfoRequest(
                user_id=self.user_id,
                topic=topic
            )

            response = await self.stub.GetTopicInfo(request)

            topic_info = response.topic_info
            return {
                'topic': topic_info.topic,
                'subscriber_count': topic_info.subscriber_count,
                'message_count': topic_info.message_count,
                'last_message_time': topic_info.last_message_time,
                'has_retained_message': topic_info.has_retained_message
            }

        except Exception as e:
            return self.handle_error(e, "get topic info")

    async def list_topics(self, prefix: str = '', page: int = 1,
                         page_size: int = 50) -> Optional[Dict]:
        """List topics."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ListTopicsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                prefix=prefix,
                page=page,
                page_size=page_size
            )

            response = await self.stub.ListTopics(request)

            topics = []
            for topic_info in response.topics:
                topics.append({
                    'topic': topic_info.topic,
                    'subscriber_count': topic_info.subscriber_count,
                    'message_count': topic_info.message_count
                })

            return {
                'topics': topics,
                'total_count': response.total_count
            }

        except Exception as e:
            return self.handle_error(e, "list topics")

    async def validate_topic(self, topic: str,
                            allow_wildcards: bool = False) -> Optional[Dict]:
        """Validate topic name."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ValidateTopicRequest(
                topic=topic,
                allow_wildcards=allow_wildcards
            )

            response = await self.stub.ValidateTopic(request)

            return {
                'valid': response.valid,
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "validate topic")

    # ============================================
    # Retained Messages
    # ============================================

    async def set_retained_message(self, topic: str, payload: bytes,
                                  qos: int = 1) -> bool:
        """Set retained message."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.SetRetainedMessageRequest(
                user_id=self.user_id,
                topic=topic,
                payload=payload,
                qos=qos
            )

            response = await self.stub.SetRetainedMessage(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set retained message")
            return False

    async def get_retained_message(self, topic: str) -> Optional[Dict]:
        """Get retained message."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.GetRetainedMessageRequest(
                user_id=self.user_id,
                topic=topic
            )

            response = await self.stub.GetRetainedMessage(request)

            if response.found:
                message = response.message
                return {
                    'found': True,
                    'topic': message.topic,
                    'payload': message.payload,
                    'qos': message.qos,
                    'timestamp': message.timestamp
                }
            return {'found': False}

        except Exception as e:
            return self.handle_error(e, "get retained message")

    async def delete_retained_message(self, topic: str) -> bool:
        """Delete retained message."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.DeleteRetainedMessageRequest(
                user_id=self.user_id,
                topic=topic
            )

            response = await self.stub.DeleteRetainedMessage(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete retained message")
            return False

    # ============================================
    # Statistics & Monitoring
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get statistics."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = await self.stub.GetStatistics(request)

            return {
                'total_devices': response.total_devices,
                'online_devices': response.online_devices,
                'total_topics': response.total_topics,
                'total_subscriptions': response.total_subscriptions,
                'messages_sent_today': response.messages_sent_today,
                'messages_received_today': response.messages_received_today,
                'active_sessions': response.active_sessions
            }

        except Exception as e:
            return self.handle_error(e, "get statistics")

    async def get_device_metrics(self, device_id: str,
                                start_time=None, end_time=None) -> Optional[Dict]:
        """Get device metrics."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.GetDeviceMetricsRequest(
                user_id=self.user_id,
                device_id=device_id,
                start_time=start_time,
                end_time=end_time
            )

            response = await self.stub.GetDeviceMetrics(request)

            return {
                'device_id': response.device_id,
                'messages_sent': response.messages_sent,
                'messages_received': response.messages_received,
                'bytes_sent': response.bytes_sent,
                'bytes_received': response.bytes_received,
                'message_rate': [(p.timestamp, p.value) for p in response.message_rate],
                'error_rate': [(p.timestamp, p.value) for p in response.error_rate]
            }

        except Exception as e:
            return self.handle_error(e, "get device metrics")

    # ============================================
    # Device Message Streaming
    # ============================================

    async def subscribe_device_messages(
        self,
        organization_id: Optional[str] = None,
        message_types: Optional[List[int]] = None,
        device_ids: Optional[List[str]] = None,
        topic_patterns: Optional[List[str]] = None
    ) -> AsyncIterator[Dict]:
        """
        Subscribe to all device messages (async streaming).

        Args:
            organization_id: Organization ID (optional, for filtering)
            message_types: Message types to subscribe (1=TELEMETRY, 2=STATUS, etc.)
            device_ids: Specific device IDs to subscribe
            topic_patterns: Custom topic patterns

        Yields:
            Device message dictionaries
        """
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.SubscribeDeviceMessagesRequest(
                user_id=self.user_id,
                organization_id=organization_id or '',
                message_types=message_types or [],
                device_ids=device_ids or [],
                topic_patterns=topic_patterns or []
            )

            async for message in self.stub.SubscribeDeviceMessages(request):
                yield {
                    'device_id': message.device_id,
                    'message_type': message.message_type,
                    'topic': message.topic,
                    'payload': message.payload,
                    'timestamp': message.timestamp,
                    'metadata': dict(message.metadata)
                }

        except Exception as e:
            self.handle_error(e, "subscribe device messages")

    # ============================================
    # Webhook Management
    # ============================================

    async def register_webhook(
        self,
        url: str,
        organization_id: Optional[str] = None,
        message_types: Optional[List[int]] = None,
        device_ids: Optional[List[str]] = None,
        topic_patterns: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        secret: Optional[str] = None
    ) -> Optional[Dict]:
        """Register webhook for device messages."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.RegisterWebhookRequest(
                user_id=self.user_id,
                organization_id=organization_id or '',
                url=url,
                message_types=message_types or [],
                device_ids=device_ids or [],
                topic_patterns=topic_patterns or [],
                headers=headers or {},
                secret=secret or ''
            )

            response = await self.stub.RegisterWebhook(request)

            if response.success:
                return {
                    'success': True,
                    'webhook_id': response.webhook_id,
                    'webhook': {
                        'webhook_id': response.webhook.webhook_id,
                        'url': response.webhook.url,
                        'enabled': response.webhook.enabled,
                        'success_count': response.webhook.success_count,
                        'failure_count': response.webhook.failure_count,
                    }
                }
            return None

        except Exception as e:
            return self.handle_error(e, "register webhook")

    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister webhook."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.UnregisterWebhookRequest(
                user_id=self.user_id,
                webhook_id=webhook_id
            )

            response = await self.stub.UnregisterWebhook(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "unregister webhook")
            return False

    async def list_webhooks(self, organization_id: Optional[str] = None,
                           include_disabled: bool = False) -> List[Dict]:
        """List registered webhooks."""
        try:
            await self._ensure_connected()
            request = mqtt_service_pb2.ListWebhooksRequest(
                user_id=self.user_id,
                organization_id=organization_id or '',
                include_disabled=include_disabled
            )

            response = await self.stub.ListWebhooks(request)

            webhooks = []
            for webhook in response.webhooks:
                webhooks.append({
                    'webhook_id': webhook.webhook_id,
                    'url': webhook.url,
                    'enabled': webhook.enabled,
                    'message_types': list(webhook.message_types),
                    'device_ids': list(webhook.device_ids),
                    'topic_patterns': list(webhook.topic_patterns),
                    'success_count': webhook.success_count,
                    'failure_count': webhook.failure_count,
                })
            return webhooks

        except Exception as e:
            return self.handle_error(e, "list webhooks") or []

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
