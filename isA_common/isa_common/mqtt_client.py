#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT gRPC Client
"""

from typing import List, Dict, Optional, Callable
from .base_client import BaseGRPCClient
from .proto import mqtt_service_pb2, mqtt_service_pb2_grpc


class MQTTClient(BaseGRPCClient):
    """MQTT gRPC client"""

    def __init__(self, host: str = 'localhost', port: int = 50053, user_id: Optional[str] = None,
                 organization_id: Optional[str] = None, lazy_connect: bool = True,
                 enable_compression: bool = True, enable_retry: bool = True):
        """
        Initialize MQTT client

        Args:
            host: Service address (default: localhost)
            port: Service port (default: 50053)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
        """
        super().__init__(host, port, user_id, lazy_connect, enable_compression, enable_retry)
        self.organization_id = organization_id or 'default-org'

    def _create_stub(self):
        """Create MQTT service stub"""
        return mqtt_service_pb2_grpc.MQTTServiceStub(self.channel)

    def service_name(self) -> str:
        return "MQTT"

    def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.MQTTHealthCheckRequest(deep_check=deep_check)
            response = self.stub.HealthCheck(request)

            print(f"✅ [MQTT] Healthy: {response.healthy}")
            print(f"   Broker status: {response.broker_status}")
            print(f"   Active connections: {response.active_connections}")

            return {
                'healthy': response.healthy,
                'broker_status': response.broker_status,
                'active_connections': response.active_connections,
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    def connect(self, client_id: str, username: str = '', password: str = '') -> Optional[Dict]:
        """Connect to MQTT service"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.ConnectRequest(
                client_id=client_id,
                user_id=self.user_id,
                username=username,
                password=password
            )

            response = self.stub.Connect(request)

            if response.success:
                print(f"✅ [MQTT] Connected: {client_id}")
                print(f"   Session ID: {response.session_id}")
                return {
                    'success': True,
                    'session_id': response.session_id,
                    'message': response.message
                }
            else:
                print(f"⚠️  [MQTT] Connection failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "connect")

    def disconnect(self, session_id: str) -> Optional[Dict]:
        """Disconnect"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.DisconnectRequest(
                session_id=session_id,
                user_id=self.user_id
            )

            response = self.stub.Disconnect(request)

            if response.success:
                print(f"✅ [MQTT] Disconnected")
                return {
                    'success': True,
                    'message': response.message
                }
            else:
                print(f"⚠️  [MQTT] Disconnect failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "disconnect")

    def get_connection_status(self, session_id: str) -> Optional[Dict]:
        """Get connection status"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.ConnectionStatusRequest(
                session_id=session_id,
                user_id=self.user_id
            )

            response = self.stub.GetConnectionStatus(request)

            print(f"✅ [MQTT] Connection status: {'Connected' if response.connected else 'Disconnected'}")
            print(f"   Messages sent: {response.messages_sent}")
            print(f"   Messages received: {response.messages_received}")

            return {
                'connected': response.connected,
                'connected_at': response.connected_at,
                'messages_sent': response.messages_sent,
                'messages_received': response.messages_received
            }

        except Exception as e:
            return self.handle_error(e, "get connection status")

    def publish(self, session_id: str, topic: str, payload: bytes, qos: int = 1, retained: bool = False) -> Optional[Dict]:
        """Publish message"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.PublishRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic=topic,
                payload=payload,
                qos=qos,
                retained=retained
            )

            response = self.stub.Publish(request)

            if response.success:
                print(f"✅ [MQTT] Message published: {topic}")
                return {
                    'success': True,
                    'message_id': response.message_id
                }
            else:
                print(f"⚠️  [MQTT] Publish failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "publish")

    def publish_batch(self, session_id: str, messages: List[Dict]) -> Optional[Dict]:
        """
        Publish multiple messages in batch
        
        Args:
            session_id: Session ID
            messages: List of dicts with keys: topic, payload, qos, retained
        """
        try:
            self._ensure_connected()
            
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

            response = self.stub.PublishBatch(request)

            if response.success:
                print(f"✅ [MQTT] Batch published: {response.published_count}/{len(messages)} messages")
                return {
                    'success': True,
                    'published_count': response.published_count,
                    'failed_count': response.failed_count,
                    'message_ids': list(response.message_ids),
                    'errors': list(response.errors)
                }
            else:
                print(f"⚠️  [MQTT] Batch publish had failures: {response.failed_count}")
                return None

        except Exception as e:
            return self.handle_error(e, "publish batch")

    def publish_json(self, session_id: str, topic: str, data: Dict, qos: int = 1, retained: bool = False) -> Optional[Dict]:
        """Publish JSON message"""
        try:
            self._ensure_connected()
            
            from google.protobuf.struct_pb2 import Struct
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

            response = self.stub.PublishJSON(request)

            if response.success:
                print(f"✅ [MQTT] JSON message published: {topic}")
                return {
                    'success': True,
                    'message_id': response.message_id
                }
            else:
                print(f"⚠️  [MQTT] JSON publish failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "publish JSON")

    def subscribe(self, session_id: str, topic_filter: str, qos: int = 1, callback=None):
        """
        Subscribe to topic (streaming)
        
        Args:
            session_id: Session ID
            topic_filter: Topic filter (supports wildcards +, #)
            qos: QoS level
            callback: Function to call for each message (takes topic, payload, qos, retained, timestamp)
        """
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.SubscribeRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic_filter=topic_filter,
                qos=qos
            )

            print(f"✅ [MQTT] Subscribing to: {topic_filter}")
            
            for message in self.stub.Subscribe(request):
                if callback:
                    callback(message.topic, message.payload, message.qos, 
                            message.retained, message.timestamp)
                else:
                    print(f"📩 [MQTT] Message from {message.topic}: {message.payload[:50]}")

        except Exception as e:
            self.handle_error(e, "subscribe")

    def subscribe_multiple(self, session_id: str, subscriptions: List[Dict], callback=None):
        """
        Subscribe to multiple topics
        
        Args:
            session_id: Session ID
            subscriptions: List of dicts with keys: topic_filter, qos
            callback: Function to call for each message
        """
        try:
            self._ensure_connected()
            
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

            print(f"✅ [MQTT] Subscribing to {len(subscriptions)} topics")
            
            for message in self.stub.SubscribeMultiple(request):
                if callback:
                    callback(message.topic, message.payload, message.qos,
                            message.retained, message.timestamp)
                else:
                    print(f"📩 [MQTT] Message from {message.topic}: {message.payload[:50]}")

        except Exception as e:
            self.handle_error(e, "subscribe multiple")

    def unsubscribe(self, session_id: str, topic_filters: List[str]) -> Optional[int]:
        """Unsubscribe from topics"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.UnsubscribeRequest(
                user_id=self.user_id,
                session_id=session_id,
                topic_filters=topic_filters
            )

            response = self.stub.Unsubscribe(request)

            if response.success:
                print(f"✅ [MQTT] Unsubscribed from {response.unsubscribed_count} topics")
                return response.unsubscribed_count
            else:
                print(f"⚠️  [MQTT] Unsubscribe failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "unsubscribe")

    def list_subscriptions(self, session_id: str) -> List[Dict]:
        """List active subscriptions"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.ListSubscriptionsRequest(
                user_id=self.user_id,
                session_id=session_id
            )

            response = self.stub.ListSubscriptions(request)

            subscriptions = []
            for sub in response.subscriptions:
                subscriptions.append({
                    'topic_filter': sub.topic_filter,
                    'qos': sub.qos
                })
            
            print(f"✅ [MQTT] Listed {len(subscriptions)} subscriptions")
            return subscriptions

        except Exception as e:
            return self.handle_error(e, "list subscriptions") or []

    # ============================================
    # Device Management
    # ============================================

    def register_device(self, device_id: str, device_name: str, device_type: str = 'sensor',
                       metadata: Dict[str, str] = None) -> Optional[Dict]:
        """Register IoT device"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.RegisterDeviceRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                device_id=device_id,
                device_name=device_name,
                device_type=device_type,
                metadata=metadata or {}
            )

            response = self.stub.RegisterDevice(request)

            if response.success:
                print(f"✅ [MQTT] Device registered: {device_id} ({device_type})")
                return {
                    'success': True,
                    'device': response.device,
                    'message': response.message
                }
            else:
                print(f"⚠️  [MQTT] Device registration failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "register device")

    def unregister_device(self, device_id: str) -> bool:
        """Unregister device"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.UnregisterDeviceRequest(
                user_id=self.user_id,
                device_id=device_id
            )

            response = self.stub.UnregisterDevice(request)

            if response.success:
                print(f"✅ [MQTT] Device unregistered: {device_id}")
                return True
            else:
                print(f"⚠️  [MQTT] Unregister failed: {response.message}")
                return False

        except Exception as e:
            self.handle_error(e, "unregister device")
            return False

    def list_devices(self, status: int = None, page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """List registered devices"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.ListDevicesRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                status=status or 0,
                page=page,
                page_size=page_size
            )

            response = self.stub.ListDevices(request)

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
            
            print(f"✅ [MQTT] Listed {len(devices)} devices (total: {response.total_count})")
            return {
                'devices': devices,
                'total_count': response.total_count,
                'page': response.page,
                'page_size': response.page_size
            }

        except Exception as e:
            return self.handle_error(e, "list devices")

    def get_device_info(self, device_id: str) -> Optional[Dict]:
        """Get device information"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.GetDeviceInfoRequest(
                user_id=self.user_id,
                device_id=device_id
            )

            response = self.stub.GetDeviceInfo(request)

            device = response.device
            info = {
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
            
            print(f"✅ [MQTT] Device info: {device_id}")
            print(f"   Type: {device.device_type}, Status: {device.status}")
            return info

        except Exception as e:
            return self.handle_error(e, "get device info")

    def update_device_status(self, device_id: str, status: int, metadata: Dict[str, str] = None) -> Optional[Dict]:
        """Update device status"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.UpdateDeviceStatusRequest(
                user_id=self.user_id,
                device_id=device_id,
                status=status,
                metadata=metadata or {}
            )

            response = self.stub.UpdateDeviceStatus(request)

            if response.success:
                print(f"✅ [MQTT] Device status updated: {device_id} -> {status}")
                return {'success': True, 'device': response.device}
            else:
                print(f"⚠️  [MQTT] Status update failed")
                return None

        except Exception as e:
            return self.handle_error(e, "update device status")

    # ============================================
    # Topic Management
    # ============================================

    def get_topic_info(self, topic: str) -> Optional[Dict]:
        """Get topic information"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.GetTopicInfoRequest(
                user_id=self.user_id,
                topic=topic
            )

            response = self.stub.GetTopicInfo(request)

            topic_info = response.topic_info
            info = {
                'topic': topic_info.topic,
                'subscriber_count': topic_info.subscriber_count,
                'message_count': topic_info.message_count,
                'last_message_time': topic_info.last_message_time,
                'has_retained_message': topic_info.has_retained_message
            }
            
            print(f"✅ [MQTT] Topic info: {topic}")
            print(f"   Subscribers: {topic_info.subscriber_count}")
            print(f"   Messages: {topic_info.message_count}")
            return info

        except Exception as e:
            return self.handle_error(e, "get topic info")

    def list_topics(self, prefix: str = '', page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """List topics"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.ListTopicsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                prefix=prefix,
                page=page,
                page_size=page_size
            )

            response = self.stub.ListTopics(request)

            topics = []
            for topic_info in response.topics:
                topics.append({
                    'topic': topic_info.topic,
                    'subscriber_count': topic_info.subscriber_count,
                    'message_count': topic_info.message_count
                })
            
            print(f"✅ [MQTT] Listed {len(topics)} topics (total: {response.total_count})")
            return {
                'topics': topics,
                'total_count': response.total_count
            }

        except Exception as e:
            return self.handle_error(e, "list topics")

    def validate_topic(self, topic: str, allow_wildcards: bool = False) -> Optional[Dict]:
        """Validate topic name"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.ValidateTopicRequest(
                topic=topic,
                allow_wildcards=allow_wildcards
            )

            response = self.stub.ValidateTopic(request)

            if response.valid:
                print(f"✅ [MQTT] Topic valid: {topic}")
            else:
                print(f"⚠️  [MQTT] Topic invalid: {response.message}")

            return {
                'valid': response.valid,
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "validate topic")

    # ============================================
    # Retained Messages
    # ============================================

    def set_retained_message(self, topic: str, payload: bytes, qos: int = 1) -> bool:
        """Set retained message"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.SetRetainedMessageRequest(
                user_id=self.user_id,
                topic=topic,
                payload=payload,
                qos=qos
            )

            response = self.stub.SetRetainedMessage(request)

            if response.success:
                print(f"✅ [MQTT] Retained message set: {topic}")
                return True
            else:
                print(f"⚠️  [MQTT] Set retained message failed: {response.message}")
                return False

        except Exception as e:
            self.handle_error(e, "set retained message")
            return False

    def get_retained_message(self, topic: str) -> Optional[Dict]:
        """Get retained message"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.GetRetainedMessageRequest(
                user_id=self.user_id,
                topic=topic
            )

            response = self.stub.GetRetainedMessage(request)

            if response.found:
                message = response.message
                print(f"✅ [MQTT] Retained message found: {topic}")
                return {
                    'found': True,
                    'topic': message.topic,
                    'payload': message.payload,
                    'qos': message.qos,
                    'timestamp': message.timestamp
                }
            else:
                print(f"⚠️  [MQTT] No retained message on topic: {topic}")
                return {'found': False}

        except Exception as e:
            return self.handle_error(e, "get retained message")

    def delete_retained_message(self, topic: str) -> bool:
        """Delete retained message"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.DeleteRetainedMessageRequest(
                user_id=self.user_id,
                topic=topic
            )

            response = self.stub.DeleteRetainedMessage(request)

            if response.success:
                print(f"✅ [MQTT] Retained message deleted: {topic}")
                return True
            else:
                print(f"⚠️  [MQTT] Delete retained message failed: {response.message}")
                return False

        except Exception as e:
            self.handle_error(e, "delete retained message")
            return False

    # ============================================
    # Monitoring Operations
    # ============================================

    def get_statistics(self) -> Optional[Dict]:
        """Get statistics"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.GetStatistics(request)

            stats = {
                'total_devices': response.total_devices,
                'online_devices': response.online_devices,
                'total_topics': response.total_topics,
                'total_subscriptions': response.total_subscriptions,
                'messages_sent_today': response.messages_sent_today,
                'messages_received_today': response.messages_received_today,
                'active_sessions': response.active_sessions
            }

            print(f"✅ [MQTT] Statistics:")
            print(f"   Total devices: {stats['total_devices']}")
            print(f"   Online devices: {stats['online_devices']}")
            print(f"   Total topics: {stats['total_topics']}")
            print(f"   Active sessions: {stats['active_sessions']}")

            return stats

        except Exception as e:
            return self.handle_error(e, "get statistics")

    def get_device_metrics(self, device_id: str, start_time=None, end_time=None) -> Optional[Dict]:
        """Get device metrics"""
        try:
            self._ensure_connected()
            request = mqtt_service_pb2.GetDeviceMetricsRequest(
                user_id=self.user_id,
                device_id=device_id,
                start_time=start_time,
                end_time=end_time
            )

            response = self.stub.GetDeviceMetrics(request)

            metrics = {
                'device_id': response.device_id,
                'messages_sent': response.messages_sent,
                'messages_received': response.messages_received,
                'bytes_sent': response.bytes_sent,
                'bytes_received': response.bytes_received,
                'message_rate': [(p.timestamp, p.value) for p in response.message_rate],
                'error_rate': [(p.timestamp, p.value) for p in response.error_rate]
            }
            
            print(f"✅ [MQTT] Device metrics: {device_id}")
            print(f"   Messages: {response.messages_sent} sent, {response.messages_received} received")
            print(f"   Bytes: {response.bytes_sent} sent, {response.bytes_received} received")
            return metrics

        except Exception as e:
            return self.handle_error(e, "get device metrics")


# Quick test
if __name__ == '__main__':
    with MQTTClient(host='localhost', port=50053, user_id='test_user', organization_id='test_org') as client:
        # Health check
        client.health_check()

        # Connect
        conn = client.connect('test-client-001')
        
        if conn:
            session_id = conn['session_id']
            
            # Validate topic
            client.validate_topic('sensors/temperature')

            # Publish message
            client.publish(session_id, 'sensors/temperature', b'25.5', qos=1)

            # Get statistics
            client.get_statistics()

            # Disconnect
            client.disconnect(session_id)
