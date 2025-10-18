# MinIO gRPC Service

Complete MinIO object storage gRPC service with client examples and tests.

## 📁 Project Structure

```
cmd/minio-service/
├── main.go                          # Service entry point
├── server/
│   ├── server.go                    # gRPC service implementation
│   └── auth.go                      # Authentication service
├── tests/
│   └── minio_grpc_test.sh          # Go-based integration tests
├── examples/
│   └── minio_client_example.py     # Python client example
└── README.md                        # This file
```

## 🚀 Quick Start

### 1. Start the Service

```bash
# Using Docker Compose
docker-compose -f deployments/compose/grpc-services.yml up -d minio-grpc-service

# Verify service is running
docker ps | grep minio-grpc

# Check logs
docker logs isa-minio-grpc

# Verify Consul registration
curl http://localhost:8500/v1/catalog/services | jq '.["minio-grpc-service"]'
```

The service will be available at `localhost:50051`.

### 2. Run Go Tests

```bash
# Run all integration tests
./cmd/minio-service/tests/minio_grpc_test.sh

# Or specify custom endpoint
GRPC_ENDPOINT=192.168.1.100:50051 ./cmd/minio-service/tests/minio_grpc_test.sh
```

The Go test script will:
- Generate temporary Go test code
- Test all 11 gRPC methods
- Clean up test buckets and objects

**Tests included:**
1. Health Check
2. Create Bucket
3. List Buckets
4. Put Object (Streaming)
5. List Objects
6. Stat Object
7. Get Object (Streaming)
8. Get Presigned URL
9. Copy Object
10. Delete Object
11. Delete Bucket

### 3. Run Python Example

#### Step 1: Generate Python Proto Files

```bash
# Install dependencies
pip install grpcio grpcio-tools protobuf

# Create output directory
mkdir -p cmd/minio-service/examples/proto

# Generate Python code from proto files
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=cmd/minio-service/examples/proto \
    --grpc_python_out=cmd/minio-service/examples/proto \
    api/proto/common.proto \
    api/proto/minio_service.proto

# Create Python package
touch cmd/minio-service/examples/proto/__init__.py
```

#### Step 2: Run the Example

```bash
# Run with default localhost connection
python cmd/minio-service/examples/minio_client_example.py

# Or specify custom host
python cmd/minio-service/examples/minio_client_example.py --host 192.168.1.100 --port 50051
```

The Python example demonstrates:
- Creating and managing buckets
- Uploading and downloading objects (streaming)
- Listing objects and buckets
- Getting presigned URLs
- Copying and deleting objects
- Object metadata operations

## 📝 Service Features

### Implemented Methods (20 total)

#### Bucket Management (6 methods)
- ✅ `CreateBucket` - Create a new bucket
- ✅ `ListBuckets` - List all user buckets
- ✅ `DeleteBucket` - Delete a bucket (with force option)
- ✅ `GetBucketInfo` - Get bucket details
- ✅ `SetBucketPolicy` - Set bucket access policy
- ✅ `GetBucketPolicy` - Get bucket policy

#### Object Operations (8 methods)
- ✅ `PutObject` - Upload object (streaming)
- ✅ `GetObject` - Download object (streaming)
- ✅ `DeleteObject` - Delete single object
- ✅ `DeleteObjects` - Batch delete objects
- ✅ `ListObjects` - List objects in bucket
- ✅ `CopyObject` - Copy object between buckets
- ✅ `StatObject` - Get object metadata

#### Presigned URLs (2 methods)
- ✅ `GetPresignedURL` - Generate download URL
- ✅ `GetPresignedPutURL` - Generate upload URL

#### Multipart Upload (4 methods)
- ✅ `InitiateMultipartUpload` - Start multipart upload
- ✅ `UploadPart` - Upload a part
- ✅ `CompleteMultipartUpload` - Finish upload
- ✅ `AbortMultipartUpload` - Cancel upload

#### Health Check (1 method)
- ✅ `HealthCheck` - Service health status

## 🔧 Configuration

### Environment Variables

