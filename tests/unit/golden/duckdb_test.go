//go:build unit

// Package golden provides unit tests for DuckDB service contracts.
package golden

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	duckdb_contract "github.com/isa-cloud/isa_cloud/tests/contracts/duckdb"
)

// ===================================================================================
// TEST: DATA FACTORY - DuckDB
// ===================================================================================

func TestDuckDBTestDataFactory_MakeExecuteQueryRequest(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.DatabaseId)
		assert.NotEmpty(t, req.Query)
	})

	t.Run("accepts custom query via option", func(t *testing.T) {
		customQuery := "SELECT * FROM sales WHERE year = 2024"
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithQuery(customQuery))

		assert.Equal(t, customQuery, req.Query)
	})

	t.Run("accepts database ID via option", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithDatabaseID("db-123"))

		assert.Equal(t, "db-123", req.DatabaseId)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithQueryUser("u1"))

		assert.Equal(t, "u1", req.UserId)
	})

	t.Run("accepts max rows via option", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithMaxRows(1000))

		assert.Equal(t, int32(1000), req.MaxRows)
	})

	t.Run("accepts timeout via option", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithTimeout(60))

		assert.Equal(t, int32(60), req.TimeoutSeconds)
	})

	t.Run("accepts explain flag via option", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithExplain(true))

		assert.True(t, req.Explain)
	})

	t.Run("supports multiple options chained", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery("SELECT 1"),
			duckdb_contract.WithMaxRows(500),
			duckdb_contract.WithQueryUser("user-x"),
		)

		assert.Equal(t, "SELECT 1", req.Query)
		assert.Equal(t, int32(500), req.MaxRows)
		assert.Equal(t, "user-x", req.UserId)
	})
}

func TestDuckDBTestDataFactory_MakeExecuteStatementRequest(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("creates valid statement request with defaults", func(t *testing.T) {
		req := factory.MakeExecuteStatementRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.DatabaseId)
		assert.NotEmpty(t, req.Statement)
	})

	t.Run("accepts custom statement via option", func(t *testing.T) {
		stmt := "CREATE TABLE test (id INTEGER)"
		req := factory.MakeExecuteStatementRequest(duckdb_contract.WithStatement(stmt))

		assert.Equal(t, stmt, req.Statement)
	})
}

func TestDuckDBTestDataFactory_MakeImportFromMinIORequest(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("creates valid import request with defaults", func(t *testing.T) {
		req := factory.MakeImportFromMinIORequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.DatabaseId)
		assert.NotEmpty(t, req.TableName)
		assert.NotEmpty(t, req.BucketName)
		assert.NotEmpty(t, req.ObjectKey)
	})

	t.Run("accepts table name via option", func(t *testing.T) {
		req := factory.MakeImportFromMinIORequest(duckdb_contract.WithImportTable("sales_data"))

		assert.Equal(t, "sales_data", req.TableName)
	})

	t.Run("accepts bucket name via option", func(t *testing.T) {
		req := factory.MakeImportFromMinIORequest(duckdb_contract.WithImportBucket("data-bucket"))

		assert.Equal(t, "data-bucket", req.BucketName)
	})

	t.Run("accepts object key via option", func(t *testing.T) {
		req := factory.MakeImportFromMinIORequest(duckdb_contract.WithImportObjectKey("data/2024/sales.parquet"))

		assert.Equal(t, "data/2024/sales.parquet", req.ObjectKey)
	})

	t.Run("accepts format via option", func(t *testing.T) {
		req := factory.MakeImportFromMinIORequest(duckdb_contract.WithImportFormat("csv"))

		assert.Equal(t, "csv", req.Format)
	})
}

func TestDuckDBTestDataFactory_MakeExportToMinIORequest(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("creates valid export request with defaults", func(t *testing.T) {
		req := factory.MakeExportToMinIORequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.DatabaseId)
		assert.NotEmpty(t, req.Query)
		assert.NotEmpty(t, req.BucketName)
		assert.NotEmpty(t, req.ObjectKey)
	})

	t.Run("accepts export query via option", func(t *testing.T) {
		req := factory.MakeExportToMinIORequest(duckdb_contract.WithExportQuery("SELECT * FROM results"))

		assert.Equal(t, "SELECT * FROM results", req.Query)
	})

	t.Run("accepts export format via option", func(t *testing.T) {
		req := factory.MakeExportToMinIORequest(duckdb_contract.WithExportFormat("csv"))

		assert.Equal(t, "csv", req.Format)
	})
}

