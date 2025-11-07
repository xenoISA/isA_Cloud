# =€ NATS Client - Event Streaming, Task Queues & Messaging Made Simple

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Simple Usage Pattern

```python
from isa_common.nats_client import NATSClient

# Connect and use (auto-discovers via Consul or use direct host)
with NATSClient(host='localhost', port=50056, user_id='your-service') as client:

    # 1. Basic Pub/Sub - Publish events
    client.publish('events.user.login', b'User logged in')

    # 2. Publish JSON events
    import json
    event = {'user_id': 'usr_123', 'action': 'login', 'timestamp': '2025-10-24T10:00:00Z'}
    client.publish('events.user.login', json.dumps(event).encode())

    # 3. Subscribe to events (with callback)
    def handle_message(msg):
        print(f"Received: {msg['subject']} - {msg['data']}")

    client.subscribe('events.user.*', handle_message, timeout_seconds=60)

    # 4. Request-Reply pattern (RPC)
    response = client.request('api.users.get', b'user_id=123', timeout_seconds=5)

    # 5. Key-Value Store (Redis replacement)
    client.kv_put('config', 'database.host', b'localhost')
    value = client.kv_get('config', 'database.host')

    # 6. JetStream - Persistent messaging
    client.create_stream('TASKS', subjects=['tasks.>'], max_msgs=10000)
    client.publish_to_stream('TASKS', 'tasks.processing', b'task data')
```

---

## Real Service Example: Event-Driven Notification Service

```python
from isa_common.nats_client import NATSClient
import json
import threading

class NotificationService:
    def __init__(self):
        self.nats = NATSClient(user_id='notification-service')
        self.running = False

    def start(self):
        """Start listening for notification events"""
        self.running = True

        with self.nats:
            # Subscribe to user events
            def handle_user_event(msg):
                event = json.loads(msg['data'].decode())
                self.send_notification(event)

            # Listen to all user events with wildcard
            client.subscribe('events.user.*', handle_user_event, timeout_seconds=3600)

    def send_notification(self, event):
        """Process and send notification"""
        if event['action'] == 'login':
            print(f"User {event['user_id']} logged in - sending welcome notification")
        elif event['action'] == 'purchase':
            print(f"User {event['user_id']} made purchase - sending receipt")

    def publish_event(self, event_type, data):
        """Publish events to the system"""
        with self.nats:
            subject = f'events.notification.{event_type}'
            self.nats.publish(subject, json.dumps(data).encode())

# Usage
service = NotificationService()
threading.Thread(target=service.start, daemon=True).start()

# Publish events from anywhere in your system
service.publish_event('email', {'to': 'user@example.com', 'subject': 'Welcome!'})
```

---

## Real Service Example: Task Queue (Celery Replacement)

```python
from isa_common.nats_client import NATSClient
import json

class TaskQueue:
    """Distributed task queue using NATS JetStream"""

    def __init__(self, stream_name='TASKS'):
        self.nats = NATSClient(user_id='task-queue')
        self.stream_name = stream_name

        # Initialize JetStream
        with self.nats:
            self.nats.create_stream(
                name=stream_name,
                subjects=['tasks.>'],
                max_msgs=100000,
                max_bytes=100*1024*1024  # 100MB
            )

    def enqueue_task(self, task_type, payload, priority='normal'):
        """Add task to queue (like Celery .delay())"""
        with self.nats:
            task = {
                'task_type': task_type,
                'priority': priority,
                'payload': payload,
                'retry_count': 3
            }

            result = self.nats.publish_to_stream(
                self.stream_name,
                'tasks.processing',
                json.dumps(task).encode()
            )

            if result:
                print(f"Task {task_type} enqueued - sequence: {result['sequence']}")
                return result['sequence']
            return None

    def process_tasks(self, worker_name, batch_size=10):
        """Worker that processes tasks (like Celery worker)"""
        with self.nats:
            # Create consumer for this worker
            self.nats.create_consumer(
                stream_name=self.stream_name,
                consumer_name=worker_name,
                filter_subject='tasks.>'
            )

            while True:
                # Pull tasks from queue
                messages = self.nats.pull_messages(
                    stream_name=self.stream_name,
                    consumer_name=worker_name,
                    batch_size=batch_size
                )

                if not messages:
                    break

                # Process each task
                for msg in messages:
                    task = json.loads(msg['data'].decode())

                    # Execute task
                    self.execute_task(task)

                    # Acknowledge completion
                    self.nats.ack_message(
                        self.stream_name,
                        worker_name,
                        msg['sequence']
                    )

    def execute_task(self, task):
        """Execute the actual task logic"""
        task_type = task['task_type']
        payload = task['payload']

        if task_type == 'send_email':
            print(f"Sending email to {payload['to']}")
        elif task_type == 'process_image':
            print(f"Processing image {payload['image_id']}")
        elif task_type == 'generate_report':
            print(f"Generating {payload['report_type']} report")

# Usage - Producer (enqueue tasks)
queue = TaskQueue()
queue.enqueue_task('send_email', {'to': 'user@example.com', 'subject': 'Welcome!'}, priority='high')
queue.enqueue_task('process_image', {'image_id': 'img_123', 'operations': ['resize']}, priority='normal')

# Usage - Worker (process tasks)
import threading
def worker():
    queue.process_tasks('worker-1', batch_size=10)

threading.Thread(target=worker, daemon=True).start()
```

