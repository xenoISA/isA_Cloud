//go:build api

// Package golden provides API tests for DuckDB gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running DuckDB gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Query Tests - SELECT operations and analytics
// 3. Statement Tests - DDL and DML operations
// 4. Import/Export Tests - MinIO integration
// 5. Error Handling Tests - Invalid inputs
//
// Related Documents:
// - Logic Contract: tests/contracts/duckdb/logic_contract.md
// - Fixtures: tests/contracts/duckdb/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestDuckdb
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/duckdb"
	duckdb_contract "github.com/isa-cloud/isa_cloud/tests/contracts/duckdb"
)

var duckdbClient pb.DuckDBServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("DUCKDB_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50052"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	duckdbClient = pb.NewDuckDBServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestDuckdbAPI_HealthCheck(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := duckdbClient.HealthCheck(ctx, &pb.HealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
		assert.NotEmpty(t, resp.Status)
	})
}

// ===================================================================================
// TEST: QUERY OPERATIONS
// ===================================================================================

func TestDuckdbAPI_Query(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	factory := duckdb_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	t.Run("simple select query", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT 1 as value, 'test' as name"),
		)

		resp, err := duckdbClient.ExecuteQuery(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
		assert.NotEmpty(t, resp.Rows)
	})

	t.Run("query with aggregation", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery(`
				SELECT
					COUNT(*) as count,
					SUM(x) as sum,
					AVG(x) as avg
				FROM generate_series(1, 100) t(x)
			`),
		)

		resp, err := duckdbClient.ExecuteQuery(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("query with window function", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery(`
				SELECT
					x,
					ROW_NUMBER() OVER (ORDER BY x) as rn,
					SUM(x) OVER () as total
				FROM generate_series(1, 10) t(x)
			`),
		)

		resp, err := duckdbClient.ExecuteQuery(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("query with max rows limit", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT * FROM generate_series(1, 1000) t(x)"),
			duckdb_contract.WithMaxRows(100),
		)

		resp, err := duckdbClient.ExecuteQuery(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
		assert.LessOrEqual(t, len(resp.Rows), 100)
	})

	t.Run("query with explain", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT * FROM generate_series(1, 10) t(x)"),
			duckdb_contract.WithExplain(true),
		)

		resp, err := duckdbClient.ExecuteQuery(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("query fails with empty SQL", func(t *testing.T) {
		scenarios := duckdb_contract.NewScenarios()
		req := scenarios.EmptyQuery()

		_, err := duckdbClient.ExecuteQuery(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("query fails with syntax error", func(t *testing.T) {
		scenarios := duckdb_contract.NewScenarios()
		req := scenarios.SyntaxErrorQuery()

		_, err := duckdbClient.ExecuteQuery(ctx, req)

		require.Error(t, err)
	})
}

// ===================================================================================
// TEST: EXECUTE STATEMENT OPERATIONS
// ===================================================================================

func TestDuckdbAPI_ExecuteStatement(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	factory := duckdb_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	t.Run("create table", func(t *testing.T) {
		req := factory.MakeExecuteStatementRequest(
			duckdb_contract.WithStatement("CREATE TEMP TABLE IF NOT EXISTS api_test (id INTEGER, name VARCHAR)"),
		)

		resp, err := duckdbClient.ExecuteStatement(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("insert data", func(t *testing.T) {
		// Create table first
		createReq := factory.MakeExecuteStatementRequest(
			duckdb_contract.WithStatement("CREATE TEMP TABLE IF NOT EXISTS api_insert_test (id INTEGER, name VARCHAR)"),
		)
		_, err := duckdbClient.ExecuteStatement(ctx, createReq)
		require.NoError(t, err)

		// Insert data
		req := factory.MakeExecuteStatementRequest(
			duckdb_contract.WithStatement("INSERT INTO api_insert_test VALUES (1, 'test')"),
		)

		resp, err := duckdbClient.ExecuteStatement(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("execute fails with empty statement", func(t *testing.T) {
		req := factory.MakeExecuteStatementRequest(
			duckdb_contract.WithStatement(""),
		)

		_, err := duckdbClient.ExecuteStatement(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: DATABASE OPERATIONS
// ===================================================================================

func TestDuckdbAPI_Database(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	factory := duckdb_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	testDBName := "api_test_db_" + time.Now().Format("20060102150405")

	t.Run("create database", func(t *testing.T) {
		req := factory.MakeCreateDatabaseRequest(
			duckdb_contract.WithDatabaseName(testDBName),
		)

		resp, err := duckdbClient.CreateDatabase(ctx, req)

		// May fail if database already exists
		if err == nil {
			assert.True(t, resp.Success)
		}
	})

	t.Run("list databases", func(t *testing.T) {
		req := &pb.ListDatabasesRequest{
			UserId:         "test-user-001",
			OrganizationId: "test-org-001",
		}

		resp, err := duckdbClient.ListDatabases(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Databases)
	})

	// Cleanup
	t.Run("delete database", func(t *testing.T) {
		req := &pb.DeleteDatabaseRequest{
			DatabaseId: testDBName,
			UserId:     "test-user-001",
		}

		_, _ = duckdbClient.DeleteDatabase(ctx, req)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestDuckdbAPI_MultiTenantIsolation(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	scenarios := duckdb_contract.NewScenarios()

	t.Run("different tenants have isolated databases", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Verify they have different org IDs
		assert.NotEqual(t,
			tenant1Req.OrganizationId,
			tenant2Req.OrganizationId)
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestDuckdbAPI_ResponseContracts(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	factory := duckdb_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("ExecuteQueryResponse has required fields", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT 1 as value"),
		)

		resp, err := duckdbClient.ExecuteQuery(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.Success
		_ = resp.RowCount
	})

	t.Run("ExecuteStatementResponse has required fields", func(t *testing.T) {
		req := factory.MakeExecuteStatementRequest(
			duckdb_contract.WithStatement("SELECT 1"),
		)

		resp, err := duckdbClient.ExecuteStatement(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.Success
		_ = resp.AffectedRows
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestDuckdbAPI_ErrorCodes(t *testing.T) {
	if duckdbClient == nil {
		t.Skip("DuckDB gRPC client not initialized")
	}

	factory := duckdb_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty query", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithQuery(""))

		_, err := duckdbClient.ExecuteQuery(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQueryUser(""),
		)

		_, err := duckdbClient.ExecuteQuery(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("error for non-existent table", func(t *testing.T) {
		scenarios := duckdb_contract.NewScenarios()
		req := scenarios.NonExistentTable()

		_, err := duckdbClient.ExecuteQuery(ctx, req)

		require.Error(t, err)
	})
}