func TestDuckDBTestDataFactory_MakeCreateDatabaseRequest(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("creates valid database request with defaults", func(t *testing.T) {
		req := factory.MakeCreateDatabaseRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.DatabaseName)
	})

	t.Run("accepts database name via option", func(t *testing.T) {
		req := factory.MakeCreateDatabaseRequest(duckdb_contract.WithDatabaseName("analytics-db"))

		assert.Equal(t, "analytics-db", req.DatabaseName)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeCreateDatabaseRequest(duckdb_contract.WithDatabaseUser("u1", "o1"))

		assert.Equal(t, "u1", req.UserId)
		assert.Equal(t, "o1", req.OrganizationId)
	})
}

// ===================================================================================
// TEST: SCENARIOS - DuckDB
// ===================================================================================

func TestDuckDBScenarios(t *testing.T) {
	scenarios := duckdb_contract.NewScenarios()

	t.Run("SimpleSelect returns usable request", func(t *testing.T) {
		req := scenarios.SimpleSelect()

		require.NotNil(t, req)
		assert.NotEmpty(t, req.Query)
		assert.Contains(t, strings.ToUpper(req.Query), "SELECT")
	})

	t.Run("AggregationQuery uses aggregation functions", func(t *testing.T) {
		req := scenarios.AggregationQuery()

		query := strings.ToUpper(req.Query)
		hasAgg := strings.Contains(query, "SUM") ||
			strings.Contains(query, "AVG") ||
			strings.Contains(query, "COUNT")
		assert.True(t, hasAgg)
	})

	t.Run("WindowFunctionQuery uses window functions", func(t *testing.T) {
		req := scenarios.WindowFunctionQuery()

		query := strings.ToUpper(req.Query)
		assert.True(t, strings.Contains(query, "OVER"))
	})

	t.Run("TimeSeriesQuery groups by time", func(t *testing.T) {
		req := scenarios.TimeSeriesQuery("created_at")

		query := strings.ToUpper(req.Query)
		assert.True(t, strings.Contains(query, "DATE_TRUNC"))
	})

	t.Run("PaginatedQuery supports pagination", func(t *testing.T) {
		req := scenarios.PaginatedQuery(2, 100)

		query := strings.ToUpper(req.Query)
		assert.True(t, strings.Contains(query, "LIMIT"))
		assert.True(t, strings.Contains(query, "OFFSET"))
	})

	t.Run("ParquetImport returns import request", func(t *testing.T) {
		req := scenarios.ParquetImport("sales", "data/sales.parquet")

		assert.Equal(t, "sales", req.TableName)
		assert.Equal(t, "parquet", req.Format)
	})

	t.Run("CSVImport returns CSV import request", func(t *testing.T) {
		req := scenarios.CSVImport("users", "data/users.csv")

		assert.Equal(t, "users", req.TableName)
		assert.Equal(t, "csv", req.Format)
	})

	t.Run("EmptyQuery for edge case", func(t *testing.T) {
		req := scenarios.EmptyQuery()

		assert.Empty(t, req.Query)
	})

	t.Run("SyntaxErrorQuery for edge case", func(t *testing.T) {
		req := scenarios.SyntaxErrorQuery()

		// Contains intentional typos
		assert.Contains(t, req.Query, "SELCT")
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.UserId, tenant2.UserId)
		assert.NotEqual(t, tenant1.OrganizationId, tenant2.OrganizationId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - DuckDB
// ===================================================================================

func TestDuckDBBusinessRules(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("BR-001: databases are isolated by tenant", func(t *testing.T) {
		req := factory.MakeCreateDatabaseRequest()

		isolatedSchema := duckdb_contract.ExpectedSchemaName(req.OrganizationId)

		assert.Contains(t, isolatedSchema, req.OrganizationId)
	})

	t.Run("BR-002: requests require user_id", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest()

		assert.NotEmpty(t, req.UserId)
	})

	t.Run("BR-003: queries support timeout", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithTimeout(120))

		assert.Equal(t, int32(120), req.TimeoutSeconds)
	})

	t.Run("BR-004: import supports multiple formats", func(t *testing.T) {
		formats := []string{"parquet", "csv"}

		for _, format := range formats {
			req := factory.MakeImportFromMinIORequest(duckdb_contract.WithImportFormat(format))
			assert.Equal(t, format, req.Format)
		}
	})

	t.Run("BR-005: export supports multiple formats", func(t *testing.T) {
		formats := []string{"parquet", "csv"}

		for _, format := range formats {
			req := factory.MakeExportToMinIORequest(duckdb_contract.WithExportFormat(format))
			assert.Equal(t, format, req.Format)
		}
	})
}

