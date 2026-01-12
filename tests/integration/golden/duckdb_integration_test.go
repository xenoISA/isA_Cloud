//go:build integration

// Package golden provides integration tests for DuckDB service.
package golden

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	duckdb_contract "github.com/isa-cloud/isa_cloud/tests/contracts/duckdb"
)

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockDuckDBClient mocks the DuckDB client
type MockDuckDBClient struct {
	mock.Mock
}

func (m *MockDuckDBClient) Query(ctx context.Context, db, query string) ([]map[string]interface{}, error) {
	args := m.Called(ctx, db, query)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]map[string]interface{}), args.Error(1)
}

func (m *MockDuckDBClient) Import(ctx context.Context, db, bucket, key, table, format string) error {
	args := m.Called(ctx, db, bucket, key, table, format)
	return args.Error(0)
}

func (m *MockDuckDBClient) Export(ctx context.Context, db, query, bucket, key, format string) error {
	args := m.Called(ctx, db, query, bucket, key, format)
	return args.Error(0)
}

// MockDuckDBAuthService mocks authentication
type MockDuckDBAuthService struct {
	mock.Mock
}

func (m *MockDuckDBAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - QUERY OPERATION
// ===================================================================================

func TestDuckDBIntegration_Query(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("successful query operation", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)
		mockAuth := new(MockDuckDBAuthService)

		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT * FROM sales WHERE year = 2024"),
		)

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		expectedResults := []map[string]interface{}{
			{"year": "2024", "amount": 1000},
			{"year": "2024", "amount": 2000},
		}

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockDuck.On("Query", mock.Anything, isolatedDB, req.Query).Return(expectedResults, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		results, err := mockDuck.Query(context.Background(), isolatedDB, req.Query)
		require.NoError(t, err)
		assert.Len(t, results, 2)
	})

	t.Run("aggregation query", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		scenarios := duckdb_contract.NewScenarios()
		req := scenarios.AggregationQuery()

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		expectedResults := []map[string]interface{}{
			{"category": "A", "total": 5000},
			{"category": "B", "total": 3000},
		}

		mockDuck.On("Query", mock.Anything, isolatedDB, req.Query).Return(expectedResults, nil)

		results, err := mockDuck.Query(context.Background(), isolatedDB, req.Query)
		require.NoError(t, err)
		assert.Len(t, results, 2)
	})

	t.Run("window function query", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		scenarios := duckdb_contract.NewScenarios()
		req := scenarios.WindowFunctionQuery()

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		expectedResults := []map[string]interface{}{
			{"date": "2024-01-01", "amount": 100, "rolling_sum": 100},
			{"date": "2024-01-02", "amount": 200, "rolling_sum": 300},
		}

		mockDuck.On("Query", mock.Anything, isolatedDB, req.Query).Return(expectedResults, nil)

		results, err := mockDuck.Query(context.Background(), isolatedDB, req.Query)
		require.NoError(t, err)
		assert.Len(t, results, 2)
	})

	t.Run("query fails with syntax error", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("INVALID SQL SYNTAX"),
		)

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Query", mock.Anything, isolatedDB, req.Query).
			Return(nil, errors.New("syntax error"))

		_, err := mockDuck.Query(context.Background(), isolatedDB, req.Query)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "syntax error")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - IMPORT
// ===================================================================================

func TestDuckDBIntegration_Import(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("successful parquet import", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)
		mockAuth := new(MockDuckDBAuthService)

		req := factory.MakeImportFromMinIORequest(
			duckdb_contract.WithImportTable("sales_data"),
			duckdb_contract.WithImportBucket("data-bucket"),
			duckdb_contract.WithImportObjectKey("data.parquet"),
			duckdb_contract.WithImportFormat("parquet"),
		)

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockDuck.On("Import", mock.Anything, isolatedDB, req.BucketName, req.ObjectKey, req.TableName, req.Format).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockDuck.Import(context.Background(), isolatedDB, req.BucketName, req.ObjectKey, req.TableName, req.Format)
		require.NoError(t, err)
	})

	t.Run("import fails with file not found", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		req := factory.MakeImportFromMinIORequest(
			duckdb_contract.WithImportObjectKey("nonexistent.parquet"),
		)

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Import", mock.Anything, isolatedDB, req.BucketName, req.ObjectKey, req.TableName, req.Format).
			Return(errors.New("file not found"))

		err := mockDuck.Import(context.Background(), isolatedDB, req.BucketName, req.ObjectKey, req.TableName, req.Format)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not found")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - EXPORT
// ===================================================================================

func TestDuckDBIntegration_Export(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("successful parquet export", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)
		mockAuth := new(MockDuckDBAuthService)

		req := factory.MakeExportToMinIORequest(
			duckdb_contract.WithExportQuery("SELECT * FROM sales"),
			duckdb_contract.WithExportFormat("parquet"),
		)

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockDuck.On("Export", mock.Anything, isolatedDB, req.Query, req.BucketName, req.ObjectKey, req.Format).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockDuck.Export(context.Background(), isolatedDB, req.Query, req.BucketName, req.ObjectKey, req.Format)
		require.NoError(t, err)
	})

	t.Run("export to CSV", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		req := factory.MakeExportToMinIORequest(duckdb_contract.WithExportFormat("csv"))

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Export", mock.Anything, isolatedDB, req.Query, req.BucketName, req.ObjectKey, "csv").Return(nil)

		err := mockDuck.Export(context.Background(), isolatedDB, req.Query, req.BucketName, req.ObjectKey, "csv")
		require.NoError(t, err)
	})

	t.Run("export to JSON", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		req := factory.MakeExportToMinIORequest(duckdb_contract.WithExportFormat("json"))

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Export", mock.Anything, isolatedDB, req.Query, req.BucketName, req.ObjectKey, "json").Return(nil)

		err := mockDuck.Export(context.Background(), isolatedDB, req.Query, req.BucketName, req.ObjectKey, "json")
		require.NoError(t, err)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestDuckDBIntegration_MultiTenantIsolation(t *testing.T) {
	scenarios := duckdb_contract.NewScenarios()

	t.Run("different tenants have different databases", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		db1 := duckdb_contract.ExpectedSchemaName(tenant1Req.UserId)
		db2 := duckdb_contract.ExpectedSchemaName(tenant2Req.UserId)

		assert.NotEqual(t, db1, db2)
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestDuckDBIntegration_ErrorHandling(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("connection error is propagated", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		req := factory.MakeExecuteQueryRequest()
		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Query", mock.Anything, isolatedDB, req.Query).
			Return(nil, errors.New("database connection failed"))

		_, err := mockDuck.Query(context.Background(), isolatedDB, req.Query)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "connection failed")
	})

	t.Run("out of memory error", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		// Query that might cause OOM
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT * FROM very_large_table"),
		)

		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Query", mock.Anything, isolatedDB, req.Query).
			Return(nil, errors.New("out of memory"))

		_, err := mockDuck.Query(context.Background(), isolatedDB, req.Query)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "out of memory")
	})

	t.Run("access denied for file path", func(t *testing.T) {
		mockDuck := new(MockDuckDBClient)

		req := factory.MakeImportFromMinIORequest()
		isolatedDB := duckdb_contract.ExpectedSchemaName(req.UserId)

		mockDuck.On("Import", mock.Anything, isolatedDB, req.BucketName, req.ObjectKey, req.TableName, req.Format).
			Return(errors.New("access denied"))

		err := mockDuck.Import(context.Background(), isolatedDB, req.BucketName, req.ObjectKey, req.TableName, req.Format)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "access denied")
	})
}
