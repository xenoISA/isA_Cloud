#!/usr/bin/env python3
"""
Async NATS gRPC Client
High-performance async NATS client using grpc.aio

Performance Benefits:
- True async I/O without GIL blocking
- Concurrent message publishing
- Efficient streaming subscriptions
- Memory-efficient connection pooling
"""

import logging
from typing import List, Dict, Optional, AsyncIterator, Callable, TYPE_CHECKING
from .async_base_client import AsyncBaseGRPCClient
from .proto import nats_service_pb2, nats_service_pb2_grpc
from google.protobuf.duration_pb2 import Duration

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)


class AsyncNATSClient(AsyncBaseGRPCClient):
    """Async NATS gRPC client for high-performance messaging."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        lazy_connect: bool = True,
        enable_compression: bool = False,
        enable_retry: bool = True,
        consul_registry: Optional['ConsulRegistry'] = None,
        service_name_override: Optional[str] = None
    ):
        """
        Initialize async NATS client.

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: False for low latency)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional)
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
        """Create NATS service stub."""
        return nats_service_pb2_grpc.NATSServiceStub(self.channel)

    def service_name(self) -> str:
        return "NATS"

    def default_port(self) -> int:
        return 50056

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.NATSHealthCheckRequest(deep_check=deep_check)
            response = await self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'nats_status': response.nats_status,
                'jetstream_enabled': response.jetstream_enabled,
                'connections': response.connections,
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Core Publish/Subscribe
    # ============================================

    async def publish(
        self,
        subject: str,
        data: bytes,
        headers: Optional[Dict[str, str]] = None,
        reply_to: str = ''
    ) -> Optional[Dict]:
        """
        Publish message to subject (fire-and-forget, ephemeral).

        Args:
            subject: Subject to publish to (lowercase.dots)
            data: Message payload
            headers: Optional headers
            reply_to: Optional reply-to subject

        Returns:
            {'success': True, 'message': str} or None
        """
        try:
            await self._ensure_connected()

            request = nats_service_pb2.PublishRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject,
                data=data,
                headers=headers or {},
                reply_to=reply_to
            )

            response = await self.stub.Publish(request)

            if response.success:
                return {'success': True, 'message': response.message}
            return None

        except Exception as e:
            return self.handle_error(e, "publish")

    async def publish_batch(self, messages: List[Dict]) -> Optional[Dict]:
        """
        Batch publish multiple messages.

        Args:
            messages: List of dicts with 'subject' and 'data' keys

        Returns:
            {'success': True, 'published_count': int, 'errors': list}
        """
        try:
            await self._ensure_connected()

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

            response = await self.stub.PublishBatch(request)

            if response.success:
                return {
                    'success': True,
                    'published_count': response.published_count,
                    'errors': list(response.errors)
                }
            return None

        except Exception as e:
            return self.handle_error(e, "publish batch")

    async def subscribe(self, subject: str, queue_group: str = '') -> AsyncIterator[Dict]:
        """
        Subscribe to a subject and yield messages.

        Args:
            subject: Subject to subscribe to (supports wildcards: *, >)
            queue_group: Optional queue group for load balancing

        Yields:
            Message dicts with 'subject', 'data', 'headers', 'reply_to', 'sequence'
        """
        try:
            await self._ensure_connected()

            request = nats_service_pb2.SubscribeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject,
                queue_group=queue_group
            )

            async for message_response in self.stub.Subscribe(request):
                yield {
                    'subject': message_response.subject,
                    'data': message_response.data,
                    'headers': dict(message_response.headers),
                    'reply_to': message_response.reply_to,
                    'sequence': message_response.sequence
                }

        except Exception as e:
            self.handle_error(e, "subscribe")

    async def request(self, subject: str, data: bytes, timeout_seconds: int = 5) -> Optional[Dict]:
        """Request-reply pattern."""
        try:
            await self._ensure_connected()
            timeout = Duration(seconds=timeout_seconds)

            request = nats_service_pb2.RequestRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                subject=subject,
                data=data,
                timeout=timeout
            )

            response = await self.stub.Request(request)

            if response.success:
                return {
                    'success': True,
                    'data': response.data,
                    'subject': response.subject
                }
            return None

        except Exception as e:
            return self.handle_error(e, "request")

    # ============================================
    # JetStream Operations
    # ============================================

    async def create_stream(
        self,
        name: str,
        subjects: List[str],
        max_msgs: int = -1,
        max_bytes: int = -1
    ) -> Optional[Dict]:
        """
        Create JetStream stream.

        Args:
            name: Stream name (should be UPPERCASE_UNDERSCORE)
            subjects: List of subjects to capture (lowercase.dots)
            max_msgs: Maximum number of messages (-1 for unlimited)
            max_bytes: Maximum bytes (-1 for unlimited)

        Returns:
            Stream info dict or None
        """
        try:
            await self._ensure_connected()

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

            response = await self.stub.CreateStream(request)

            if response.success:
                return {
                    'success': True,
                    'stream': {
                        'name': response.stream.name,
                        'subjects': list(response.stream.config.subjects),
                        'messages': response.stream.state.messages
                    }
                }
            return None

        except Exception as e:
            return self.handle_error(e, "create stream")

    async def delete_stream(self, stream_name: str) -> Optional[Dict]:
        """Delete JetStream stream."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.DeleteStreamRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name
            )

            response = await self.stub.DeleteStream(request)

            if response.success:
                return {'success': True}
            return None

        except Exception as e:
            return self.handle_error(e, "delete stream")

    async def list_streams(self) -> List[Dict]:
        """List all streams."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.ListStreamsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = await self.stub.ListStreams(request)

            return [
                {
                    'name': stream.name,
                    'subjects': list(stream.subjects),
                    'messages': stream.messages,
                    'bytes': stream.bytes
                }
                for stream in response.streams
            ]

        except Exception as e:
            return self.handle_error(e, "list streams") or []

    async def publish_to_stream(self, stream_name: str, subject: str, data: bytes) -> Optional[Dict]:
        """Publish message to JetStream stream."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.PublishToStreamRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                subject=subject,
                data=data
            )

            response = await self.stub.PublishToStream(request)

            if response.success:
                return {
                    'success': True,
                    'sequence': response.sequence
                }
            return None

        except Exception as e:
            return self.handle_error(e, "publish to stream")

    async def create_consumer(
        self,
        stream_name: str,
        consumer_name: str,
        filter_subject: str = ''
    ) -> Optional[Dict]:
        """
        Create JetStream consumer (pull-based, durable).

        Args:
            stream_name: Name of the stream to consume from
            consumer_name: Consumer name (should be lowercase-hyphens)
            filter_subject: Optional subject filter (lowercase.dots)

        Returns:
            Consumer info dict or None
        """
        try:
            await self._ensure_connected()

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

            response = await self.stub.CreateConsumer(request)

            if response.success:
                return {
                    'success': True,
                    'consumer': consumer_name
                }
            return None

        except Exception as e:
            return self.handle_error(e, "create consumer")

    async def pull_messages(self, stream_name: str, consumer_name: str, batch_size: int = 10) -> List[Dict]:
        """Pull messages from JetStream consumer."""
        try:
            await self._ensure_connected()

            request = nats_service_pb2.PullMessagesRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                consumer_name=consumer_name,
                batch_size=batch_size
            )

            response = await self.stub.PullMessages(request)

            return [
                {
                    'subject': msg.subject,
                    'data': msg.data,
                    'sequence': msg.sequence,
                    'num_delivered': msg.num_delivered
                }
                for msg in response.messages
            ]

        except Exception as e:
            return self.handle_error(e, "pull messages") or []

    async def ack_message(self, stream_name: str, consumer_name: str, sequence: int) -> Optional[Dict]:
        """Acknowledge message."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.AckMessageRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                stream_name=stream_name,
                consumer_name=consumer_name,
                sequence=sequence
            )

            response = await self.stub.AckMessage(request)

            if response.success:
                return {'success': True}
            return None

        except Exception as e:
            return self.handle_error(e, "ack message")

    # ============================================
    # KV Store Operations
    # ============================================

    async def kv_put(self, bucket: str, key: str, value: bytes) -> Optional[Dict]:
        """Put value in KV store."""
        try:
            await self._ensure_connected()

            request = nats_service_pb2.KVPutRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                key=key,
                value=value
            )

            response = await self.stub.KVPut(request)

            if response.success:
                return {
                    'success': True,
                    'revision': response.revision
                }
            return None

        except Exception as e:
            return self.handle_error(e, "kv put")

    async def kv_get(self, bucket: str, key: str) -> Optional[Dict]:
        """Get value from KV store."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.KVGetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                key=key
            )

            response = await self.stub.KVGet(request)

            if response.found:
                return {
                    'found': True,
                    'value': response.value,
                    'revision': response.revision
                }
            return None

        except Exception as e:
            return self.handle_error(e, "kv get")

    async def kv_delete(self, bucket: str, key: str) -> Optional[Dict]:
        """Delete key from KV store."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.KVDeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                key=key
            )

            response = await self.stub.KVDelete(request)

            if response.success:
                return {'success': True}
            return None

        except Exception as e:
            return self.handle_error(e, "kv delete")

    async def kv_keys(self, bucket: str) -> List[str]:
        """List all keys in KV bucket."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.KVKeysRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket
            )

            response = await self.stub.KVKeys(request)
            return list(response.keys)

        except Exception as e:
            return self.handle_error(e, "kv keys") or []

    # ============================================
    # Object Store Operations
    # ============================================

    async def object_put(self, bucket: str, object_name: str, data: bytes) -> Optional[Dict]:
        """Put object in object store."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.ObjectPutRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                object_name=object_name,
                data=data
            )

            response = await self.stub.ObjectPut(request)

            if response.success:
                return {
                    'success': True,
                    'object_id': response.object_id
                }
            return None

        except Exception as e:
            return self.handle_error(e, "object put")

    async def object_get(self, bucket: str, object_name: str) -> Optional[Dict]:
        """Get object from object store."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.ObjectGetRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                object_name=object_name
            )

            response = await self.stub.ObjectGet(request)

            if response.found:
                return {
                    'found': True,
                    'data': response.data,
                    'metadata': dict(response.metadata)
                }
            return None

        except Exception as e:
            return self.handle_error(e, "object get")

    async def object_delete(self, bucket: str, object_name: str) -> Optional[Dict]:
        """Delete object from object store."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.ObjectDeleteRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket,
                object_name=object_name
            )

            response = await self.stub.ObjectDelete(request)

            if response.success:
                return {'success': True}
            return None

        except Exception as e:
            return self.handle_error(e, "object delete")

    async def object_list(self, bucket: str) -> List[Dict]:
        """List objects in object store bucket."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.ObjectListRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                bucket=bucket
            )

            response = await self.stub.ObjectList(request)

            return [
                {
                    'name': obj.name,
                    'size': obj.size,
                    'metadata': dict(obj.metadata)
                }
                for obj in response.objects
            ]

        except Exception as e:
            return self.handle_error(e, "object list") or []

    # ============================================
    # Statistics
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get statistics."""
        try:
            await self._ensure_connected()
            request = nats_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = await self.stub.GetStatistics(request)

            return {
                'total_streams': response.total_streams,
                'total_consumers': response.total_consumers,
                'total_messages': response.total_messages,
                'total_bytes': response.total_bytes,
                'connections': response.connections,
                'in_msgs': response.in_msgs,
                'out_msgs': response.out_msgs
            }

        except Exception as e:
            return self.handle_error(e, "get statistics")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def publish_many_concurrent(self, messages: List[Dict]) -> List[Optional[Dict]]:
        """
        Publish multiple messages concurrently.

        Args:
            messages: List of {'subject': str, 'data': bytes, 'headers': dict}

        Returns:
            List of publish results
        """
        import asyncio

        async def pub_single(msg: Dict) -> Optional[Dict]:
            return await self.publish(
                subject=msg['subject'],
                data=msg['data'],
                headers=msg.get('headers')
            )

        return await asyncio.gather(*[pub_single(m) for m in messages])


# Example usage
if __name__ == '__main__':
    import asyncio

    async def main():
        async with AsyncNATSClient(host='localhost', port=50056, user_id='test_user') as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Publish
            result = await client.publish('test.subject', b'Hello async NATS!')
            print(f"Publish: {result}")

            # Batch publish
            batch_result = await client.publish_batch([
                {'subject': 'test.1', 'data': b'msg1'},
                {'subject': 'test.2', 'data': b'msg2'},
                {'subject': 'test.3', 'data': b'msg3'}
            ])
            print(f"Batch publish: {batch_result}")

            # Stats
            stats = await client.get_statistics()
            print(f"Stats: {stats}")

    asyncio.run(main())
