# isA Common

Shared Python infrastructure library for the isA platform.

## Overview

`isa-common` provides Python client libraries and utilities for interacting with various infrastructure services in the isA Cloud platform, including:

- **DuckDB Client** - Analytics database integration
- **Loki Client** - Log aggregation and querying
- **MinIO Client** - Object storage operations
- **MQTT Client** - Message broker for IoT
- **NATS Client** - Cloud-native messaging system
- **Redis Client** - Caching and data structures
- **Supabase Client** - Backend-as-a-Service integration

## Installation

Install from PyPI:

```bash
pip install isa-common
```

## Quick Start

### DuckDB Client Example

```python
from isa_common.duckdb_client import DuckDBClient

client = DuckDBClient(host="localhost", port=50051)
client.connect()

# Execute query
result = client.execute_query("SELECT * FROM my_table")
print(result)
```

### NATS Client Example

```python
from isa_common.nats_client import NATSClient

client = NATSClient(host="localhost", port=50054)
client.connect()

# Publish message
client.publish("my.subject", b"Hello World")

# Subscribe to subject
messages = client.subscribe("my.subject")
```

### MinIO Client Example

```python
from isa_common.minio_client import MinIOClient

client = MinIOClient(host="localhost", port=50052)
client.connect()

# Upload file
client.put_object("my-bucket", "file.txt", b"file contents")

# Download file
data = client.get_object("my-bucket", "file.txt")
```

## Features

- **gRPC-based** communication with backend services
- **Service Discovery** integration with Consul
- **Automatic Reconnection** with configurable retry policies
- **Type Safety** with Pydantic models
- **Comprehensive Examples** included in the package

## Requirements

- Python 3.8+
- grpcio >= 1.50.0
- pydantic >= 2.0.0
- tenacity >= 8.0.0

## Documentation

For detailed documentation and more examples, see:
- [DuckDB Client Examples](examples/duck_client_examples.py)
- [Loki Client Examples](examples/loki_client_examples.py)
- [MinIO Client Examples](examples/minio_client_examples.py)
- [MQTT Client Examples](examples/mqtt_client_examples.py)
- [NATS Client Examples](examples/nats_client_examples.py)
- [Redis Client Examples](examples/redis_client_examples.py)
- [Supabase Client Examples](examples/supa_client_examples.py)

## Development

Install development dependencies:

```bash
pip install isa-common[dev]
```

Run tests:

```bash
pytest
```

## License

Copyright © 2024 isA Platform

## Support

For issues and questions, please visit: https://github.com/isa-platform/isA_Cloud







