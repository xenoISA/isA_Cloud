#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NATS gRPC Client
"""

from typing import List, Dict, Optional, Callable, TYPE_CHECKING
from .base_client import BaseGRPCClient
from .proto import nats_service_pb2, nats_service_pb2_grpc
from google.protobuf.duration_pb2 import Duration

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class NATSClient(BaseGRPCClient):
    """NATS gRPC client"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 organization_id: Optional[str] = None, lazy_connect: bool = True,
                 enable_compression: bool = False, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        Initialize NATS client

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: False)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'nats')
        """
        # Let BaseGRPCClient handle Consul discovery and fallback defaults
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
        """Create NATS service stub"""
        return nats_service_pb2_grpc.NATSServiceStub(self.channel)

    def service_name(self) -> str:
        return "NATS"

    def default_port(self) -> int:
        return 50056

    def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.NATSHealthCheckRequest(deep_check=deep_check)
            response = self.stub.HealthCheck(request)

            print(f"✅ [NATS] Healthy: {response.healthy}")
            print(f"   NATS status: {response.nats_status}")
            print(f"   JetStream enabled: {response.jetstream_enabled}")
            print(f"   Connections: {response.connections}")

            return {
                'healthy': response.healthy,
                'nats_status': response.nats_status,
                'jetstream_enabled': response.jetstream_enabled,
                'connections': response.connections,
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    def publish(self, subject: str, data: bytes, headers: Optional[Dict[str, str]] = None,
                reply_to: str = '') -> Optional[Dict]:
        """Publish message to subject"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.PublishRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject,
                data=data,
                headers=headers or {},
                reply_to=reply_to
            )

            response = self.stub.Publish(request)

            if response.success:
                print(f"✅ [NATS] Message published to: {subject}")
                return {
                    'success': True,
                    'message': response.message
                }
            else:
                print(f"⚠️  [NATS] Publish failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "publish")

    def publish_batch(self, messages: List[Dict]) -> Optional[Dict]:
        """
        Batch publish multiple messages

        Args:
            messages: List of dicts with 'subject' and 'data' keys
                     e.g. [{'subject': 'test.1', 'data': b'msg1'}, ...]
        """
        try:
            self._ensure_connected()

            nats_messages = []
            for msg in messages:
                nats_msg = nats_service_pb2.NATSMessage(
                    subject=msg['subject'],
                    data=msg['data'],
                    headers=msg.get('headers', {}),
                    reply_to=msg.get('reply_to', '')
                )
                nats_messages.append(nats_msg)

            request = nats_service_pb2.PublishBatchRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                messages=nats_messages
            )

            response = self.stub.PublishBatch(request)

            if response.success:
                print(f"✅ [NATS] Batch published: {response.published_count}/{len(messages)} messages")
                return {
                    'success': True,
                    'published_count': response.published_count,
                    'errors': list(response.errors)
                }
            else:
                print(f"⚠️  [NATS] Batch publish failed")
                return None

        except Exception as e:
            return self.handle_error(e, "publish batch")

    def subscribe(self, subject: str, callback: Callable[[Dict], None],
                 queue_group: str = '', timeout_seconds: int = 60):
        """
        Subscribe to a subject and receive messages via callback

        Args:
            subject: Subject to subscribe to (supports wildcards: *, >)
            callback: Function to call for each message: callback(message_dict)
            queue_group: Optional queue group for load balancing
            timeout_seconds: How long to listen (default: 60s)

        Returns:
            Number of messages received
        """
        try:
            self._ensure_connected()

            request = nats_service_pb2.SubscribeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject,
                queue_group=queue_group
            )

            print(f"✅ [NATS] Subscribed to: {subject}")
            if queue_group:
                print(f"   Queue group: {queue_group}")

            count = 0
            # Subscribe returns a stream of messages
            for message_response in self.stub.Subscribe(request, timeout=timeout_seconds):
                msg_dict = {
                    'subject': message_response.subject,
                    'data': message_response.data,
                    'headers': dict(message_response.headers),
                    'reply_to': message_response.reply_to,
                    'sequence': message_response.sequence
                }
                callback(msg_dict)
                count += 1

            print(f"✅ [NATS] Subscription ended: {count} messages received")
            return count

        except Exception as e:
            if 'timeout' in str(e).lower():
                print(f"✅ [NATS] Subscription timeout (normal)")
                return 0
            return self.handle_error(e, "subscribe") or 0

    def unsubscribe(self, subject: str) -> Optional[Dict]:
        """Unsubscribe from a subject"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.UnsubscribeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject
            )

            response = self.stub.Unsubscribe(request)

            if response.success:
                print(f"✅ [NATS] Unsubscribed from: {subject}")
                return {'success': True}
            else:
                print(f"⚠️  [NATS] Unsubscribe failed")
                return None

        except Exception as e:
            return self.handle_error(e, "unsubscribe")

    def request(self, subject: str, data: bytes, timeout_seconds: int = 5) -> Optional[Dict]:
        """Request-reply pattern"""
        try:
            self._ensure_connected()
            timeout = Duration(seconds=timeout_seconds)

            request = nats_service_pb2.RequestRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject,
                data=data,
                timeout=timeout
            )

            response = self.stub.Request(request)

            if response.success:
                print(f"✅ [NATS] Request completed: {subject}")
                return {
                    'success': True,
                    'data': response.data,
                    'subject': response.subject
                }
            else:
                print(f"⚠️  [NATS] Request failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "request")

    def get_statistics(self) -> Optional[Dict]:
        """Get statistics"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.GetStatistics(request)

            stats = {
                'total_streams': response.total_streams,
                'total_consumers': response.total_consumers,
                'total_messages': response.total_messages,
                'total_bytes': response.total_bytes,
                'connections': response.connections,
                'in_msgs': response.in_msgs,
                'out_msgs': response.out_msgs
            }

            print(f"✅ [NATS] Statistics:")
            print(f"   Total streams: {stats['total_streams']}")
            print(f"   Total consumers: {stats['total_consumers']}")
            print(f"   Total messages: {stats['total_messages']}")
            print(f"   Connections: {stats['connections']}")

            return stats

        except Exception as e:
            return self.handle_error(e, "get statistics")

    def list_streams(self) -> List[Dict]:
        """List all streams"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.ListStreamsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.ListStreams(request)

            streams = []
            for stream in response.streams:
                streams.append({
                    'name': stream.name,
                    'subjects': list(stream.subjects),
                    'messages': stream.messages,
                    'bytes': stream.bytes
                })
            
            print(f"✅ [NATS] Found {len(streams)} streams")
            return streams

        except Exception as e:
            return self.handle_error(e, "list streams") or []

    def kv_put(self, bucket: str, key: str, value: bytes) -> Optional[Dict]:
        """Put value in KV store"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.KVPutRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                key=key,
                value=value
            )

            response = self.stub.KVPut(request)

            if response.success:
                print(f"✅ [NATS] KV put: {bucket}/{key}")
                return {
                    'success': True,
                    'revision': response.revision
                }
            else:
                print(f"⚠️  [NATS] KV put failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "kv put")

    def kv_get(self, bucket: str, key: str) -> Optional[Dict]:
        """Get value from KV store"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.KVGetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                key=key
            )

            response = self.stub.KVGet(request)

            if response.found:
                print(f"✅ [NATS] KV get: {bucket}/{key}")
                return {
                    'found': True,
                    'value': response.value,
                    'revision': response.revision
                }
            else:
                print(f"⚠️  [NATS] KV key not found: {bucket}/{key}")
                return None

        except Exception as e:
            return self.handle_error(e, "kv get")

    def kv_delete(self, bucket: str, key: str) -> Optional[Dict]:
        """Delete key from KV store"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.KVDeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                key=key
            )

            response = self.stub.KVDelete(request)

            if response.success:
                print(f"✅ [NATS] KV delete: {bucket}/{key}")
                return {'success': True}
            else:
                print(f"⚠️  [NATS] KV delete failed: {bucket}/{key}")
                return None

        except Exception as e:
            return self.handle_error(e, "kv delete")

    def kv_keys(self, bucket: str) -> List[str]:
        """List all keys in KV bucket"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.KVKeysRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket
            )

            response = self.stub.KVKeys(request)

            print(f"✅ [NATS] KV keys: {bucket} - {len(response.keys)} keys")
            return list(response.keys)

        except Exception as e:
            return self.handle_error(e, "kv keys") or []

    # JetStream Stream Management
    def create_stream(self, name: str, subjects: List[str],
                     max_msgs: int = -1, max_bytes: int = -1) -> Optional[Dict]:
        """Create JetStream stream"""
        try:
            self._ensure_connected()

            config = nats_service_pb2.StreamConfig(
                name=name,
                subjects=subjects,
                storage=nats_service_pb2.STORAGE_FILE,
                max_msgs=max_msgs,
                max_bytes=max_bytes
            )

            request = nats_service_pb2.CreateStreamRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                config=config
            )

            response = self.stub.CreateStream(request)

            if response.success:
                print(f"✅ [NATS] Stream created: {name}")
                return {
                    'success': True,
                    'stream': {
                        'name': response.stream.name,
                        'subjects': list(response.stream.config.subjects),
                        'messages': response.stream.state.messages
                    }
                }
            else:
                print(f"⚠️  [NATS] Stream creation failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "create stream")

    def delete_stream(self, stream_name: str) -> Optional[Dict]:
        """Delete JetStream stream"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.DeleteStreamRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name
            )

            response = self.stub.DeleteStream(request)

            if response.success:
                print(f"✅ [NATS] Stream deleted: {stream_name}")
                return {'success': True}
            else:
                print(f"⚠️  [NATS] Stream deletion failed")
                return None

        except Exception as e:
            return self.handle_error(e, "delete stream")

    def publish_to_stream(self, stream_name: str, subject: str, data: bytes) -> Optional[Dict]:
        """Publish message to JetStream stream"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.PublishToStreamRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                subject=subject,
                data=data
            )

            response = self.stub.PublishToStream(request)

            if response.success:
                print(f"✅ [NATS] Published to stream {stream_name}: seq={response.sequence}")
                return {
                    'success': True,
                    'sequence': response.sequence
                }
            else:
                print(f"⚠️  [NATS] Publish to stream failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "publish to stream")

    def create_consumer(self, stream_name: str, consumer_name: str,
                       filter_subject: str = '') -> Optional[Dict]:
        """Create JetStream consumer"""
        try:
            self._ensure_connected()

            config = nats_service_pb2.ConsumerConfig(
                name=consumer_name,
                durable_name=consumer_name,
                filter_subject=filter_subject,
                delivery_policy=nats_service_pb2.DELIVERY_ALL,
                ack_policy=nats_service_pb2.ACK_EXPLICIT
            )

            request = nats_service_pb2.CreateConsumerRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                config=config
            )

            response = self.stub.CreateConsumer(request)

            if response.success:
                print(f"✅ [NATS] Consumer created: {stream_name}/{consumer_name}")
                return {
                    'success': True,
                    'consumer': consumer_name
                }
            else:
                print(f"⚠️  [NATS] Consumer creation failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "create consumer")

    def pull_messages(self, stream_name: str, consumer_name: str,
                     batch_size: int = 10) -> List[Dict]:
        """Pull messages from JetStream consumer"""
        try:
            self._ensure_connected()

            request = nats_service_pb2.PullMessagesRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                consumer_name=consumer_name,
                batch_size=batch_size
            )

            response = self.stub.PullMessages(request)

            messages = []
            for msg in response.messages:
                messages.append({
                    'subject': msg.subject,
                    'data': msg.data,
                    'sequence': msg.sequence,
                    'num_delivered': msg.num_delivered
                })

            print(f"✅ [NATS] Pulled {len(messages)} messages from {stream_name}/{consumer_name}")
            return messages

        except Exception as e:
            return self.handle_error(e, "pull messages") or []

    def ack_message(self, stream_name: str, consumer_name: str, sequence: int) -> Optional[Dict]:
        """Acknowledge message"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.AckMessageRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                consumer_name=consumer_name,
                sequence=sequence
            )

            response = self.stub.AckMessage(request)

            if response.success:
                print(f"✅ [NATS] Message acknowledged: seq={sequence}")
                return {'success': True}
            else:
                print(f"⚠️  [NATS] Message ack failed")
                return None

        except Exception as e:
            return self.handle_error(e, "ack message")

    # Object Store
    def object_put(self, bucket: str, object_name: str, data: bytes) -> Optional[Dict]:
        """Put object in object store"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.ObjectPutRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                object_name=object_name,
                data=data
            )

            response = self.stub.ObjectPut(request)

            if response.success:
                print(f"✅ [NATS] Object put: {bucket}/{object_name}")
                return {
                    'success': True,
                    'object_id': response.object_id
                }
            else:
                print(f"⚠️  [NATS] Object put failed")
                return None

        except Exception as e:
            return self.handle_error(e, "object put")

    def object_get(self, bucket: str, object_name: str) -> Optional[Dict]:
        """Get object from object store"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.ObjectGetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                object_name=object_name
            )

            response = self.stub.ObjectGet(request)

            if response.found:
                print(f"✅ [NATS] Object get: {bucket}/{object_name} - {len(response.data)} bytes")
                return {
                    'found': True,
                    'data': response.data,
                    'metadata': dict(response.metadata)
                }
            else:
                print(f"⚠️  [NATS] Object not found: {bucket}/{object_name}")
                return None

        except Exception as e:
            return self.handle_error(e, "object get")

    def object_delete(self, bucket: str, object_name: str) -> Optional[Dict]:
        """Delete object from object store"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.ObjectDeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                object_name=object_name
            )

            response = self.stub.ObjectDelete(request)

            if response.success:
                print(f"✅ [NATS] Object deleted: {bucket}/{object_name}")
                return {'success': True}
            else:
                print(f"⚠️  [NATS] Object delete failed")
                return None

        except Exception as e:
            return self.handle_error(e, "object delete")

    def object_list(self, bucket: str) -> List[Dict]:
        """List objects in object store bucket"""
        try:
            self._ensure_connected()
            request = nats_service_pb2.ObjectListRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket
            )

            response = self.stub.ObjectList(request)

            objects = []
            for obj in response.objects:
                objects.append({
                    'name': obj.name,
                    'size': obj.size,
                    'metadata': dict(obj.metadata)
                })

            print(f"✅ [NATS] Object list: {bucket} - {len(objects)} objects")
            return objects

        except Exception as e:
            return self.handle_error(e, "object list") or []


# Quick test
if __name__ == '__main__':
    with NATSClient(host='localhost', port=50056, user_id='test_user', 
                    organization_id='test_org', enable_compression=False) as client:
        # Health check
        client.health_check()

        # Publish
        client.publish('test.subject', b'Hello NATS!')

        # Request-reply
        client.request('test.request', b'ping', timeout_seconds=5)

        # Get statistics
        client.get_statistics()

        # JetStream - List streams
        streams = client.list_streams()
        print(f"Streams: {streams}")

        # KV Store
        client.kv_put('test-bucket', 'mykey', b'myvalue')
        result = client.kv_get('test-bucket', 'mykey')
        if result:
            print(f"KV value: {result['value']}")
