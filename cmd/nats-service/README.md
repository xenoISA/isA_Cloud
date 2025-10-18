# NATS gRPC Service

Complete NATS messaging and event streaming gRPC service with client examples and tests.

## 📁 Project Structure

```
cmd/nats-service/
├── main.go                          # Service entry point
├── server/
│   ├── server.go                    # gRPC service implementation
│   └── auth.go                      # Authentication service
├── tests/
│   └── nats_grpc_test.sh           # Go-based integration tests
├── examples/
│   └── nats_client_example.py      # Python client example
└── README.md                        # This file
```

## 🚀 Quick Start

### 1. Start the Service

```bash
# Using Docker Compose
docker-compose -f deployments/compose/grpc-services.yml up -d nats-grpc-service

# Verify service is running
docker ps | grep nats-grpc

# Check logs
docker logs isa-nats-grpc

# Verify Consul registration
curl http://localhost:8500/v1/catalog/services | jq '.["nats-grpc-service"]'
```

The service will be available at `localhost:50056`.

### 2. Run Go Tests

```bash
# Run all integration tests
./cmd/nats-service/tests/nats_grpc_test.sh

# Or specify custom endpoint
GRPC_ENDPOINT=192.168.1.100:50056 ./cmd/nats-service/tests/nats_grpc_test.sh
```

The Go test script will:
- Generate temporary Go test code
- Test all 25+ gRPC methods
- Clean up test streams and resources

**Tests included:**
1. Health Check
2. Publish Message
3. Publish Batch Messages
4. Create JetStream Stream
5. Get Stream Info
6. Publish to Stream
7. Key-Value Store - Put
8. Key-Value Store - Get
9. Object Store - Put
10. Object Store - Get
11. Get NATS Statistics
12. Get Stream Statistics
13. Delete Stream (Cleanup)

### 3. Run Python Example

#### Step 1: Generate Python Proto Files

```bash
# Install dependencies
pip install grpcio grpcio-tools protobuf

# Create output directory
mkdir -p cmd/nats-service/examples/proto

# Generate Python code from proto files
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=cmd/nats-service/examples/proto \
    --grpc_python_out=cmd/nats-service/examples/proto \
    api/proto/common.proto \
    api/proto/nats_service.proto

# Create Python package
touch cmd/nats-service/examples/proto/__init__.py
```

#### Step 2: Run the Example

```bash
# Run with default localhost connection
python cmd/nats-service/examples/nats_client_example.py

# Or specify custom host
python cmd/nats-service/examples/nats_client_example.py --host 192.168.1.100 --port 50056
```

The Python example demonstrates:
- Publishing messages and batch messages
- Creating and managing JetStream streams
- Key-Value store operations (Put/Get/Delete/Keys)
- Object store operations (Put/Get/Delete/List)
- Stream statistics and monitoring
- Request/Response patterns

## 📝 Service Features

### Implemented Methods (25 total)

#### Basic Pub/Sub (4 methods)
- ✅ `Publish` - Publish a message to a subject
- ✅ `PublishBatch` - Publish multiple messages at once
- ✅ `Subscribe` - Subscribe to messages (streaming)
- ✅ `Unsubscribe` - Unsubscribe from a subject

#### Request/Response (1 method)
- ✅ `Request` - Send request and wait for response

#### Queue Groups (1 method)
- ✅ `QueueSubscribe` - Subscribe to queue group (streaming)

#### JetStream Stream Management (6 methods)
- ✅ `CreateStream` - Create a new JetStream stream
- ✅ `DeleteStream` - Delete a stream
- ✅ `GetStreamInfo` - Get stream information
- ✅ `ListStreams` - List all user streams
- ✅ `UpdateStream` - Update stream configuration
- ✅ `PurgeStream` - Purge messages from stream

#### JetStream Consumer Management (4 methods)
- ✅ `CreateConsumer` - Create a stream consumer
- ✅ `DeleteConsumer` - Delete a consumer
- ✅ `GetConsumerInfo` - Get consumer information
- ✅ `ListConsumers` - List stream consumers

#### JetStream Message Operations (4 methods)
- ✅ `PublishToStream` - Publish message to stream
- ✅ `PullMessages` - Pull messages from consumer
- ✅ `AckMessage` - Acknowledge a message
- ✅ `NakMessage` - Negatively acknowledge a message

#### Key-Value Store (4 methods)
- ✅ `KVPut` - Store key-value pair
- ✅ `KVGet` - Retrieve value by key
- ✅ `KVDelete` - Delete a key
- ✅ `KVKeys` - List all keys in bucket