```bash
# MinIO Connection
ISA_CLOUD_STORAGE_MINIO_ENDPOINT=staging-minio:9000
ISA_CLOUD_STORAGE_MINIO_ACCESS_KEY=minioadmin
ISA_CLOUD_STORAGE_MINIO_SECRET_KEY=minioadmin
ISA_CLOUD_STORAGE_MINIO_USE_SSL=false
ISA_CLOUD_STORAGE_MINIO_REGION=us-east-1

# Consul Service Discovery
ISA_CLOUD_STORAGE_CONSUL_ENABLED=true
ISA_CLOUD_STORAGE_CONSUL_HOST=staging-consul
ISA_CLOUD_STORAGE_CONSUL_PORT=8500

# gRPC Configuration
ISA_CLOUD_STORAGE_MINIO_GRPC_PORT=50051
```

### Service Registration

The service automatically registers with Consul on startup:
- **Service Name**: `minio-grpc-service`
- **Service ID**: `minio-service-{hostname}`
- **Port**: 50051
- **Health Check**: gRPC health check every 10 seconds

## 🔒 Security Features

- **Multi-tenancy**: Automatic user isolation with `user-{userId}-{bucketName}` prefixes
- **Authentication**: User validation on all operations
- **Authorization**: User-based access control

## 📊 Testing

### Go Tests

The Go test script provides comprehensive integration testing:

```bash
# Run all tests
./cmd/minio-service/tests/minio_grpc_test.sh

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
python cmd/minio-service/examples/minio_client_example.py

# Expected output:
# ✅ All examples completed successfully!
# - Health Check
# - Create Bucket
# - List Buckets
# - Upload Object
# - List Objects
# - Get Object Info
# - Download Object
# - Get Presigned URL
# - Copy Object
# - Delete Object
# - Delete Bucket
```

## 🐛 Troubleshooting

### Service not starting

```bash
# Check container logs
docker logs isa-minio-grpc

# Check if port is already in use
lsof -i :50051

# Verify MinIO is accessible
docker exec isa-minio-grpc nc -zv staging-minio 9000
```

### Consul registration issues

```bash
# Check Consul connectivity
docker exec isa-minio-grpc nc -zv staging-consul 8500

# Check service registration
curl http://localhost:8500/v1/health/service/minio-grpc-service | jq

# View service logs for Consul messages
docker logs isa-minio-grpc | grep -i consul
```

### Python proto import errors

```bash
# Ensure proto files are generated
ls -la cmd/minio-service/examples/proto/

# Should see:
# - minio_service_pb2.py
# - minio_service_pb2_grpc.py
# - common_pb2.py
# - common_pb2_grpc.py
# - __init__.py

# Regenerate if missing
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=cmd/minio-service/examples/proto \
    --grpc_python_out=cmd/minio-service/examples/proto \
    api/proto/common.proto \
    api/proto/minio_service.proto
```

### Go test failures

```bash
# Check if service is running
docker ps | grep minio-grpc

# Verify gRPC endpoint is accessible
grpcurl -plaintext localhost:50051 list

# Run tests with verbose output
cd cmd/minio-service/tests/go_test
GRPC_ENDPOINT=localhost:50051 go test -v
```

## 📚 Additional Resources

- **Proto Definitions**: `api/proto/minio_service.proto`
- **Service Implementation**: `cmd/minio-service/server/server.go`
- **MinIO SDK Client**: `pkg/storage/minio/client.go`
- **Docker Compose**: `deployments/compose/grpc-services.yml`
- **Deployment Guide**: `docs/deployment/staging-deployment-guide.md`

## 🤝 Contributing

When adding new features:

1. Update proto definitions in `api/proto/minio_service.proto`
2. Regenerate Go code: `protoc --go_out=. --go-grpc_out=. api/proto/minio_service.proto`
3. Implement method in `cmd/minio-service/server/server.go`
4. Add Go test in `cmd/minio-service/tests/minio_grpc_test.sh`
5. Update Python example in `cmd/minio-service/examples/minio_client_example.py`
6. Rebuild Docker image: `docker build -t isa-minio-service:latest -f deployments/dockerfiles/Dockerfile.minio-service .`
7. Test end-to-end with both Go and Python clients

## 📝 License

Copyright © 2024 isA Cloud Platform
