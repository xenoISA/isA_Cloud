# System Contract - Go Testing Methodology

> How to Test isA Cloud Go Services

This document defines the testing methodology, conventions, and standards for all Go services in isA Cloud.

---

## Test Layer Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                         E2E Tests                                │
│              (Full system, real services)                        │
│                    //go:build e2e                                │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│                    Integration Tests                             │
│           (Real databases, real message queues)                 │
│                 //go:build integration                          │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│                     Component Tests                              │
│              (Service layer, mocked infra)                      │
│                  //go:build component                           │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│                       Unit Tests                                 │
│            (Pure functions, no dependencies)                    │
│                    //go:build unit                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Test Categories

| Layer | Build Tag | Dependencies | Speed | Scope |
|-------|-----------|--------------|-------|-------|
| **Unit** | `//go:build unit` | None | < 1ms | Single function |
| **Component** | `//go:build component` | Mocked | < 100ms | Service layer |
| **Integration** | `//go:build integration` | Real DB/Cache | < 5s | Repository layer |
| **E2E** | `//go:build e2e` | Running services | < 30s | Full flow |

---

## Test Naming Convention

```go
// Pattern: Test{Method}_{RuleID}_{Description}
func TestSet_BR001_MultiTenantKeyIsolation(t *testing.T) {}
func TestSet_EC001_EmptyKeyReturnsError(t *testing.T) {}
func TestGet_BR002_NonExistentKeyReturnsNotFound(t *testing.T) {}

// Rule IDs:
// BR-XXX = Business Rule
// EC-XXX = Edge Case
// ER-XXX = Error Handling
```

---

## Directory Structure

```
tests/
├── contracts/                    # Contract definitions
│   ├── shared_system_contract.md # This file
│   ├── README.md                 # Contract overview
│   │
│   ├── redis/                    # Redis service contracts
│   │   ├── logic_contract.md     # Business rules
│   │   └── fixtures.go           # Test data factories
│   │
│   ├── postgres/
│   │   ├── logic_contract.md
│   │   └── fixtures.go
│   │
│   └── nats/
│       ├── logic_contract.md
│       └── fixtures.go
│
├── unit/                         # Unit tests
│   └── {service}/
│       └── {file}_test.go
│
├── integration/                  # Integration tests
│   └── {service}/
│       └── {file}_test.go
│
└── e2e/                          # End-to-end tests
    └── {flow}_test.go
```

---

## Test Data Factories (Fixtures)

### Pattern: Functional Options

```go
// tests/contracts/redis/fixtures.go
package redis_contract

import (
    pb "github.com/isa-cloud/isa_cloud/api/proto/redis"
)

// TestDataFactory creates test data with sensible defaults
type TestDataFactory struct{}

// MakeSetRequest creates a SetRequest with defaults
func (f *TestDataFactory) MakeSetRequest(opts ...SetRequestOption) *pb.SetRequest {
    req := &pb.SetRequest{
        UserId:         "test-user-001",
        OrganizationId: "test-org-001",
        Key:            "test-key",
        Value:          "test-value",
        TtlSeconds:     0,
    }
    for _, opt := range opts {
        opt(req)
    }
    return req
}

// SetRequestOption modifies a SetRequest
type SetRequestOption func(*pb.SetRequest)

// WithKey sets the key
func WithKey(key string) SetRequestOption {
    return func(req *pb.SetRequest) {
        req.Key = key
    }
}

// WithValue sets the value
func WithValue(value string) SetRequestOption {
    return func(req *pb.SetRequest) {
        req.Value = value
    }
}

// WithTTL sets the TTL
func WithTTL(ttl int64) SetRequestOption {
    return func(req *pb.SetRequest) {
        req.TtlSeconds = ttl
    }
}

// WithUser sets user and org IDs
func WithUser(userID, orgID string) SetRequestOption {
    return func(req *pb.SetRequest) {
        req.UserId = userID
        req.OrganizationId = orgID
    }
}
```

### Usage in Tests

```go
func TestSet_BR001_MultiTenantIsolation(t *testing.T) {
    factory := &redis_contract.TestDataFactory{}

    // Default request
    req := factory.MakeSetRequest()

    // Customized request
    req2 := factory.MakeSetRequest(
        redis_contract.WithKey("custom-key"),
        redis_contract.WithTTL(3600),
        redis_contract.WithUser("user-002", "org-002"),
    )
}
```

