# Testing

Contract-driven development and testing strategies.

## Overview

Testing pyramid with 4 layers:

1. **Unit Tests** - Business logic, no I/O
2. **Integration Tests** - Mocked dependencies
3. **API Tests** - Real gRPC endpoints
4. **Smoke Tests** - E2E bash scripts

## Test Contracts

Located in `/tests/contracts/`:

```
tests/contracts/
├── README.md
├── shared_system_contract.md
├── redis/
│   └── logic_contract.md
├── postgres/
│   └── logic_contract.md
├── neo4j/
│   └── logic_contract.md
├── nats/
│   └── logic_contract.md
├── mqtt/
│   └── logic_contract.md
├── minio/
│   └── logic_contract.md
├── qdrant/
│   └── logic_contract.md
└── duckdb/
    └── logic_contract.md
```

## Contract Structure

Each service contract defines:

### Business Rules (BR-XXX)

```markdown
## Business Rules

### BR-001: Key Isolation
- All keys MUST be prefixed with org_id
- Keys without org_id MUST be rejected
- Format: {org_id}:{key}

### BR-002: TTL Enforcement
- Default TTL: 24 hours
- Max TTL: 30 days
- Zero TTL means no expiration
```

### Edge Cases (EC-XXX)

```markdown
## Edge Cases

### EC-001: Empty Key
- Empty string key MUST return InvalidArgument
- Whitespace-only key MUST return InvalidArgument

### EC-002: Large Value
- Values > 512MB MUST return ResourceExhausted
- Large values SHOULD be chunked
```

### Error Handling (ER-XXX)

```markdown
## Error Handling

### ER-001: Connection Failure
- MUST return Unavailable status
- MUST include retry-after hint
- MUST log error with correlation ID

### ER-002: Timeout
- Default timeout: 30 seconds
- MUST return DeadlineExceeded
- MUST cancel downstream operations
```

## Unit Tests

### Go Unit Test

```go
// services/redis-grpc/internal/service/redis_test.go
func TestSetKey(t *testing.T) {
    // Arrange
    mockRepo := mocks.NewMockRepository(t)
    service := NewRedisService(mockRepo)

    mockRepo.EXPECT().
        Set(ctx, "org_123:key", "value", time.Hour).
        Return(nil)

    // Act
    err := service.Set(ctx, "org_123", "key", "value", time.Hour)

    // Assert
    assert.NoError(t, err)
}

func TestSetKey_EmptyKey(t *testing.T) {
    service := NewRedisService(nil)

    err := service.Set(ctx, "org_123", "", "value", time.Hour)

    assert.ErrorIs(t, err, ErrInvalidKey)
}
```

### Table-Driven Tests

```go
func TestKeyValidation(t *testing.T) {
    tests := []struct {
        name    string
        key     string
        wantErr error
    }{
        {"valid key", "user:123", nil},
        {"empty key", "", ErrInvalidKey},
        {"whitespace key", "   ", ErrInvalidKey},
        {"too long key", strings.Repeat("a", 1025), ErrKeyTooLong},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := validateKey(tt.key)
            assert.ErrorIs(t, err, tt.wantErr)
        })
    }
}
```

## Integration Tests

### With Test Containers

```go
// +build integration

func TestRedisIntegration(t *testing.T) {
    ctx := context.Background()

    // Start Redis container
    container, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
        ContainerRequest: testcontainers.ContainerRequest{
            Image:        "redis:7-alpine",
            ExposedPorts: []string{"6379/tcp"},
            WaitingFor:   wait.ForListeningPort("6379/tcp"),
        },
        Started: true,
    })
    require.NoError(t, err)
    defer container.Terminate(ctx)

    host, _ := container.Host(ctx)
    port, _ := container.MappedPort(ctx, "6379")

    // Create client
    client := NewRedisClient(host, port.Int())

    // Test operations
    err = client.Set(ctx, "key", "value")
    assert.NoError(t, err)

    val, err := client.Get(ctx, "key")
    assert.NoError(t, err)
    assert.Equal(t, "value", val)
}
```

## API Tests

### gRPC API Test