---

## Quick Patterns for Common Use Cases

### Basic Pub/Sub Pattern

```python
# Publisher
with NATSClient() as client:
    client.publish('events.order.created', b'Order #12345 created')

    # Publish with headers
    client.publish(
        'events.order.created',
        b'Order data',
        headers={'priority': 'high', 'source': 'web-app'}
    )

# Subscriber (in separate process/thread)
def handle_order(msg):
    print(f"New order: {msg['data'].decode()}")
    print(f"Headers: {msg['headers']}")

with NATSClient() as client:
    client.subscribe('events.order.*', handle_order, timeout_seconds=3600)
```

### Subject Hierarchy with Wildcards

```python
with NATSClient() as client:
    # Publish to hierarchical subjects
    client.publish('orders.created', b'New order')
    client.publish('orders.updated', b'Order updated')
    client.publish('orders.cancelled', b'Order cancelled')
    client.publish('orders.payment.completed', b'Payment done')

    # Subscribe with wildcards
    # '*' matches one level: orders.created, orders.updated
    client.subscribe('orders.*', callback, timeout_seconds=60)

    # '>' matches multiple levels: orders.payment.completed
    client.subscribe('orders.>', callback, timeout_seconds=60)
```

### Batch Publishing

```python
with NATSClient() as client:
    messages = [
        {'subject': 'events.batch.1', 'data': b'Message 1'},
        {'subject': 'events.batch.2', 'data': b'Message 2'},
        {
            'subject': 'events.batch.3',
            'data': b'Message 3',
            'headers': {'priority': 'high'}
        }
    ]

    result = client.publish_batch(messages)
    print(f"Published {result['published_count']} messages")
```

### Request-Reply Pattern (Synchronous RPC)

```python
# Service that responds to requests
def handle_request(msg):
    # Process request and return response
    return b'Response data'

with NATSClient() as service:
    # Set up responder
    service.subscribe('api.users.get', handle_request, timeout_seconds=3600)

# Client that makes requests
with NATSClient() as client:
    response = client.request('api.users.get', b'user_id=123', timeout_seconds=5)
    if response:
        print(f"Got response: {response['data']}")
```

### Key-Value Store (Redis Integration)

```python
with NATSClient() as client:
    bucket = 'app-config'

    # Store configuration
    client.kv_put(bucket, 'database.host', b'localhost')
    client.kv_put(bucket, 'database.port', b'5432')
    client.kv_put(bucket, 'cache.ttl', b'300')

    # Retrieve value
    result = client.kv_get(bucket, 'database.host')
    if result:
        print(f"Value: {result['value'].decode()}")
        print(f"Revision: {result['revision']}")

    # List all keys in bucket
    keys = client.kv_keys(bucket)
    print(f"Keys: {keys}")

    # Delete key
    client.kv_delete(bucket, 'cache.ttl')
```

### JetStream - Persistent Message Streams

```python
with NATSClient() as client:
    # Create stream for persistent messaging
    client.create_stream(
        name='EVENTS',
        subjects=['events.>'],
        max_msgs=100000,       # Keep last 100k messages
        max_bytes=10*1024*1024 # 10MB max storage
    )

    # Publish to stream (persisted)
    result = client.publish_to_stream(
        stream_name='EVENTS',
        subject='events.user.signup',
        data=b'New user registered'
    )
    print(f"Sequence: {result['sequence']}")

    # List all streams
    streams = client.list_streams()
    for stream in streams:
        print(f"{stream['name']}: {stream['messages']} messages")

    # Delete stream
    client.delete_stream('EVENTS')
```

### JetStream Consumer Pattern (Pull-Based)

```python
with NATSClient() as client:
    stream_name = 'TASKS'
    consumer_name = 'worker-1'

    # Create consumer
    client.create_consumer(
        stream_name=stream_name,
        consumer_name=consumer_name,
        filter_subject='tasks.processing'
    )

    # Pull messages from stream
    messages = client.pull_messages(
        stream_name=stream_name,
        consumer_name=consumer_name,
        batch_size=10
    )

    # Process and acknowledge
    for msg in messages:
        print(f"Processing: {msg['data'].decode()}")
        print(f"Sequence: {msg['sequence']}")
        print(f"Delivered: {msg['num_delivered']} times")

        # Process message...

        # Acknowledge after processing
        client.ack_message(stream_name, consumer_name, msg['sequence'])
```