// ===================================================================================
// TEST: EDGE CASES - DuckDB
// ===================================================================================

func TestDuckDBEdgeCases(t *testing.T) {
	scenarios := duckdb_contract.NewScenarios()
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("EC-001: empty query should be rejectable", func(t *testing.T) {
		req := scenarios.EmptyQuery()

		assert.Empty(t, req.Query)
	})

	t.Run("EC-002: syntax error query should be rejectable", func(t *testing.T) {
		req := scenarios.SyntaxErrorQuery()

		assert.NotEmpty(t, req.Query)
	})

	t.Run("EC-003: non-existent table query", func(t *testing.T) {
		req := scenarios.NonExistentTable()

		assert.Contains(t, req.Query, "non_existent_table")
	})

	t.Run("EC-005: heavy query (memory intensive)", func(t *testing.T) {
		req := scenarios.HeavyQuery()

		assert.Contains(t, strings.ToUpper(req.Query), "CROSS JOIN")
	})

	t.Run("EC-009: division by zero query", func(t *testing.T) {
		req := scenarios.DivisionByZero()

		assert.Contains(t, req.Query, "1/0")
	})

	t.Run("EC-002: very long query", func(t *testing.T) {
		longQuery := "SELECT " + strings.Repeat("column, ", 500) + "id FROM large_table"
		req := factory.MakeExecuteQueryRequest(duckdb_contract.WithQuery(longQuery))

		assert.Greater(t, len(req.Query), 3000)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - DuckDB
// ===================================================================================

func TestDuckDBMultiTenantIsolation(t *testing.T) {
	scenarios := duckdb_contract.NewScenarios()

	t.Run("different tenants have different schemas", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		schema1 := duckdb_contract.ExpectedSchemaName(tenant1.OrganizationId)
		schema2 := duckdb_contract.ExpectedSchemaName(tenant2.OrganizationId)

		assert.NotEqual(t, schema1, schema2)
	})
}

// ===================================================================================
// TEST: ANALYTICAL QUERY PATTERNS
// ===================================================================================

func TestDuckDBAnalyticalPatterns(t *testing.T) {
	factory := duckdb_contract.NewTestDataFactory()

	t.Run("aggregation with GROUP BY", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery(`
				SELECT category, SUM(amount) as total
				FROM sales
				GROUP BY category
			`),
		)

		query := strings.ToUpper(req.Query)
		assert.Contains(t, query, "GROUP BY")
		assert.Contains(t, query, "SUM")
	})

	t.Run("window function", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery(`
				SELECT
					date,
					amount,
					SUM(amount) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as rolling_sum
				FROM sales
			`),
		)

		query := strings.ToUpper(req.Query)
		assert.Contains(t, query, "OVER")
		assert.Contains(t, query, "ROWS BETWEEN")
	})

	t.Run("common table expression (CTE)", func(t *testing.T) {
		req := factory.MakeExecuteQueryRequest(
			duckdb_contract.WithQuery(`
				WITH monthly_sales AS (
					SELECT DATE_TRUNC('month', date) as month, SUM(amount) as total
					FROM sales
					GROUP BY 1
				)
				SELECT * FROM monthly_sales
			`),
		)

		query := strings.ToUpper(req.Query)
		assert.Contains(t, query, "WITH")
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestDuckDBAssertionHelpers(t *testing.T) {
	t.Run("ExpectedSchemaName formats correctly", func(t *testing.T) {
		schema := duckdb_contract.ExpectedSchemaName("org-001")

		assert.Contains(t, schema, "org-001")
	})

	t.Run("DefaultSchemaName uses test defaults", func(t *testing.T) {
		schema := duckdb_contract.DefaultSchemaName()

		assert.Contains(t, schema, "test-org-001")
	})

	t.Run("QualifiedTableName formats correctly", func(t *testing.T) {
		table := duckdb_contract.QualifiedTableName("org-001", "sales")

		assert.Contains(t, table, "org-001")
		assert.Contains(t, table, "sales")
	})
}