#### Object Store (4 methods)
- ✅ `ObjectPut` - Store an object
- ✅ `ObjectGet` - Retrieve an object
- ✅ `ObjectDelete` - Delete an object
- ✅ `ObjectList` - List objects in bucket

#### Statistics and Monitoring (2 methods)
- ✅ `GetStatistics` - Get NATS server statistics
- ✅ `GetStreamStats` - Get stream-specific statistics

#### Health Check (1 method)
- ✅ `HealthCheck` - Service health status

## 🔧 Configuration

### Environment Variables

```bash
# NATS Connection
NATS_URLS=nats://staging-nats:4222
NATS_CLUSTER_ID=isa-cloud-cluster
NATS_USERNAME=
NATS_PASSWORD=
NATS_TOKEN=

# JetStream Configuration
NATS_JETSTREAM_ENABLED=true
NATS_JETSTREAM_DOMAIN=

# Loki Audit Logging
LOKI_URL=http://staging-loki:3100

# Consul Service Discovery
CONSUL_ENABLED=true
CONSUL_HOST=staging-consul
CONSUL_PORT=8500

# gRPC Configuration
GRPC_PORT=50056
SERVICE_NAME=nats-grpc-service
SERVICE_HOSTNAME=isa-nats-grpc
```

### Service Registration

The service automatically registers with Consul on startup:
- **Service Name**: `nats-grpc-service`
- **Service ID**: `nats-service-{hostname}`
- **Port**: 50056
- **Health Check**: gRPC health check every 10 seconds
- **Tags**: `["grpc", "nats", "messaging", "eventbus"]`

## 🔒 Security Features

- **Multi-tenancy**: Automatic user isolation with `user.{userId}.{subject}` prefixes
- **Stream Isolation**: User-specific stream names `user-{userId}-{streamName}`
- **KV Bucket Isolation**: User-specific KV buckets `kv-user-{userId}-{bucket}`
- **Object Bucket Isolation**: User-specific object buckets `obj-user-{userId}-{bucket}`
- **Authentication**: User validation on all operations
- **Authorization**: User-based access control
- **Audit Logging**: All operations logged to Loki

## 📊 Testing

### Go Tests

The Go test script provides comprehensive integration testing:

```bash
# Run all tests
./cmd/nats-service/tests/nats_grpc_test.sh

# Expected output:
# ✅ PASSED: All Go tests passed
# Test Summary
# Passed: 1
# Failed: 0
# Total: 1
```

### Python Example

The Python example serves as both documentation and functional test:

```bash
python cmd/nats-service/examples/nats_client_example.py

# Expected output:
# ✅ All examples completed successfully!
# - Health Check
# - Publish Message
# - Publish Batch Messages
# - Create JetStream Stream
# - Get Stream Info
# - Publish to Stream
# - Key-Value Store Operations
# - Object Store Operations
# - Get Statistics
# - Delete Stream (Cleanup)
```

## 🔍 NATS Features

### Core Capabilities

1. **Pub/Sub Messaging**
   - High-performance message publishing
   - Wildcard subscriptions (`*`, `>`)
   - Queue groups for load balancing
   - Request/Response patterns

2. **JetStream Persistence**
   - Durable message streams
   - Consumer management
   - Message acknowledgment
   - Replay policies

3. **Key-Value Store**
   - Distributed key-value storage
   - Versioning and history
   - Bucket-based organization

4. **Object Store**
   - Large object storage
   - Metadata support
   - Efficient streaming

5. **Multi-tenancy**
   - Per-user resource isolation
   - Organization-level grouping
   - Secure access control

## 🐛 Troubleshooting

### Service not starting

```bash
# Check container logs
docker logs isa-nats-grpc

# Check if port is already in use
lsof -i :50056

# Verify NATS is accessible
docker exec isa-nats-grpc nc -zv staging-nats 4222
```

### Consul registration issues

```bash
# Check Consul connectivity
docker exec isa-nats-grpc nc -zv staging-consul 8500

# Check service registration
curl http://localhost:8500/v1/health/service/nats-grpc-service | jq

# View service logs for Consul messages
docker logs isa-nats-grpc | grep -i consul
```

### Python proto import errors

