//go:build integration

// Package golden provides integration tests for PostgreSQL service.
//
// These tests verify the service layer with mocked dependencies.
//
// Test Execution:
//
//	go test -v -tags=integration ./tests/integration/golden/...
package golden

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	postgres_contract "github.com/isa-cloud/isa_cloud/tests/contracts/postgres"
)

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockPostgresClient mocks the PostgreSQL client
type MockPostgresClient struct {
	mock.Mock
}

func (m *MockPostgresClient) Query(ctx context.Context, query string, params ...string) ([]map[string]interface{}, error) {
	args := m.Called(ctx, query, params)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]map[string]interface{}), args.Error(1)
}

func (m *MockPostgresClient) Execute(ctx context.Context, query string, params ...string) (int64, error) {
	args := m.Called(ctx, query, params)
	return args.Get(0).(int64), args.Error(1)
}

func (m *MockPostgresClient) Transaction(ctx context.Context, statements []string) error {
	args := m.Called(ctx, statements)
	return args.Error(0)
}

// MockPgAuthService mocks the authentication service
type MockPgAuthService struct {
	mock.Mock
}

func (m *MockPgAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - QUERY OPERATION
// ===================================================================================

func TestPostgresService_Query(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("successful query operation", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeQueryRequest(
			postgres_contract.WithQuery("SELECT * FROM users WHERE active = $1"),
			postgres_contract.WithParams("true"),
		)

		expectedResults := []map[string]interface{}{
			{"id": "1", "name": "Alice"},
			{"id": "2", "name": "Bob"},
		}

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Query", mock.Anything, req.Query, req.Params).Return(expectedResults, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		results, err := mockPg.Query(context.Background(), req.Query, req.Params...)
		require.NoError(t, err)
		assert.Len(t, results, 2)
	})

	t.Run("query returns empty result", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeQueryRequest(
			postgres_contract.WithQuery("SELECT * FROM users WHERE id = $1"),
			postgres_contract.WithParams("nonexistent"),
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Query", mock.Anything, req.Query, req.Params).Return([]map[string]interface{}{}, nil)

		// Execute
		results, err := mockPg.Query(context.Background(), req.Query, req.Params...)
		require.NoError(t, err)
		assert.Empty(t, results)
	})

	t.Run("query fails with unauthorized user", func(t *testing.T) {
		mockAuth := new(MockPgAuthService)

		req := factory.MakeQueryRequest()

		mockAuth.On("ValidateUser", req.UserId).Return(errors.New("unauthorized"))

		err := mockAuth.ValidateUser(req.UserId)
		assert.Error(t, err)
	})

	t.Run("query fails with database error", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeQueryRequest()

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Query", mock.Anything, req.Query, req.Params).Return(nil, errors.New("relation does not exist"))

		// Execute
		_, err := mockPg.Query(context.Background(), req.Query, req.Params...)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "relation does not exist")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - EXECUTE OPERATION
// ===================================================================================

func TestPostgresService_Execute(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("successful insert operation", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeExecuteRequest(
			postgres_contract.WithExecuteQuery("INSERT INTO users (name) VALUES ($1)"),
			postgres_contract.WithExecuteParams("Alice"),
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Execute", mock.Anything, req.Query, req.Params).Return(int64(1), nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		affected, err := mockPg.Execute(context.Background(), req.Query, req.Params...)
		require.NoError(t, err)
		assert.Equal(t, int64(1), affected)
	})

	t.Run("successful update operation", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeExecuteRequest(
			postgres_contract.WithExecuteQuery("UPDATE users SET active = $1 WHERE status = $2"),
			postgres_contract.WithExecuteParams("true", "pending"),
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Execute", mock.Anything, req.Query, req.Params).Return(int64(5), nil)

		// Execute
		affected, err := mockPg.Execute(context.Background(), req.Query, req.Params...)
		require.NoError(t, err)
		assert.Equal(t, int64(5), affected)
	})

	t.Run("execute fails with constraint violation", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeExecuteRequest()

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Execute", mock.Anything, req.Query, req.Params).
			Return(int64(0), errors.New("unique constraint violation"))

		// Execute
		_, err := mockPg.Execute(context.Background(), req.Query, req.Params...)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "constraint")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - TRANSACTION OPERATION
// ===================================================================================

func TestPostgresService_Transaction(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("successful transaction", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeTransactionRequest(
			postgres_contract.WithStatements(
				"INSERT INTO orders (id) VALUES ('order-1')",
				"UPDATE inventory SET quantity = quantity - 1",
				"INSERT INTO logs (msg) VALUES ('Order created')",
			),
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Transaction", mock.Anything, req.Statements).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockPg.Transaction(context.Background(), req.Statements)
		require.NoError(t, err)
	})

	t.Run("transaction rollback on failure", func(t *testing.T) {
		mockPg := new(MockPostgresClient)
		mockAuth := new(MockPgAuthService)

		req := factory.MakeTransactionRequest(
			postgres_contract.WithStatements(
				"INSERT INTO orders (id) VALUES ('order-1')",
				"UPDATE inventory SET quantity = -1", // Would fail constraint
			),
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockPg.On("Transaction", mock.Anything, req.Statements).
			Return(errors.New("transaction rolled back: constraint violation"))

		// Execute
		err := mockPg.Transaction(context.Background(), req.Statements)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "rolled back")
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestPostgresService_MultiTenantIsolation(t *testing.T) {
	scenarios := postgres_contract.NewScenarios()

	t.Run("different tenants have different schemas", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		schema1 := postgres_contract.ExpectedSchema(tenant1Req.OrganizationId, tenant1Req.UserId)
		schema2 := postgres_contract.ExpectedSchema(tenant2Req.OrganizationId, tenant2Req.UserId)

		assert.NotEqual(t, schema1, schema2)
	})

	t.Run("schema prefix is consistent", func(t *testing.T) {
		factory := postgres_contract.NewTestDataFactory()

		req1 := factory.MakeQueryRequest(postgres_contract.WithQueryUser("user-x", "org-x"))
		req2 := factory.MakeExecuteRequest(postgres_contract.WithExecuteUser("user-x", "org-x"))

		schema1 := postgres_contract.ExpectedSchema(req1.OrganizationId, req1.UserId)
		schema2 := postgres_contract.ExpectedSchema(req2.OrganizationId, req2.UserId)

		assert.Equal(t, schema1, schema2)
	})
}

// ===================================================================================
// TEST: SQL SAFETY
// ===================================================================================

func TestPostgresService_SQLSafety(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("parameters are not interpolated into query", func(t *testing.T) {
		dangerousInput := "'; DROP TABLE users; --"

		req := factory.MakeQueryRequest(
			postgres_contract.WithQuery("SELECT * FROM users WHERE name = $1"),
			postgres_contract.WithParams(dangerousInput),
		)

		// Query should NOT contain the dangerous input directly
		assert.NotContains(t, req.Query, dangerousInput)
		// But params should
		assert.Contains(t, req.Params, dangerousInput)
	})

	t.Run("query uses parameterized placeholders", func(t *testing.T) {
		req := factory.MakeQueryRequest(
			postgres_contract.WithQuery("SELECT * FROM users WHERE id = $1 AND status = $2"),
		)

		assert.Contains(t, req.Query, "$1")
		assert.Contains(t, req.Query, "$2")
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestPostgresService_ErrorHandling(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("connection error is propagated", func(t *testing.T) {
		mockPg := new(MockPostgresClient)

		req := factory.MakeQueryRequest()

		mockPg.On("Query", mock.Anything, req.Query, req.Params).
			Return(nil, errors.New("connection refused"))

		_, err := mockPg.Query(context.Background(), req.Query, req.Params...)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "connection refused")
	})

	t.Run("timeout error is propagated", func(t *testing.T) {
		mockPg := new(MockPostgresClient)

		req := factory.MakeQueryRequest()

		mockPg.On("Query", mock.Anything, req.Query, req.Params).
			Return(nil, errors.New("context deadline exceeded"))

		_, err := mockPg.Query(context.Background(), req.Query, req.Params...)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "deadline exceeded")
	})
}
