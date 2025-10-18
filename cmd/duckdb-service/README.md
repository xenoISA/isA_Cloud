# DuckDB gRPC Service

Complete DuckDB analytics gRPC service with client examples and tests.

## 📁 Project Structure

```
cmd/duckdb-service/
├── main.go                          # Service entry point
├── server/
│   ├── server.go                    # gRPC service implementation
│   └── auth.go                      # Authentication service
├── tests/
│   └── duckdb_grpc_test.sh         # Go-based integration tests
├── examples/
│   └── duckdb_client_example.py    # Python client example
└── README.md                        # This file
```

## 🚀 Quick Start

### 1. Start the Service

```bash
# Using Docker Compose
docker-compose -f deployments/compose/grpc-services.yml up -d duckdb-grpc-service

# Verify service is running
docker ps | grep duckdb-grpc

# Check logs
docker logs isa-duckdb-grpc

# Verify Consul registration (if enabled)
curl http://localhost:8500/v1/catalog/services | jq '.["duckdb-grpc-service"]'
```

The service will be available at `localhost:50052`.

### 2. Run Go Tests

```bash
# Run all integration tests
./cmd/duckdb-service/tests/duckdb_grpc_test.sh

# Or specify custom endpoint
GRPC_ENDPOINT=192.168.1.100:50052 ./cmd/duckdb-service/tests/duckdb_grpc_test.sh
```

The Go test script will:
- Generate temporary Go test code
- Test all major gRPC methods
- Clean up test databases and tables

**Tests included:**
1. Health Check
2. Create Database
3. List Databases
4. Create Table
5. Execute Statement (INSERT)
6. Execute Query (SELECT)
7. List Tables
8. Get Table Schema
9. Import Data from MinIO
10. Export Data to MinIO
11. Delete Database

### 3. Run Python Example

#### Step 1: Generate Python Proto Files

```bash
# Install dependencies
pip install grpcio grpcio-tools protobuf

# Create output directory
mkdir -p cmd/duckdb-service/examples/proto

# Generate Python code from proto files
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=cmd/duckdb-service/examples/proto \
    --grpc_python_out=cmd/duckdb-service/examples/proto \
    api/proto/common.proto \
    api/proto/duckdb_service.proto

# Create Python package
touch cmd/duckdb-service/examples/proto/__init__.py
```

#### Step 2: Run the Example

```bash
# Run with default localhost connection
python cmd/duckdb-service/examples/duckdb_client_example.py

# Or specify custom host
python cmd/duckdb-service/examples/duckdb_client_example.py --host 192.168.1.100 --port 50052
```

The Python example demonstrates:
- Creating and managing databases
- Creating tables with schemas
- Executing SQL queries and statements
- Streaming query results
- Importing/exporting data from/to MinIO
- Managing database backups
- Installing DuckDB extensions

## 📝 Service Features

### Implemented Methods (27 total)

#### Database Management (6 methods)
- ✅ `CreateDatabase` - Create a new database
- ✅ `ListDatabases` - List user databases
- ✅ `DeleteDatabase` - Delete a database
- ✅ `GetDatabaseInfo` - Get database details
- ✅ `BackupDatabase` - Create database backup
- ✅ `RestoreDatabase` - Restore from backup

#### Table Management (5 methods)
- ✅ `CreateTable` - Create a table with schema
- ✅ `ListTables` - List tables in database
- ✅ `DropTable` - Delete a table
- ✅ `GetTableSchema` - Get table schema
- ✅ `GetTableStats` - Get table statistics

#### Query Operations (5 methods)
- ✅ `ExecuteQuery` - Execute SELECT query
- ✅ `ExecuteQueryStream` - Stream query results
- ✅ `ExecuteStatement` - Execute DML statement
- ✅ `ExecuteBatch` - Batch execute statements
- ✅ `PrepareStatement` - Prepare statement

#### View Management (3 methods)
- ✅ `CreateView` - Create SQL view
- ✅ `ListViews` - List views
- ✅ `DropView` - Delete view

#### Data Import/Export (4 methods)
- ✅ `ImportFromMinIO` - Import from MinIO (CSV/Parquet/JSON)
- ✅ `ExportToMinIO` - Export to MinIO
- ✅ `QueryMinIOFile` - Query file directly in MinIO
- ✅ `ImportData` - Stream import data

#### Extensions (3 methods)
- ✅ `InstallExtension` - Install DuckDB extension
- ✅ `ListExtensions` - List installed extensions
- ✅ `CreateFunction` - Create user-defined function

#### Health Check (1 method)
- ✅ `HealthCheck` - Service health status
- ✅ `GetMetrics` - Service metrics

## 🔧 Configuration

### Environment Variables