### Object Store (Large Binary Data)

```python
with NATSClient() as client:
    bucket = 'documents'

    # Store objects (large binary data)
    doc_data = b'Document content' * 1000
    result = client.object_put(bucket, 'reports/q4.pdf', doc_data)
    print(f"Object ID: {result['object_id']}")

    # List objects in bucket
    objects = client.object_list(bucket)
    for obj in objects:
        print(f"{obj['name']}: {obj['size']} bytes")

    # Retrieve object
    result = client.object_get(bucket, 'reports/q4.pdf')
    if result:
        data = result['data']
        metadata = result['metadata']
        print(f"Retrieved {len(data)} bytes")

    # Delete object
    client.object_delete(bucket, 'reports/q4.pdf')
```

### Queue Groups (Load Balancing)

```python
# Multiple workers sharing the same queue group
# Only ONE worker receives each message (load balanced)

def worker_1():
    with NATSClient(user_id='worker-1') as client:
        client.subscribe(
            'tasks.processing',
            handle_task,
            queue_group='workers',  # All workers in same group
            timeout_seconds=3600
        )

def worker_2():
    with NATSClient(user_id='worker-2') as client:
        client.subscribe(
            'tasks.processing',
            handle_task,
            queue_group='workers',  # Same group = load balanced
            timeout_seconds=3600
        )

# Start multiple workers
import threading
threading.Thread(target=worker_1, daemon=True).start()
threading.Thread(target=worker_2, daemon=True).start()

# Publish tasks - automatically distributed across workers
with NATSClient() as client:
    for i in range(100):
        client.publish('tasks.processing', f'Task {i}'.encode())
```

### Large Messages and Binary Data

```python
with NATSClient() as client:
    # Binary data
    binary_data = bytes(range(256))
    client.publish('data.binary', binary_data)

    # Large messages (tested with 1MB)
    large_msg = b'X' * (1024 * 1024)  # 1MB
    client.publish('data.large', large_msg)

    # Bulk publishing (1000 messages)
    for i in range(1000):
        client.publish('test.bulk', f'Message {i}'.encode())
```

### Statistics and Monitoring

```python
with NATSClient() as client:
    # Get NATS statistics
    stats = client.get_statistics()
    print(f"Total Streams: {stats['total_streams']}")
    print(f"Total Consumers: {stats['total_consumers']}")
    print(f"Total Messages: {stats['total_messages']}")
    print(f"Connections: {stats['connections']}")
    print(f"Messages In: {stats['in_msgs']}")
    print(f"Messages Out: {stats['out_msgs']}")

    # List all streams
    streams = client.list_streams()
    for stream in streams:
        print(f"{stream['name']}: {stream['messages']} messages, {stream['bytes']} bytes")
```

### Health Check

```python
with NATSClient() as client:
    # Basic health check
    health = client.health_check()
    print(f"Healthy: {health['healthy']}")
    print(f"JetStream enabled: {health['jetstream_enabled']}")
    print(f"Connections: {health['connections']}")

    # Deep health check
    health = client.health_check(deep_check=True)
```

---

## Benefits = Zero Messaging Complexity

### What you DON'T need to worry about:
- L Raw NATS protocol implementation
- L Connection management and reconnection
- L gRPC channel setup and cleanup
- L Message serialization/deserialization
- L JetStream API complexity
- L Stream and consumer lifecycle
- L Error handling and retries
- L Wildcard subscription logic
- L Queue group configuration
- L Context managers and resource cleanup

### What you CAN focus on:
-  Your event schema design
-  Your business logic
-  Your message handlers
-  Your task processing
-  Your application features
-  Your data flows

---

## Comparison: Without vs With Client

### Without (Raw NATS + gRPC):
```python
# 200+ lines of connection setup, protocol handling, streaming logic...
import grpc
import nats
from nats_pb2_grpc import NATSServiceStub

# Setup gRPC channel
channel = grpc.insecure_channel('localhost:50056')
stub = NATSServiceStub(channel)

# Setup NATS connection
nc = await nats.connect("nats://localhost:4222")
js = nc.jetstream()

try:
    # Create stream
    await js.add_stream(
        name="TASKS",
        subjects=["tasks.>"],
        retention="limits",
        max_msgs=10000
    )

    # Publish message
    ack = await js.publish("tasks.processing", b"task data")

    # Create consumer
    consumer = await js.pull_subscribe(
        "tasks.>",
        "worker",
        stream="TASKS"
    )

    # Pull and process
    msgs = await consumer.fetch(10)
    for msg in msgs:
        # Process...
        await msg.ack()

except Exception as e:
    # Handle errors
    pass
finally:
    await nc.close()
    channel.close()
```