```bash
# Ensure proto files are generated
ls -la cmd/nats-service/examples/proto/

# Should see:
# - nats_service_pb2.py
# - nats_service_pb2_grpc.py
# - common_pb2.py
# - common_pb2_grpc.py
# - __init__.py

# Regenerate if missing
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=cmd/nats-service/examples/proto \
    --grpc_python_out=cmd/nats-service/examples/proto \
    api/proto/common.proto \
    api/proto/nats_service.proto
```

### Go test failures

```bash
# Check if service is running
docker ps | grep nats-grpc

# Verify gRPC endpoint is accessible
grpcurl -plaintext localhost:50056 list

# Run tests with verbose output
cd cmd/nats-service/tests/go_test
GRPC_ENDPOINT=localhost:50056 go test -v
```

### NATS connectivity issues

```bash
# Check NATS server status
docker exec staging-nats nats-server --signal status

# Check JetStream status
docker exec isa-nats-grpc nats stream ls

# Test basic NATS connectivity
docker exec isa-nats-grpc nats pub test.subject "hello world"
```

## 📈 Performance Considerations

- **Message Size**: Optimized for messages up to 10MB
- **Throughput**: Supports high-throughput scenarios with batching
- **Memory**: JetStream streams can use memory or file storage
- **Scaling**: Horizontal scaling through queue groups
- **Persistence**: Configurable retention policies

## 🔧 Advanced Configuration

### JetStream Stream Configuration

```go
streamConfig := &pb.StreamConfig{
    Name:       "events",
    Subjects:   []string{"events.>", "alerts.>"},
    Storage:    pb.StorageType_STORAGE_FILE,
    MaxMsgs:    1000000,
    MaxBytes:   1024 * 1024 * 1024, // 1GB
    MaxAge:     durationpb.New(24 * time.Hour),
    Replicas:   3,
}
```

### Consumer Configuration

```go
consumerConfig := &pb.ConsumerConfig{
    Name:           "processor",
    DurableName:    "events-processor",
    DeliveryPolicy: pb.DeliveryPolicy_DELIVERY_NEW,
    AckPolicy:      pb.AckPolicy_ACK_EXPLICIT,
    AckWait:        durationpb.New(30 * time.Second),
    MaxDeliver:     5,
}
```

## 📚 Additional Resources

- **Proto Definitions**: `api/proto/nats_service.proto`
- **Service Implementation**: `cmd/nats-service/server/server.go`
- **NATS SDK Client**: `pkg/infrastructure/event/nats/client.go`
- **Docker Compose**: `deployments/compose/grpc-services.yml`
- **NATS Documentation**: https://docs.nats.io/
- **JetStream Guide**: https://docs.nats.io/jetstream

## 🤝 Contributing

When adding new features:

1. Update proto definitions in `api/proto/nats_service.proto`
2. Regenerate Go code: `protoc --go_out=. --go-grpc_out=. api/proto/nats_service.proto`
3. Implement method in `cmd/nats-service/server/server.go`
4. Add Go test in `cmd/nats-service/tests/nats_grpc_test.sh`
5. Update Python example in `cmd/nats-service/examples/nats_client_example.py`
6. Rebuild Docker image: `docker build -t isa-nats-service:latest -f deployments/dockerfiles/Dockerfile.nats-service .`
7. Test end-to-end with both Go and Python clients

## 📋 Method Checklist

All 25 methods from `nats_service.proto` are implemented:

### Basic Pub/Sub ✅
- [x] Publish
- [x] PublishBatch  
- [x] Subscribe (streaming)
- [x] Unsubscribe

### Request/Response ✅
- [x] Request

### Queue Groups ✅  
- [x] QueueSubscribe (streaming)

### JetStream Streams ✅
- [x] CreateStream
- [x] DeleteStream
- [x] GetStreamInfo
- [x] ListStreams
- [x] UpdateStream
- [x] PurgeStream

### JetStream Consumers ✅
- [x] CreateConsumer
- [x] DeleteConsumer
- [x] GetConsumerInfo
- [x] ListConsumers

### JetStream Messages ✅
- [x] PublishToStream
- [x] PullMessages
- [x] AckMessage
- [x] NakMessage

### Key-Value Store ✅
- [x] KVPut
- [x] KVGet
- [x] KVDelete
- [x] KVKeys

### Object Store ✅
- [x] ObjectPut
- [x] ObjectGet
- [x] ObjectDelete
- [x] ObjectList

### Monitoring ✅
- [x] GetStatistics
- [x] GetStreamStats

### Health Check ✅
- [x] HealthCheck

## 📝 License

Copyright © 2024 isA Cloud Platform