```bash
# DuckDB Configuration
ISA_CLOUD_STORAGE_DUCKDB_DATABASE_PATH=/data/duckdb
ISA_CLOUD_STORAGE_DUCKDB_MEMORY_LIMIT=2GB
ISA_CLOUD_STORAGE_DUCKDB_THREADS=4

# MinIO Integration (for database file storage)
ISA_CLOUD_STORAGE_MINIO_ENDPOINT=staging-minio:9000
ISA_CLOUD_STORAGE_MINIO_ACCESS_KEY=minioadmin
ISA_CLOUD_STORAGE_MINIO_SECRET_KEY=minioadmin
ISA_CLOUD_STORAGE_MINIO_USE_SSL=false

# Consul Service Discovery
ISA_CLOUD_STORAGE_CONSUL_ENABLED=false
ISA_CLOUD_STORAGE_CONSUL_HOST=staging-consul
ISA_CLOUD_STORAGE_CONSUL_PORT=8500

# gRPC Configuration
ISA_CLOUD_STORAGE_DUCKDB_GRPC_PORT=50052
```

### Service Registration

The service automatically registers with Consul on startup (if enabled):
- **Service Name**: `duckdb-grpc-service`
- **Service ID**: `duckdb-service-{hostname}`
- **Port**: 50052
- **Health Check**: gRPC health check every 10 seconds

## 🔒 Security Features

- **Multi-tenancy**: Automatic user isolation with per-user databases in MinIO
- **Authentication**: User validation on all operations
- **Authorization**: User-based access control
- **Isolation**: User-specific table prefixes (`user_{userId}_{tableName}`)

## 🗄️ Storage Architecture

### Per-User Database Files in MinIO

Each user's databases are stored in MinIO buckets:

```
MinIO Structure:
user-{userId}-duckdb/        # User bucket
  ├── database1.duckdb       # User's first database
  ├── database2.duckdb       # User's second database
  └── backups/               # Database backups
      └── backup-*.duckdb

org-{orgId}-duckdb/          # Organization bucket
  └── shared.duckdb          # Shared organization database
```

### Database Lifecycle

1. **Create**: Database file created in MinIO bucket
2. **Open**: File downloaded to local temp, DuckDB opens it
3. **Modify**: Changes tracked locally
4. **Sync**: Auto-sync every 30 seconds to MinIO
5. **Close**: Final sync to MinIO, local file removed

## 📊 Testing

### Go Tests

The Go test script provides comprehensive integration testing:

```bash
# Run all tests
./cmd/duckdb-service/tests/duckdb_grpc_test.sh

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
python cmd/duckdb-service/examples/duckdb_client_example.py

# Expected output:
# ✅ All examples completed successfully!
# - Health Check
# - Create Database
# - Create Table
# - Insert Data
# - Query Data
# - List Tables
# - Get Table Schema
# - Delete Database
```

## 🐛 Troubleshooting

### Service not starting

```bash
# Check container logs
docker logs isa-duckdb-grpc

# Check if port is already in use
lsof -i :50052

# Verify MinIO is accessible
docker exec isa-duckdb-grpc nc -zv staging-minio 9000
```

### MinIO connection issues

```bash
# Check MinIO connectivity
docker exec isa-duckdb-grpc nc -zv staging-minio 9000

# Verify MinIO credentials in environment
docker exec isa-duckdb-grpc env | grep MINIO

# View service logs for MinIO messages
docker logs isa-duckdb-grpc | grep -i minio
```

### Python proto import errors

```bash
# Ensure proto files are generated
ls -la cmd/duckdb-service/examples/proto/

# Should see:
# - duckdb_service_pb2.py
# - duckdb_service_pb2_grpc.py
# - common_pb2.py
# - common_pb2_grpc.py
# - __init__.py

# Regenerate if missing
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=cmd/duckdb-service/examples/proto \
    --grpc_python_out=cmd/duckdb-service/examples/proto \
    api/proto/common.proto \
    api/proto/duckdb_service.proto
```

### Database file sync issues

```bash
# Check temp directory
docker exec isa-duckdb-grpc ls -la /tmp/duckdb/

# Verify MinIO bucket exists
docker exec staging-minio mc ls minio/user-{userId}-duckdb/

# Check database file permissions
docker exec isa-duckdb-grpc ls -la /tmp/duckdb/*.duckdb
```

## 📚 Additional Resources

- **Proto Definitions**: `api/proto/duckdb_service.proto`
- **Service Implementation**: `cmd/duckdb-service/server/server.go`
- **MinIO SDK Client**: `pkg/storage/minio/client.go`
- **DuckDB Client**: `pkg/analytics/duckdb/client.go`
- **Docker Compose**: `deployments/compose/grpc-services.yml`
- **Deployment Guide**: `docs/deployment/staging-deployment-guide.md`

## 🤝 Contributing

When adding new features:

1. Update proto definitions in `api/proto/duckdb_service.proto`
2. Regenerate Go code: `protoc --go_out=. --go-grpc_out=. api/proto/duckdb_service.proto`
3. Implement method in `cmd/duckdb-service/server/server.go`
4. Add Go test in `cmd/duckdb-service/tests/duckdb_grpc_test.sh`
5. Update Python example in `cmd/duckdb-service/examples/duckdb_client_example.py`
6. Rebuild Docker image: `docker build -t isa-duckdb-service:latest -f deployments/dockerfiles/Dockerfile.duckdb-service .`
7. Test end-to-end with both Go and Python clients

## 📝 License

Copyright © 2024 isA Cloud Platform