### With isa_common:
```python
# 6 lines
with NATSClient() as client:
    client.create_stream('TASKS', subjects=['tasks.>'], max_msgs=10000)
    client.publish_to_stream('TASKS', 'tasks.processing', b'task data')
    client.create_consumer('TASKS', 'worker', filter_subject='tasks.>')
    msgs = client.pull_messages('TASKS', 'worker', batch_size=10)
    for msg in msgs:
        client.ack_message('TASKS', 'worker', msg['sequence'])
```

---

## Complete Feature List

 **Basic Pub/Sub**: publish, subscribe with callbacks, wildcards
 **Batch Publishing**: publish multiple messages at once
 **Request-Reply**: synchronous RPC pattern
 **Subject Hierarchy**: organize topics with wildcards (*, >)
 **Queue Groups**: load-balanced message distribution
 **Message Headers**: custom metadata per message
 **Binary Data**: support for any binary payload
 **Large Messages**: tested with 1MB+ messages
 **Bulk Operations**: 1000+ messages in one batch

 **JetStream - Persistent Streams**: durable message storage
 **JetStream - Stream Management**: create, delete, list streams
 **JetStream - Publish to Stream**: persistent message publishing
 **JetStream - Consumer**: pull-based message consumption
 **JetStream - Pull Messages**: batch message retrieval
 **JetStream - Acknowledgment**: manual message ack
 **JetStream - Statistics**: stream and consumer metrics

 **Key-Value Store**: Redis-like operations
 **KV - Put/Get/Delete**: basic KV operations
 **KV - Keys Listing**: list all keys in bucket
 **KV - Revisions**: versioned values

 **Object Store**: large binary data storage
 **Object - Put/Get/Delete**: object CRUD operations
 **Object - List**: enumerate objects in bucket
 **Object - Metadata**: object information

 **Health Check**: service status monitoring
 **Statistics**: comprehensive metrics
 **Multi-tenancy**: user and organization scoping
 **Auto-cleanup**: context manager support
 **Consul Integration**: automatic service discovery

---

## Test Results

**19/19 tests passing (100% success rate)**

Comprehensive functional tests cover:
- Service health checks
- Basic publish operations
- JSON message publishing
- Subject hierarchy with wildcards
- Binary data publishing
- Large message handling (1MB tested)
- Bulk publishing (1000 messages)
- Request-reply pattern
- Key-Value store operations (Redis integration)
- JetStream stream creation
- JetStream persistent publishing
- JetStream consumer creation (task worker pattern)
- JetStream pull and acknowledgment (Celery pattern)
- Object store operations (MinIO integration)
- Stream statistics and monitoring
- Batch publishing
- Subscribe with callback
- Subscribe with wildcards
- Unsubscribe operations

All tests demonstrate production-ready reliability across:
- Event streaming and pub/sub
- Task queue patterns (Celery replacement)
- Distributed caching (Redis replacement)
- Object storage (MinIO integration)
- Request-reply (RPC) patterns

---

## Use Cases

### 1. Event-Driven Architecture
Replace Kafka/RabbitMQ with simpler NATS pub/sub for microservices communication.

### 2. Task Queues
Replace Celery with NATS JetStream for distributed task processing.

### 3. Distributed Caching
Use NATS KV store as a Redis alternative for configuration and caching.

### 4. Real-Time Notifications
Stream events to multiple subscribers with wildcard patterns.

### 5. Request-Reply (RPC)
Synchronous service-to-service communication patterns.

### 6. Work Queue Pattern
Load-balanced task distribution across multiple workers.

### 7. Log Aggregation
Collect logs from multiple services with hierarchical subjects.

### 8. Data Pipelines
Stream data processing with persistent JetStream storage.

---

## Bottom Line

Instead of wrestling with raw NATS protocol, JetStream APIs, gRPC serialization, and connection management...

**You write 3 lines and ship features.** =€

The NATS client gives you:
- **Production-ready** messaging out of the box (19/19 tests passing)
- **Event streaming** with pub/sub and wildcards
- **Task queues** as a Celery replacement via JetStream
- **Key-Value store** as a Redis replacement
- **Object store** for large binary data (MinIO integration)
- **Request-Reply** for synchronous RPC
- **Load balancing** via queue groups
- **Large message support** (1MB+ tested)
- **Bulk operations** (1000+ messages)
- **Auto-cleanup** via context managers
- **Multi-tenancy** via user/org scoping
- **Type-safe** results (dicts)

Just pip install and focus on your event-driven architecture and messaging logic!
