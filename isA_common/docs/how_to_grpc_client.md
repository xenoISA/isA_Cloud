# gRPC Clients Usage Guide

Complete guide for using the `grpc_clients` package to interact with ISA Cloud gRPC services.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Service Discovery with Consul](#service-discovery-with-consul)
- [Client Reference](#client-reference)
  - [MinIO Client](#minio-client)
  - [DuckDB Client](#duckdb-client)
  - [Supabase Client](#supabase-client)
  - [MQTT Client](#mqtt-client)
  - [NATS Client](#nats-client)
- [Advanced Usage](#advanced-usage)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

---

## Overview

The `grpc_clients` package provides a unified Python interface for interacting with ISA Cloud microservices. All clients share a common base class that provides:

- **Lazy connection**: Connections are established on-demand
- **Automatic reconnection**: Built-in retry logic for failed requests
- **Context manager support**: Use `with` statements for automatic cleanup
- **Consistent error handling**: Unified error messages across all services
- **Multi-tenant isolation**: User-specific data namespacing

### Available Services

| Service | Port | Description |
|---------|------|-------------|
| MinIO | 50051 | Object storage (S3-compatible) |
| DuckDB | 50052 | OLAP analytics database |
| MQTT | 50053 | IoT messaging broker |
| Loki | 50054 | Log aggregation (planned) |
| Redis | 50055 | In-memory cache (planned) |
| NATS | 50056 | Cloud-native messaging |
| Supabase | 50057 | PostgreSQL + pgvector |

---

## Installation

### Prerequisites

```bash
# Python 3.8+
python3 --version

# Install gRPC tools
pip install grpcio grpcio-tools protobuf tenacity
```

### Setup

1. **Copy the `grpc_clients` folder** to your project:
   ```bash
   cp -r /path/to/isA_Cloud/grpc_clients /path/to/your/project/
   ```

2. **Verify installation**:
   ```python
   from grpc_clients import get_client, show_available_services

   # List all available services
   show_available_services()
   ```

---

## Quick Start

### Method 1: Using the Factory

```python
from grpc_clients import get_client

# Create a client using factory
minio = get_client('minio', host='localhost', port=50051, user_id='user_123')

# Use the client
minio.health_check()

# Close when done
minio.close()
```

### Method 2: Direct Instantiation

```python
from grpc_clients import MinIOClient

# Create client directly
minio = MinIOClient(host='localhost', port=50051, user_id='user_123')

# Use the client
minio.create_bucket('my-bucket')

# Close when done
minio.close()
```

### Method 3: Context Manager (Recommended)

```python
from grpc_clients import MinIOClient

# Automatic connection management
with MinIOClient(host='localhost', port=50051, user_id='user_123') as minio:
    minio.create_bucket('my-bucket')
    minio.upload_object('my-bucket', 'file.txt', b'Hello World!')
    # Connection automatically closed when exiting the block
```

---

## Service Discovery with Consul

All gRPC services register with Consul for service discovery. You can use Consul to dynamically find service addresses.

### Finding Services with Consul

```python
import consul

def get_service_address(service_name: str, consul_host: str = 'localhost', consul_port: int = 8500):
    """
    Find service address using Consul

    Args:
        service_name: Service name (e.g., 'minio-grpc-service')
        consul_host: Consul address
        consul_port: Consul port

    Returns:
        Tuple of (host, port) or None if not found
    """
    c = consul.Consul(host=consul_host, port=consul_port)

    # Get service instances
    index, services = c.health.service(service_name, passing=True)

    if services:
        service = services[0]
        address = service['Service']['Address']
        port = service['Service']['Port']
        return address, port

    return None, None

# Example usage
host, port = get_service_address('minio-grpc-service')
if host and port:
    from grpc_clients import MinIOClient
    with MinIOClient(host=host, port=port, user_id='user_123') as client:
        client.health_check()
```

### Service Names in Consul

| Service | Consul Service Name |
|---------|---------------------|
| MinIO | `minio-grpc-service` |
| DuckDB | `duckdb-grpc-service` |
| Supabase | `supabase-grpc-service` |
| MQTT | `mqtt-grpc-service` |
| NATS | `nats-grpc-service` |

### Complete Example with Consul

```python
import consul
from grpc_clients import get_client

class ServiceDiscovery:
    """Helper class for service discovery"""

    def __init__(self, consul_host='localhost', consul_port=8500):
        self.consul = consul.Consul(host=consul_host, port=consul_port)

    def get_client(self, service_type: str, user_id: str):
        """
        Get gRPC client using Consul service discovery

        Args:
            service_type: Service type ('minio', 'duckdb', etc.)
            user_id: User ID for multi-tenant isolation

        Returns:
            gRPC client instance
        """
        service_map = {
            'minio': 'minio-grpc-service',
            'duckdb': 'duckdb-grpc-service',
            'supabase': 'supabase-grpc-service',
            'mqtt': 'mqtt-grpc-service',
            'nats': 'nats-grpc-service',
        }

        service_name = service_map.get(service_type)
        if not service_name:
            raise ValueError(f"Unknown service type: {service_type}")

        # Find service in Consul
        index, services = self.consul.health.service(service_name, passing=True)

        if not services:
            raise RuntimeError(f"Service {service_name} not found in Consul")

        # Get first healthy instance
        service = services[0]['Service']
        host = service['Address']
        port = service['Port']

        # Create client using factory
        return get_client(service_type, host=host, port=port, user_id=user_id)

# Usage
discovery = ServiceDiscovery()

# Get MinIO client via Consul
with discovery.get_client('minio', user_id='user_123') as minio:
    minio.health_check()
    minio.list_buckets()

# Get DuckDB client via Consul
with discovery.get_client('duckdb', user_id='user_123') as duckdb:
    duckdb.health_check()
    duckdb.list_databases()
```

---

## Client Reference

### MinIO Client

Object storage client (S3-compatible).

#### Basic Operations

```python
from grpc_clients import MinIOClient

with MinIOClient(host='localhost', port=50051, user_id='user_123', enable_compression=False) as client:
    # Health check
    health = client.health_check(detailed=True)

    # Bucket operations
    client.create_bucket('mybucket', organization_id='my-org', region='us-east-1')
    buckets = client.list_buckets(organization_id='my-org')
    print(f"Buckets: {[b['name'] for b in buckets]}")

    # Upload object (streaming)
    with open('file.txt', 'rb') as f:
        data = f.read()
    result = client.upload_object(
        bucket_name='mybucket',
        object_key='path/to/file.txt',
        data=data,
        content_type='text/plain'
    )
    print(f"Uploaded: {result['object_key']}, ETag: {result['etag']}")

    # List objects
    objects = client.list_objects(bucket_name='mybucket', prefix='path/', max_keys=100)
    for obj in objects:
        print(f"  {obj['key']} - {obj['size']} bytes")

    # Get presigned URL (5 minutes expiry)
    url = client.get_presigned_url(
        bucket_name='mybucket',
        object_key='path/to/file.txt',
        expiry_seconds=300
    )
    print(f"Download URL: {url}")
```

#### Important Notes

- **Bucket naming**: MinIO enforces strict naming rules (lowercase, no underscores)
- **User isolation**: Bucket names are automatically prefixed with `user-{user_id}-`
- **Compression**: Disabled by default due to compatibility issues

---

### DuckDB Client

OLAP analytics database client.

#### Basic Operations

```python
from grpc_clients import DuckDBClient

with DuckDBClient(host='localhost', port=50052, user_id='user_123', enable_compression=False) as client:
    # Health check
    healthy = client.health_check(detailed=False)

    # Database operations
    client.create_database('analytics', metadata={'description': 'Analytics DB'})
    databases = client.list_databases()
    print(f"Databases: {[db['name'] for db in databases]}")

    # Create table
    schema = {
        'id': 'INTEGER',
        'name': 'VARCHAR',
        'age': 'INTEGER',
        'created_at': 'TIMESTAMP'
    }
    client.create_table('analytics', 'users', schema)

    # Insert data
    rows = client.execute_statement(
        'analytics',
        "INSERT INTO users VALUES (1, 'Alice', 30, NOW()), (2, 'Bob', 25, NOW())"
    )
    print(f"Inserted {rows} rows")

    # Query data
    results = client.execute_query(
        'analytics',
        'SELECT * FROM users WHERE age > 20 ORDER BY age DESC',
        limit=100
    )
    for row in results:
        print(f"  {row}")

    # List tables
    tables = client.list_tables('analytics')
    print(f"Tables: {tables}")
```

#### MinIO Integration

```python
# Import data from MinIO
client.import_from_minio(
    db_name='analytics',
    table_name='imported_data',
    bucket='mybucket',
    object_key='data.parquet',
    file_format='parquet'
)

# Query MinIO file directly (without importing)
results = client.query_minio_file(
    db_name='analytics',
    bucket='mybucket',
    object_key='data.csv',
    file_format='csv',
    limit=100
)
```

---

### Supabase Client

PostgreSQL with pgvector extension for vector search.

#### Database Operations

```python
from grpc_clients import SupabaseClient

with SupabaseClient(host='localhost', port=50057, user_id='user_123', enable_compression=False) as client:
    # Health check
    healthy = client.health_check()

    # Query data
    users = client.query(
        table='users',
        select='id, name, email',
        filter='age>25',
        limit=10,
        order='created_at.desc'
    )
    print(f"Found {len(users)} users")

    # Insert data
    new_users = [
        {'name': 'Alice', 'email': 'alice@example.com', 'age': 30},
        {'name': 'Bob', 'email': 'bob@example.com', 'age': 25}
    ]
    inserted = client.insert('users', new_users)
    print(f"Inserted: {inserted}")

    # Update data
    updated = client.update(
        'users',
        {'age': 26},
        filter='name=eq.Bob'
    )
    print(f"Updated {len(updated)} rows")

    # Delete data
    deleted = client.delete('users', filter='age<18')
    print(f"Deleted {len(deleted)} rows")
```

#### Vector Operations (pgvector)

```python
import random

# Generate fake embedding (1536 dimensions for OpenAI)
embedding = [random.random() for _ in range(1536)]

# Upsert embedding
doc_id = client.upsert_embedding(
    table='documents',
    doc_id='doc_001',
    embedding=embedding,
    metadata={'title': 'Test Document', 'category': 'tech'}
)

# Similarity search
query_embedding = [random.random() for _ in range(1536)]
results = client.similarity_search(
    table='documents',
    query_embedding=query_embedding,
    limit=10,
    filter='category=eq.tech',
    threshold=0.7
)

for result in results:
    print(f"  ID: {result['id']}, Similarity: {result['similarity']:.3f}")
    print(f"  Metadata: {result['metadata']}")

# Hybrid search (text + vector)
hybrid_results = client.hybrid_search(
    table='documents',
    text_query='machine learning',
    vector_query=query_embedding,
    limit=10,
    text_weight=0.5,
    vector_weight=0.5
)

# Batch upsert
embeddings_data = [
    {
        'id': f'doc_{i:03d}',
        'embedding': [random.random() for _ in range(1536)],
        'metadata': {'title': f'Document {i}', 'index': i}
    }
    for i in range(100)
]
count = client.batch_upsert_embeddings('documents', embeddings_data)
print(f"Batch inserted {count} embeddings")
```

---

### MQTT Client

IoT messaging broker client.

#### Basic Operations

```python
from grpc_clients import MQTTClient

with MQTTClient(host='localhost', port=50053, user_id='user_123',
                organization_id='my-org', enable_compression=False) as client:
    # Health check
    health = client.health_check(deep_check=True)
    print(f"Broker status: {health['broker_status']}")
    print(f"Active connections: {health['active_connections']}")

    # Connect to MQTT broker
    conn = client.connect(client_id='device-001', username='', password='')
    if conn:
        session_id = conn['session_id']
        print(f"Connected with session: {session_id}")

        # Validate topic
        valid = client.validate_topic('sensors/temperature', allow_wildcards=False)
        print(f"Topic valid: {valid['valid']}")

        # Publish message
        result = client.publish(
            session_id=session_id,
            topic='sensors/temperature',
            payload=b'25.5',
            qos=1,
            retained=False
        )
        print(f"Published message: {result['message_id']}")

        # Get statistics
        stats = client.get_statistics()
        print(f"Total devices: {stats['total_devices']}")
        print(f"Online devices: {stats['online_devices']}")
        print(f"Total topics: {stats['total_topics']}")

        # Disconnect
        client.disconnect(session_id)
```

#### Important Notes

- Topics are automatically namespaced per user: `{user_id}/{organization_id}/topic`
- QoS levels: 0 (at most once), 1 (at least once), 2 (exactly once)
- Retained messages persist on the broker

---

### NATS Client

Cloud-native messaging with JetStream and KV store.

#### Basic Operations

```python
from grpc_clients import NATSClient

with NATSClient(host='localhost', port=50056, user_id='user_123',
                organization_id='my-org', enable_compression=False) as client:
    # Health check
    health = client.health_check(deep_check=True)
    print(f"NATS status: {health['nats_status']}")
    print(f"JetStream enabled: {health['jetstream_enabled']}")

    # Publish message
    result = client.publish(
        subject='events.user.login',
        data=b'{"user_id": "123", "timestamp": "2025-10-15T10:00:00Z"}',
        headers={'content-type': 'application/json'}
    )
    print(f"Published to: events.user.login")

    # Request-reply pattern (5 second timeout)
    response = client.request(
        subject='api.user.get',
        data=b'{"user_id": "123"}',
        timeout_seconds=5
    )
    if response:
        print(f"Response: {response['data']}")

    # Get statistics
    stats = client.get_statistics()
    print(f"Total streams: {stats['total_streams']}")
    print(f"Total messages: {stats['total_messages']}")
```

#### JetStream (Persistent Messaging)

```python
# List streams
streams = client.list_streams()
for stream in streams:
    print(f"Stream: {stream['name']}")
    print(f"  Subjects: {stream['subjects']}")
    print(f"  Messages: {stream['messages']}")
    print(f"  Bytes: {stream['bytes']}")
```

#### KV Store

```python
# Put value
result = client.kv_put(
    bucket='config',
    key='app.version',
    value=b'1.0.0'
)
print(f"KV revision: {result['revision']}")

# Get value
result = client.kv_get(bucket='config', key='app.version')
if result:
    print(f"Value: {result['value'].decode()}")
    print(f"Revision: {result['revision']}")
```

---

## Advanced Usage

### Connection Options

All clients support the following connection options:

```python
client = MinIOClient(
    host='localhost',
    port=50051,
    user_id='user_123',
    lazy_connect=True,           # Delay connection until first use (default: True)
    enable_compression=False,    # Enable gzip compression (default: True, but disabled for compatibility)
    enable_retry=True            # Enable automatic retry on failures (default: True)
)
```

### Retry Configuration

The base client uses the `tenacity` library for retries:

- **Max attempts**: 3
- **Wait strategy**: Exponential backoff (1s min, 10s max)
- **Retry conditions**: Only on `grpc.RpcError`

### Error Handling

All clients return `None` on errors and log details:

```python
result = client.create_bucket('invalid_bucket_name')
if result is None:
    print("Operation failed - check logs for details")
else:
    print(f"Success: {result}")
```

### Multi-tenant Isolation

All services implement automatic tenant isolation:

- **MinIO**: Buckets prefixed with `user-{user_id}-`
- **DuckDB**: Databases namespaced by user/organization
- **Supabase**: Row-level security with user_id filtering
- **MQTT**: Topics namespaced: `{user_id}/{org_id}/topic`
- **NATS**: Subjects prefixed per user/organization

---

## Error Handling

### Common Patterns

```python
from grpc_clients import MinIOClient
import grpc

try:
    with MinIOClient(host='localhost', port=50051, user_id='user_123') as client:
        result = client.create_bucket('my-bucket')
        if result is None:
            print("❌ Bucket creation failed")
        else:
            print("✅ Bucket created successfully")

except grpc.RpcError as e:
    print(f"❌ gRPC error: {e.code()} - {e.details()}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
```

### Checking Service Health

```python
def check_all_services(user_id='health_check'):
    """Check health of all gRPC services"""
    from grpc_clients import MinIOClient, DuckDBClient, SupabaseClient, MQTTClient, NATSClient

    services = [
        ('MinIO', MinIOClient, 50051),
        ('DuckDB', DuckDBClient, 50052),
        ('MQTT', MQTTClient, 50053),
        ('NATS', NATSClient, 50056),
        ('Supabase', SupabaseClient, 50057),
    ]

    for name, ClientClass, port in services:
        try:
            with ClientClass(host='localhost', port=port, user_id=user_id,
                           enable_compression=False) as client:
                healthy = client.health_check()
                status = "✅ Healthy" if healthy else "❌ Unhealthy"
                print(f"{name:12} {status}")
        except Exception as e:
            print(f"{name:12} ❌ Error: {e}")

# Run health checks
check_all_services()
```

---

## Best Practices

### 1. Always Use Context Managers

```python
# Good ✅
with MinIOClient(host='localhost', port=50051, user_id='user_123') as client:
    client.upload_object(...)

# Bad ❌
client = MinIOClient(host='localhost', port=50051, user_id='user_123')
client.upload_object(...)
# Connection not closed!
```

### 2. Disable Compression for Now

Until server-side compression is fully configured, disable it:

```python
client = MinIOClient(..., enable_compression=False)
```

### 3. Use Service Discovery in Production

Don't hardcode service addresses - use Consul:

```python
# Good ✅
from service_discovery import ServiceDiscovery
discovery = ServiceDiscovery()
with discovery.get_client('minio', user_id='user_123') as client:
    ...

# Bad ❌
with MinIOClient(host='10.0.1.5', port=50051, ...) as client:
    ...
```

### 4. Handle Errors Gracefully

```python
result = client.create_bucket('my-bucket')
if result is None:
    # Handle error - maybe retry, log, or notify user
    logger.error("Failed to create bucket")
    return

# Continue with successful result
print(f"Created bucket: {result['bucket']}")
```

### 5. Use Appropriate Isolation

```python
# User-specific data
client = MinIOClient(user_id='alice_123', ...)

# Organization-specific data
client = MQTTClient(user_id='alice_123', organization_id='acme-corp', ...)
```

### 6. Validate Naming Conventions

```python
# MinIO bucket names: lowercase, no underscores
bucket_name = 'my-bucket-name'  # ✅
bucket_name = 'my_bucket_name'  # ❌

# MQTT topics: forward slashes
topic = 'sensors/temperature/room1'  # ✅
topic = 'sensors.temperature.room1'  # ❌ (this is for NATS)

# NATS subjects: dots
subject = 'events.user.login'  # ✅
subject = 'events/user/login'  # ❌ (this is for MQTT)
```

---

## Troubleshooting

### Connection Refused

```
ERROR - [MinIO] 健康检查 失败: failed to connect to all addresses
```

**Solution**: Ensure the service is running and accessible:
```bash
docker-compose -f deployments/compose/grpc-services.yml ps
```

### Bucket Name Invalid

```
ERROR - Bucket name contains invalid characters
```

**Solution**: Use lowercase alphanumeric with hyphens only. The server automatically prefixes with `user-{user_id}-`, so avoid underscores in your user_id or bucket names.

### Compression Not Supported

```
ERROR - grpc: Decompressor is not installed for grpc-encoding "gzip"
```

**Solution**: Disable compression:
```python
client = MinIOClient(..., enable_compression=False)
```

### Proto Field Missing

```
ERROR - Protocol message has no "description" field
```

**Solution**: Check the proto definition - field names may have changed. Use proto introspection:
```python
from grpc_clients.proto import duckdb_service_pb2
fields = duckdb_service_pb2.CreateDatabaseRequest.DESCRIPTOR.fields
for field in fields:
    print(f"  - {field.name}")
```

---

## Example: Complete Workflow

```python
from grpc_clients import MinIOClient, DuckDBClient, SupabaseClient

def analytics_workflow(user_id='data_analyst'):
    """Complete data analytics workflow"""

    # 1. Upload raw data to MinIO
    print("=== Step 1: Upload raw data ===")
    with MinIOClient(host='localhost', port=50051, user_id=user_id, enable_compression=False) as minio:
        minio.create_bucket('rawdata')

        # Upload CSV file
        with open('sales_data.csv', 'rb') as f:
            minio.upload_object('rawdata', 'sales_2025.csv', f.read(), content_type='text/csv')

    # 2. Process data with DuckDB
    print("\n=== Step 2: Process with DuckDB ===")
    with DuckDBClient(host='localhost', port=50052, user_id=user_id, enable_compression=False) as duckdb:
        # Create analytics database
        duckdb.create_database('analytics')

        # Import from MinIO
        duckdb.import_from_minio(
            db_name='analytics',
            table_name='sales',
            bucket='rawdata',
            object_key='sales_2025.csv',
            file_format='csv'
        )

        # Run aggregation query
        results = duckdb.execute_query(
            'analytics',
            '''
            SELECT
                DATE_TRUNC('month', sale_date) as month,
                SUM(amount) as total_sales,
                COUNT(*) as num_transactions
            FROM sales
            GROUP BY month
            ORDER BY month
            '''
        )

        print(f"Monthly aggregation: {results}")

    # 3. Store results in Supabase
    print("\n=== Step 3: Store in Supabase ===")
    with SupabaseClient(host='localhost', port=50057, user_id=user_id, enable_compression=False) as supabase:
        # Insert aggregated data
        supabase.insert('monthly_sales', results)

        # Query for reporting
        report = supabase.query(
            'monthly_sales',
            select='month, total_sales, num_transactions',
            order='month.desc',
            limit=12
        )

        print(f"Last 12 months: {report}")

    print("\n✅ Analytics workflow completed!")

# Run the workflow
analytics_workflow()
```

---

## License

ISA Cloud gRPC Clients - Internal Use Only

## Support

For issues or questions:
- Check logs: `docker-compose -f deployments/compose/grpc-services.yml logs <service>`
- Verify Consul: http://localhost:8500/ui
- Review proto definitions: `api/proto/*.proto`