---

## Test Templates

### Unit Test Template

```go
//go:build unit

package server_test

import (
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

func TestIsolateKey_BR001_PrefixesWithOrgAndUser(t *testing.T) {
    // Arrange
    userID := "user-123"
    orgID := "org-001"
    key := "session:token"

    // Act
    result := isolateKey(userID, orgID, key)

    // Assert
    expected := "org-001:user-123:session:token"
    assert.Equal(t, expected, result)
}
```

### Component Test Template

```go
//go:build component

package server_test

import (
    "context"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
    "github.com/stretchr/testify/require"

    fixtures "github.com/isa-cloud/isa_cloud/tests/contracts/redis"
)

func TestSet_BR001_MultiTenantIsolation(t *testing.T) {
    // Arrange
    mockRedis := new(MockRedisClient)
    mockLoki := new(MockLokiClient)
    server := NewRedisServer(mockRedis, mockLoki)

    factory := &fixtures.TestDataFactory{}
    req := factory.MakeSetRequest()

    // Expect isolated key
    expectedKey := "test-org-001:test-user-001:test-key"
    mockRedis.On("Set", mock.Anything, expectedKey, "test-value", int64(0)).
        Return(nil)

    // Act
    resp, err := server.Set(context.Background(), req)

    // Assert
    require.NoError(t, err)
    assert.True(t, resp.Success)
    mockRedis.AssertExpectations(t)
}
```

### Integration Test Template

```go
//go:build integration

package integration_test

import (
    "context"
    "testing"
    "time"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"

    fixtures "github.com/isa-cloud/isa_cloud/tests/contracts/redis"
)

func TestRedisService_Integration(t *testing.T) {
    // Skip if no Redis available
    if testing.Short() {
        t.Skip("skipping integration test")
    }

    // Setup real Redis connection
    client := setupRedisClient(t)
    defer client.Close()

    server := NewRedisServer(client, nil)
    factory := &fixtures.TestDataFactory{}

    t.Run("Set and Get roundtrip", func(t *testing.T) {
        // Arrange
        setReq := factory.MakeSetRequest(
            fixtures.WithKey("integration-test-key"),
            fixtures.WithValue("integration-test-value"),
        )

        // Act - Set
        setResp, err := server.Set(context.Background(), setReq)
        require.NoError(t, err)
        assert.True(t, setResp.Success)

        // Act - Get
        getReq := factory.MakeGetRequest(
            fixtures.WithKey("integration-test-key"),
        )
        getResp, err := server.Get(context.Background(), getReq)

        // Assert
        require.NoError(t, err)
        assert.Equal(t, "integration-test-value", getResp.Value)
    })
}
```

### Table-Driven Test Template

```go
//go:build unit

package server_test

import (
    "testing"

    "github.com/stretchr/testify/assert"
)

func TestValidateKey(t *testing.T) {
    tests := []struct {
        name    string
        key     string
        wantErr bool
        errMsg  string
    }{
        {
            name:    "valid key",
            key:     "user:profile:123",
            wantErr: false,
        },
        {
            name:    "EC-001: empty key",
            key:     "",
            wantErr: true,
            errMsg:  "key cannot be empty",
        },
        {
            name:    "EC-002: key too long",
            key:     string(make([]byte, 1025)),
            wantErr: true,
            errMsg:  "key exceeds maximum length",
        },
        {
            name:    "EC-003: key with invalid characters",
            key:     "key\x00with\x00nulls",
            wantErr: true,
            errMsg:  "key contains invalid characters",
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := validateKey(tt.key)

            if tt.wantErr {
                assert.Error(t, err)
                assert.Contains(t, err.Error(), tt.errMsg)
            } else {
                assert.NoError(t, err)
            }
        })
    }
}
```

---

## Mocking Patterns

### Interface-Based Mocking