```go
// +build api

func TestRedisGRPCService(t *testing.T) {
    // Connect to running service
    conn, err := grpc.Dial("localhost:50055", grpc.WithInsecure())
    require.NoError(t, err)
    defer conn.Close()

    client := pb.NewRedisServiceClient(conn)

    // Test Set
    _, err = client.Set(ctx, &pb.SetRequest{
        OrgId: "org_123",
        Key:   "test_key",
        Value: []byte("test_value"),
        Ttl:   3600,
    })
    assert.NoError(t, err)

    // Test Get
    resp, err := client.Get(ctx, &pb.GetRequest{
        OrgId: "org_123",
        Key:   "test_key",
    })
    assert.NoError(t, err)
    assert.Equal(t, []byte("test_value"), resp.Value)
}
```

## Smoke Tests

### Bash Smoke Test

```bash
#!/bin/bash
# tests/smoke/redis-smoke.sh

set -e

GRPC_HOST=${GRPC_HOST:-localhost:50055}

echo "Testing Redis gRPC service at $GRPC_HOST"

# Test health check
grpcurl -plaintext $GRPC_HOST grpc.health.v1.Health/Check

# Test Set operation
grpcurl -plaintext -d '{
  "org_id": "test_org",
  "key": "smoke_test",
  "value": "dGVzdA==",
  "ttl": 60
}' $GRPC_HOST redis.RedisService/Set

# Test Get operation
RESULT=$(grpcurl -plaintext -d '{
  "org_id": "test_org",
  "key": "smoke_test"
}' $GRPC_HOST redis.RedisService/Get)

echo "Smoke test passed!"
```

## Test Fixtures

### Fixture Generation

```go
// tests/fixtures/redis_fixtures.go
type RedisFixture struct {
    OrgID string
    Keys  []KeyValuePair
}

func NewRedisFixture(orgID string) *RedisFixture {
    return &RedisFixture{
        OrgID: orgID,
        Keys: []KeyValuePair{
            {Key: "user:1", Value: `{"name":"John"}`},
            {Key: "user:2", Value: `{"name":"Jane"}`},
        },
    }
}

func (f *RedisFixture) Setup(ctx context.Context, client RedisClient) error {
    for _, kv := range f.Keys {
        if err := client.Set(ctx, f.OrgID, kv.Key, kv.Value); err != nil {
            return err
        }
    }
    return nil
}

func (f *RedisFixture) Teardown(ctx context.Context, client RedisClient) error {
    for _, kv := range f.Keys {
        _ = client.Delete(ctx, f.OrgID, kv.Key)
    }
    return nil
}
```

## Running Tests

### Make Commands

```bash
# All unit tests
make test

# Integration tests
make test-integration

# API tests (requires running services)
make test-api

# Smoke tests
make test-smoke

# All tests
make test-all

# With coverage
make test-coverage
```

### Go Commands

```bash
# Unit tests
go test -v -short ./...

# Integration tests
go test -v -tags=integration ./...

# API tests
go test -v -tags=api ./...

# Race detection
go test -v -race ./...

# Coverage report
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

## Test Coverage

### Coverage Requirements

| Component | Minimum |
|-----------|---------|
| Service Layer | 80% |
| Repository Layer | 70% |
| Handler Layer | 60% |
| Overall | 75% |

### Coverage Report

```bash
go test -coverprofile=coverage.out ./...
go tool cover -func=coverage.out | grep total
```

## Mocking

### Generate Mocks

```bash
mockgen -source=internal/repository/interface.go \
  -destination=internal/mocks/repository_mock.go \
  -package=mocks
```

### Using Mocks

```go
func TestService(t *testing.T) {
    ctrl := gomock.NewController(t)
    defer ctrl.Finish()

    mockRepo := mocks.NewMockRepository(ctrl)
    service := NewService(mockRepo)

    mockRepo.EXPECT().
        Get(gomock.Any(), "key").
        Return("value", nil)

    result, err := service.Get(ctx, "key")
    assert.NoError(t, err)
    assert.Equal(t, "value", result)
}
```

## Next Steps

- [CI/CD](./cicd) - Automated testing in pipelines
- [Operations](./operations) - Monitoring & debugging
- [gRPC Services](./grpc-services) - Service implementation
