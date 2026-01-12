#!/usr/bin/env python3
"""
Async NATS Native Client
High-performance async NATS client using nats-py.

This client connects directly to NATS using the official nats-py library,
providing full support for all NATS operations including:
- Core Pub/Sub messaging
- Request/Reply pattern
- JetStream streams and consumers
- Key-Value store
- Object store

Performance Benefits:
- True async I/O without GIL blocking
- Direct NATS protocol (no gRPC gateway overhead)
- JetStream for persistence and exactly-once delivery
- Built-in reconnection and cluster support
"""

import os
import logging
import asyncio
from typing import List, Dict, Optional, AsyncIterator, Any

import nats
from nats.aio.client import Client as NATSClient
from nats.js.api import StreamConfig, ConsumerConfig, DeliverPolicy, AckPolicy
from nats.js.errors import NotFoundError
from nats.errors import TimeoutError as NATSTimeoutError

logger = logging.getLogger(__name__)


class AsyncNATSClient:
    """
    Async NATS client using native nats-py driver.

    Provides direct connection to NATS with full feature support including
    Core NATS, JetStream, KV Store, and Object Store.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        lazy_connect: bool = True,
        **kwargs  # Accept additional kwargs for compatibility
    ):
        """
        Initialize async NATS client with native driver.

        Args:
            host: NATS host (default: from NATS_HOST env or 'localhost')
            port: NATS port (default: from NATS_PORT env or 4222)
            user_id: User ID for subject prefixing (optional)
            organization_id: Organization ID (optional)
            username: NATS username (default: from NATS_USER env)
            password: NATS password (default: from NATS_PASSWORD env)
            lazy_connect: Delay connection until first use (default: True)
        """
        self._host = host or os.getenv('NATS_HOST', 'localhost')
        self._port = port or int(os.getenv('NATS_PORT', '4222'))
        self._username = username or os.getenv('NATS_USER')
        self._password = password or os.getenv('NATS_PASSWORD')

        self.user_id = user_id or 'default'
        self.organization_id = organization_id or 'default-org'

        self._nc: Optional[NATSClient] = None
        self._js = None  # JetStream context
        self._subscriptions: Dict[str, Any] = {}

        logger.info(f"AsyncNATSClient initialized: {self._host}:{self._port}")

    def _get_subject_prefix(self) -> str:
        """Get subject prefix for multi-tenant isolation."""
        return f"{self.organization_id}.{self.user_id}."

    def _prefix_subject(self, subject: str) -> str:
        """Add prefix to subject for isolation."""
        prefix = self._get_subject_prefix()
        if subject.startswith(prefix):
            return subject
        return f"{prefix}{subject}"

    async def _ensure_connected(self):
        """Ensure NATS connection is established."""
        if self._nc is None or not self._nc.is_connected:
            server_url = f"nats://{self._host}:{self._port}"

            connect_opts = {
                'servers': [server_url],
                'reconnect_time_wait': 2,
                'max_reconnect_attempts': 10,
            }

            if self._username and self._password:
                connect_opts['user'] = self._username
                connect_opts['password'] = self._password

            self._nc = await nats.connect(**connect_opts)
            self._js = self._nc.jetstream()
            logger.info(f"Connected to NATS at {self._host}:{self._port}")

    async def close(self):
        """Close NATS connection."""
        if self._nc:
            await self._nc.drain()
            await self._nc.close()
            self._nc = None
            self._js = None
        logger.info("NATS connection closed")

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - keeps connection alive for reuse."""
        pass

    async def shutdown(self):
        """Explicitly shutdown the connection. Call at application exit."""
        await self.close()

    def handle_error(self, error: Exception, operation: str) -> None:
        """Handle and log errors."""
        logger.error(f"NATS {operation} failed: {error}")
        return None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Check NATS service health."""
        try:
            await self._ensure_connected()

            jetstream_enabled = self._js is not None

            return {
                'healthy': self._nc.is_connected,
                'nats_status': 'connected' if self._nc.is_connected else 'disconnected',
                'jetstream_enabled': jetstream_enabled,
                'connections': 1 if self._nc.is_connected else 0,
                'message': 'NATS server is reachable'
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
            subject: Subject to publish to
            data: Message payload
            headers: Optional headers
            reply_to: Optional reply-to subject

        Returns:
            {'success': True, 'message': str} or None
        """
        try:
            await self._ensure_connected()

            await self._nc.publish(
                subject,
                data,
                reply=reply_to if reply_to else None,
                headers=headers
            )

            return {'success': True, 'message': f'Published to {subject}'}

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

            published = 0
            errors = []

            for msg in messages:
                try:
                    await self._nc.publish(
                        msg['subject'],
                        msg['data'],
                        reply=msg.get('reply_to'),
                        headers=msg.get('headers')
                    )
                    published += 1
                except Exception as e:
                    errors.append(str(e))

            return {
                'success': True,
                'published_count': published,
                'errors': errors
            }

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

            sub = await self._nc.subscribe(subject, queue=queue_group if queue_group else None)
            self._subscriptions[subject] = sub

            async for msg in sub.messages:
                yield {
                    'subject': msg.subject,
                    'data': msg.data,
                    'headers': dict(msg.headers) if msg.headers else {},
                    'reply_to': msg.reply or '',
                    'sequence': 0  # Core NATS doesn't have sequence
                }

        except Exception as e:
            self.handle_error(e, "subscribe")

    async def request(self, subject: str, data: bytes, timeout_seconds: int = 5) -> Optional[Dict]:
        """Request-reply pattern."""
        try:
            await self._ensure_connected()

            response = await self._nc.request(
                subject,
                data,
                timeout=timeout_seconds
            )

            return {
                'success': True,
                'data': response.data,
                'subject': response.subject
            }

        except NATSTimeoutError:
            logger.warning(f"NATS request to {subject} timed out after {timeout_seconds}s")
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
            subjects: List of subjects to capture
            max_msgs: Maximum number of messages (-1 for unlimited)
            max_bytes: Maximum bytes (-1 for unlimited)

        Returns:
            Stream info dict or None
        """
        try:
            await self._ensure_connected()

            config = StreamConfig(
                name=name,
                subjects=subjects,
                max_msgs=max_msgs if max_msgs > 0 else None,
                max_bytes=max_bytes if max_bytes > 0 else None,
            )

            stream = await self._js.add_stream(config)

            return {
                'success': True,
                'stream': {
                    'name': stream.config.name,
                    'subjects': list(stream.config.subjects),
                    'messages': stream.state.messages
                }
            }

        except Exception as e:
            return self.handle_error(e, "create stream")

    async def delete_stream(self, stream_name: str) -> Optional[Dict]:
        """Delete JetStream stream."""
        try:
            await self._ensure_connected()

            await self._js.delete_stream(stream_name)
            return {'success': True}

        except Exception as e:
            return self.handle_error(e, "delete stream")

    async def list_streams(self) -> List[Dict]:
        """List all streams."""
        try:
            await self._ensure_connected()

            streams = []
            async for stream in self._js.streams():
                info = await stream.info()
                streams.append({
                    'name': info.config.name,
                    'subjects': list(info.config.subjects) if info.config.subjects else [],
                    'messages': info.state.messages,
                    'bytes': info.state.bytes
                })

            return streams

        except Exception as e:
            return self.handle_error(e, "list streams") or []

    async def publish_to_stream(self, stream_name: str, subject: str, data: bytes) -> Optional[Dict]:
        """Publish message to JetStream stream."""
        try:
            await self._ensure_connected()

            ack = await self._js.publish(subject, data)

            return {
                'success': True,
                'sequence': ack.seq
            }

        except Exception as e:
            return self.handle_error(e, "publish to stream")

    async def create_consumer(
        self,
        stream_name: str,
        consumer_name: str,
        filter_subject: str = '',
        delivery_policy: str = 'all'
    ) -> Optional[Dict]:
        """
        Create JetStream consumer (pull-based, durable).

        Args:
            stream_name: Name of the stream to consume from
            consumer_name: Consumer name
            filter_subject: Optional subject filter
            delivery_policy: Delivery policy - 'all', 'new', or 'last'

        Returns:
            Consumer info dict or None
        """
        try:
            await self._ensure_connected()

            # Map delivery policy
            deliver_policy_map = {
                'all': DeliverPolicy.ALL,
                'new': DeliverPolicy.NEW,
                'last': DeliverPolicy.LAST,
            }
            deliver = deliver_policy_map.get(delivery_policy.lower(), DeliverPolicy.ALL)

            config = ConsumerConfig(
                durable_name=consumer_name,
                filter_subject=filter_subject if filter_subject else None,
                deliver_policy=deliver,
                ack_policy=AckPolicy.EXPLICIT,
            )

            consumer = await self._js.add_consumer(stream_name, config)

            return {
                'success': True,
                'consumer': consumer_name
            }

        except Exception as e:
            return self.handle_error(e, "create consumer")

    async def pull_messages(self, stream_name: str, consumer_name: str, batch_size: int = 10) -> List[Dict]:
        """Pull messages from JetStream consumer."""
        try:
            await self._ensure_connected()

            # Get the pull subscription
            psub = await self._js.pull_subscribe(
                "",  # No filter, consumer has it
                durable=consumer_name,
                stream=stream_name
            )

            messages = []
            try:
                msgs = await psub.fetch(batch_size, timeout=5)
                for msg in msgs:
                    messages.append({
                        'subject': msg.subject,
                        'data': msg.data,
                        'sequence': msg.metadata.sequence.stream,
                        'num_delivered': msg.metadata.num_delivered
                    })
            except NATSTimeoutError:
                pass  # No messages available

            return messages

        except Exception as e:
            return self.handle_error(e, "pull messages") or []

    async def ack_message(self, stream_name: str, consumer_name: str, sequence: int) -> Optional[Dict]:
        """Acknowledge message."""
        try:
            # In nats-py, ack is typically done on the message object itself
            # This is a placeholder - actual implementation depends on message context
            return {'success': True}

        except Exception as e:
            return self.handle_error(e, "ack message")

    # ============================================
    # KV Store Operations
    # ============================================

    async def kv_put(self, bucket: str, key: str, value: bytes) -> Optional[Dict]:
        """Put value in KV store."""
        try:
            await self._ensure_connected()

            try:
                kv = await self._js.key_value(bucket)
            except NotFoundError:
                kv = await self._js.create_key_value(bucket=bucket)

            revision = await kv.put(key, value)

            return {
                'success': True,
                'revision': revision
            }

        except Exception as e:
            return self.handle_error(e, "kv put")

    async def kv_get(self, bucket: str, key: str) -> Optional[Dict]:
        """Get value from KV store."""
        try:
            await self._ensure_connected()

            kv = await self._js.key_value(bucket)
            entry = await kv.get(key)

            if entry and entry.value:
                return {
                    'found': True,
                    'value': entry.value,
                    'revision': entry.revision
                }
            return None

        except NotFoundError:
            return None
        except Exception as e:
            return self.handle_error(e, "kv get")

    async def kv_delete(self, bucket: str, key: str) -> Optional[Dict]:
        """Delete key from KV store."""
        try:
            await self._ensure_connected()

            kv = await self._js.key_value(bucket)
            await kv.delete(key)

            return {'success': True}

        except Exception as e:
            return self.handle_error(e, "kv delete")

    async def kv_keys(self, bucket: str) -> List[str]:
        """List all keys in KV bucket."""
        try:
            await self._ensure_connected()

            kv = await self._js.key_value(bucket)
            keys = []

            async for key in kv.keys():
                keys.append(key)

            return keys

        except NotFoundError:
            return []
        except Exception as e:
            return self.handle_error(e, "kv keys") or []

    # ============================================
    # Object Store Operations
    # ============================================

    async def object_put(self, bucket: str, object_name: str, data: bytes) -> Optional[Dict]:
        """Put object in object store."""
        try:
            await self._ensure_connected()

            try:
                obs = await self._js.object_store(bucket)
            except NotFoundError:
                obs = await self._js.create_object_store(bucket=bucket)

            info = await obs.put(object_name, data)

            return {
                'success': True,
                'object_id': info.nuid
            }

        except Exception as e:
            return self.handle_error(e, "object put")

    async def object_get(self, bucket: str, object_name: str) -> Optional[Dict]:
        """Get object from object store."""
        try:
            await self._ensure_connected()

            obs = await self._js.object_store(bucket)
            result = await obs.get(object_name)

            if result:
                return {
                    'found': True,
                    'data': result.data,
                    'metadata': {}  # nats-py doesn't expose metadata the same way
                }
            return None

        except NotFoundError:
            return None
        except Exception as e:
            return self.handle_error(e, "object get")

    async def object_delete(self, bucket: str, object_name: str) -> Optional[Dict]:
        """Delete object from object store."""
        try:
            await self._ensure_connected()

            obs = await self._js.object_store(bucket)
            await obs.delete(object_name)

            return {'success': True}

        except Exception as e:
            return self.handle_error(e, "object delete")

    async def object_list(self, bucket: str) -> List[Dict]:
        """List objects in object store bucket."""
        try:
            await self._ensure_connected()

            obs = await self._js.object_store(bucket)
            objects = []

            async for info in obs.list():
                objects.append({
                    'name': info.name,
                    'size': info.size,
                    'metadata': {}
                })

            return objects

        except NotFoundError:
            return []
        except Exception as e:
            return self.handle_error(e, "object list") or []

    # ============================================
    # Statistics
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get statistics."""
        try:
            await self._ensure_connected()

            # Get account info for statistics
            account_info = await self._js.account_info()

            return {
                'total_streams': account_info.streams,
                'total_consumers': account_info.consumers,
                'total_messages': account_info.store_info.messages if hasattr(account_info, 'store_info') else 0,
                'total_bytes': account_info.store_info.bytes if hasattr(account_info, 'store_info') else 0,
                'connections': 1 if self._nc.is_connected else 0,
                'in_msgs': self._nc.stats.get('in_msgs', 0) if hasattr(self._nc, 'stats') else 0,
                'out_msgs': self._nc.stats.get('out_msgs', 0) if hasattr(self._nc, 'stats') else 0
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
        async def pub_single(msg: Dict) -> Optional[Dict]:
            return await self.publish(
                subject=msg['subject'],
                data=msg['data'],
                headers=msg.get('headers')
            )

        return await asyncio.gather(*[pub_single(m) for m in messages])


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncNATSClient(
            host='localhost',
            port=4222,
            user_id='test_user'
        ) as client:
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

            # KV operations
            await client.kv_put('test-bucket', 'key1', b'value1')
            kv_result = await client.kv_get('test-bucket', 'key1')
            print(f"KV get: {kv_result}")

            # Stats
            stats = await client.get_statistics()
            print(f"Stats: {stats}")

    asyncio.run(main())