```go
// Define interface in production code
type RedisClient interface {
    Set(ctx context.Context, key string, value interface{}, ttl time.Duration) error
    Get(ctx context.Context, key string) (string, error)
    Delete(ctx context.Context, keys ...string) error
}

// Mock implementation for tests
type MockRedisClient struct {
    mock.Mock
}

func (m *MockRedisClient) Set(ctx context.Context, key string, value interface{}, ttl time.Duration) error {
    args := m.Called(ctx, key, value, ttl)
    return args.Error(0)
}

func (m *MockRedisClient) Get(ctx context.Context, key string) (string, error) {
    args := m.Called(ctx, key)
    return args.String(0), args.Error(1)
}
```

### Testcontainers for Integration

```go
//go:build integration

package integration_test

import (
    "context"
    "testing"

    "github.com/testcontainers/testcontainers-go"
    "github.com/testcontainers/testcontainers-go/wait"
)

func setupRedisContainer(t *testing.T) (string, func()) {
    ctx := context.Background()

    req := testcontainers.ContainerRequest{
        Image:        "redis:7-alpine",
        ExposedPorts: []string{"6379/tcp"},
        WaitingFor:   wait.ForListeningPort("6379/tcp"),
    }

    container, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
        ContainerRequest: req,
        Started:          true,
    })
    if err != nil {
        t.Fatalf("failed to start redis: %v", err)
    }

    host, _ := container.Host(ctx)
    port, _ := container.MappedPort(ctx, "6379")

    cleanup := func() {
        container.Terminate(ctx)
    }

    return fmt.Sprintf("%s:%s", host, port.Port()), cleanup
}
```

---

## Running Tests

### By Layer

```bash
# Unit tests only (fast, no deps)
go test -tags=unit ./...

# Component tests (mocked deps)
go test -tags=component ./...

# Integration tests (real deps)
go test -tags=integration ./...

# E2E tests (full system)
go test -tags=e2e ./...

# All tests
go test ./...
```

### By Service

```bash
# Redis service tests
go test -tags=unit ./cmd/redis-service/...
go test -tags=unit ./tests/unit/redis/...

# Postgres service tests
go test -tags=unit ./cmd/postgres-service/...
```

### With Coverage

```bash
# Generate coverage report
go test -tags=unit -coverprofile=coverage.out ./...
go tool cover -html=coverage.out -o coverage.html

# Coverage summary
go test -tags=unit -cover ./...
```

### Verbose Output

```bash
# Verbose with test names
go test -tags=unit -v ./...

# Run specific test
go test -tags=unit -v -run TestSet_BR001 ./...
```

---

## CI/CD Integration

### Makefile Targets

```makefile
.PHONY: test test-unit test-integration test-coverage

test:
	go test ./...

test-unit:
	go test -tags=unit -v ./...

test-component:
	go test -tags=component -v ./...

test-integration:
	go test -tags=integration -v ./...

test-coverage:
	go test -tags=unit -coverprofile=coverage.out ./...
	go tool cover -func=coverage.out
```

### GitHub Actions

```yaml
- name: Run Unit Tests
  run: go test -tags=unit -v -race ./...

- name: Run Integration Tests
  run: |
    docker-compose up -d redis postgres nats
    go test -tags=integration -v ./...
    docker-compose down
```

---

## Golden Tests (Characterization)

For capturing existing behavior:

```go
//go:build golden

package server_test

import (
    "testing"

    "github.com/sebdah/goldie/v2"
)

func TestSetResponse_Golden(t *testing.T) {
    // Capture actual response
    resp := server.Set(context.Background(), testRequest)

    // Compare with golden file
    g := goldie.New(t)
    g.AssertJson(t, "set_response", resp)
}

// Run with -update flag to update golden files:
// go test -tags=golden -update ./...
```

---

## Best Practices

### Do's

- Use table-driven tests for multiple scenarios
- Name tests after business rules (BR-XXX) or edge cases (EC-XXX)
- Use fixtures for consistent test data
- Mock external dependencies in unit/component tests
- Use build tags to separate test layers
- Clean up resources in integration tests

### Don'ts

- Don't test implementation details, test behavior
- Don't share state between tests
- Don't use `time.Sleep()` - use channels or conditions
- Don't ignore errors in test setup
- Don't hardcode test data - use factories

---

## Related Documents

- [CDD Guide](../../docs/cdd_guide.md) - Contract-Driven Development
- [Logic Contracts](./redis/logic_contract.md) - Business rules
- [Go Dev Guide](../../docs/GO_MICROSERVICE_DEVELOPMENT_GUIDE.md) - Implementation

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
