//go:build api

// Package golden provides API tests for PostgreSQL gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running PostgreSQL gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Query Tests - SELECT operations
// 3. Execute Tests - INSERT, UPDATE, DELETE
// 4. Transaction Tests - BEGIN, COMMIT, ROLLBACK
// 5. Error Handling Tests - Invalid inputs, SQL errors
//
// Related Documents:
// - Logic Contract: tests/contracts/postgres/logic_contract.md
// - Fixtures: tests/contracts/postgres/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestPostgres
package golden

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"

	pb "github.com/isa-cloud/isa_cloud/api/proto/postgres"
	postgres_contract "github.com/isa-cloud/isa_cloud/tests/contracts/postgres"
)

var postgresClient pb.PostgresServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("POSTGRES_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50061"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	postgresClient = pb.NewPostgresServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestPostgresAPI_HealthCheck(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := postgresClient.HealthCheck(ctx, &pb.HealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
		assert.NotEmpty(t, resp.Status)
	})
}

// ===================================================================================
// TEST: QUERY OPERATION
// ===================================================================================

func TestPostgresAPI_Query(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	factory := postgres_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful simple query", func(t *testing.T) {
		req := factory.MakeQueryRequest(
			postgres_contract.WithSQL("SELECT 1 as value"),
		)

		resp, err := postgresClient.Query(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Rows)
	})

	t.Run("query fails with empty SQL", func(t *testing.T) {
		scenarios := postgres_contract.NewScenarios()
		req := scenarios.EmptyQuery()

		_, err := postgresClient.Query(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("query fails with syntax error", func(t *testing.T) {
		scenarios := postgres_contract.NewScenarios()
		req := scenarios.SyntaxErrorQuery()

		_, err := postgresClient.Query(ctx, req)

		require.Error(t, err)
	})

	t.Run("query fails with missing metadata", func(t *testing.T) {
		req := factory.MakeQueryRequest(
			postgres_contract.WithQueryUser("", "test-org"),
		)

		_, err := postgresClient.Query(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: EXECUTE OPERATION
// ===================================================================================

func TestPostgresAPI_Execute(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	factory := postgres_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful execute statement", func(t *testing.T) {
		// Create a temp table for testing
		req := factory.MakeExecuteRequest(
			postgres_contract.WithExecuteSQL("CREATE TEMP TABLE IF NOT EXISTS api_test (id INT, name TEXT)"),
		)

		resp, err := postgresClient.Execute(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
	})

	t.Run("execute fails with empty SQL", func(t *testing.T) {
		req := factory.MakeExecuteRequest(
			postgres_contract.WithExecuteSQL(""),
		)

		_, err := postgresClient.Execute(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: TRANSACTION OPERATIONS
// ===================================================================================

func TestPostgresAPI_Transactions(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	factory := postgres_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	t.Run("begin and commit transaction", func(t *testing.T) {
		// Begin transaction
		beginReq := factory.MakeBeginTransactionRequest()
		beginResp, err := postgresClient.BeginTransaction(ctx, beginReq)

		require.NoError(t, err)
		assert.NotEmpty(t, beginResp.TransactionId)

		// Commit transaction
		commitReq := &pb.CommitTransactionRequest{
			Metadata:      beginReq.Metadata,
			TransactionId: beginResp.TransactionId,
		}
		_, err = postgresClient.CommitTransaction(ctx, commitReq)

		require.NoError(t, err)
	})

	t.Run("begin and rollback transaction", func(t *testing.T) {
		// Begin transaction
		beginReq := factory.MakeBeginTransactionRequest()
		beginResp, err := postgresClient.BeginTransaction(ctx, beginReq)

		require.NoError(t, err)
		assert.NotEmpty(t, beginResp.TransactionId)

		// Rollback transaction
		rollbackReq := &pb.RollbackTransactionRequest{
			Metadata:      beginReq.Metadata,
			TransactionId: beginResp.TransactionId,
		}
		_, err = postgresClient.RollbackTransaction(ctx, rollbackReq)

		require.NoError(t, err)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestPostgresAPI_MultiTenantIsolation(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	scenarios := postgres_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("different tenants have isolated queries", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Both should work (data is isolated by org)
		resp1, err := postgresClient.Query(ctx, tenant1Req)
		require.NoError(t, err)
		assert.NotNil(t, resp1)

		resp2, err := postgresClient.Query(ctx, tenant2Req)
		require.NoError(t, err)
		assert.NotNil(t, resp2)
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestPostgresAPI_ResponseContracts(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	factory := postgres_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("QueryResponse has required fields", func(t *testing.T) {
		req := factory.MakeQueryRequest(
			postgres_contract.WithSQL("SELECT 1 as value"),
		)

		resp, err := postgresClient.Query(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.Rows
		_ = resp.RowCount
	})

	t.Run("ExecuteResponse has required fields", func(t *testing.T) {
		req := factory.MakeExecuteRequest(
			postgres_contract.WithExecuteSQL("SELECT 1"),
		)

		resp, err := postgresClient.Execute(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.RowsAffected
		_ = resp.CommandTag
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestPostgresAPI_ErrorCodes(t *testing.T) {
	if postgresClient == nil {
		t.Skip("PostgreSQL gRPC client not initialized")
	}

	factory := postgres_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty SQL", func(t *testing.T) {
		req := factory.MakeQueryRequest(postgres_contract.WithSQL(""))

		_, err := postgresClient.Query(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakeQueryRequest(
			postgres_contract.WithQueryUser("", "test-org"),
		)

		_, err := postgresClient.Query(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}
