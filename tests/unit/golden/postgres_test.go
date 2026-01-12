//go:build unit

// Package golden provides unit tests for PostgreSQL service contracts.
package golden

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/types/known/structpb"

	postgres_contract "github.com/isa-cloud/isa_cloud/tests/contracts/postgres"
)

// ===================================================================================
// TEST: DATA FACTORY - PostgreSQL
// ===================================================================================

func TestPostgresTestDataFactory_MakeQueryRequest(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeQueryRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.Sql)
	})

	t.Run("accepts custom SQL via option", func(t *testing.T) {
		customSQL := "SELECT * FROM users WHERE active = true"
		req := factory.MakeQueryRequest(postgres_contract.WithSQL(customSQL))

		assert.Equal(t, customSQL, req.Sql)
	})

	t.Run("accepts parameters via option", func(t *testing.T) {
		param1, _ := structpb.NewValue("param1")
		req := factory.MakeQueryRequest(postgres_contract.WithParams(param1))

		assert.Len(t, req.Params, 1)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeQueryRequest(postgres_contract.WithQueryUser("u1", "o1"))

		assert.Equal(t, "u1", req.Metadata.UserId)
		assert.Equal(t, "o1", req.Metadata.OrganizationId)
	})

	t.Run("supports multiple options chained", func(t *testing.T) {
		param, _ := structpb.NewValue("p1")
		req := factory.MakeQueryRequest(
			postgres_contract.WithSQL("SELECT 1"),
			postgres_contract.WithParams(param),
			postgres_contract.WithQueryUser("user-x", "org-x"),
		)

		assert.Equal(t, "SELECT 1", req.Sql)
		assert.Len(t, req.Params, 1)
		assert.Equal(t, "user-x", req.Metadata.UserId)
	})
}

func TestPostgresTestDataFactory_MakeExecuteRequest(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("creates valid execute request with defaults", func(t *testing.T) {
		req := factory.MakeExecuteRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.Sql)
	})

	t.Run("accepts INSERT statement", func(t *testing.T) {
		stmt := "INSERT INTO users (name) VALUES ($1)"
		req := factory.MakeExecuteRequest(postgres_contract.WithExecuteSQL(stmt))

		assert.Equal(t, stmt, req.Sql)
	})
}

func TestPostgresTestDataFactory_MakeBeginTransactionRequest(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	t.Run("creates valid transaction request", func(t *testing.T) {
		req := factory.MakeBeginTransactionRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
	})

	t.Run("accepts isolation level", func(t *testing.T) {
		req := factory.MakeBeginTransactionRequest(postgres_contract.WithIsolationLevel("SERIALIZABLE"))

		assert.Equal(t, "SERIALIZABLE", req.IsolationLevel)
	})
}

// ===================================================================================
// TEST: SCENARIOS - PostgreSQL
// ===================================================================================

func TestPostgresScenarios(t *testing.T) {
	scenarios := postgres_contract.NewScenarios()

	t.Run("SimpleSelect returns usable request", func(t *testing.T) {
		req := scenarios.SimpleSelect()

		require.NotNil(t, req)
		assert.Contains(t, strings.ToUpper(req.Sql), "SELECT")
	})

	t.Run("InsertUser returns INSERT statement", func(t *testing.T) {
		req := scenarios.InsertUser()

		assert.Contains(t, strings.ToUpper(req.Sql), "INSERT")
	})

	t.Run("SimpleSelect query uses parameters", func(t *testing.T) {
		req := scenarios.SimpleSelect()

		assert.Contains(t, req.Sql, "$1")
	})

	t.Run("EmptyQuery for edge case", func(t *testing.T) {
		req := scenarios.EmptyQuery()

		assert.Empty(t, req.Sql)
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.Metadata.UserId, tenant2.Metadata.UserId)
		assert.NotEqual(t, tenant1.Metadata.OrganizationId, tenant2.Metadata.OrganizationId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - PostgreSQL
// ===================================================================================

func TestPostgresBusinessRules(t *testing.T) {
	factory := postgres_contract.NewTestDataFactory()

	// BR-001: Schema Isolation
	t.Run("BR-001: queries target tenant schema", func(t *testing.T) {
		schema := postgres_contract.ExpectedIsolatedSchema("org-001", "user-001")

		assert.Contains(t, schema, "org-001")
	})

	// BR-002: Required Auth Fields
	t.Run("BR-002: requests require user_id and organization_id", func(t *testing.T) {
		req := factory.MakeQueryRequest()

		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
	})

	// BR-003: Parameterized Queries
	t.Run("BR-003: queries support parameterized values", func(t *testing.T) {
		param, _ := structpb.NewValue("123")
		req := factory.MakeQueryRequest(
			postgres_contract.WithSQL("SELECT * FROM users WHERE id = $1"),
			postgres_contract.WithParams(param),
		)

		assert.Contains(t, req.Sql, "$1")
		assert.Len(t, req.Params, 1)
	})

	// BR-005: Read Replica Routing
	t.Run("BR-005: SELECT queries can use read replicas", func(t *testing.T) {
		req := factory.MakeQueryRequest(postgres_contract.WithSQL("SELECT * FROM users"))

		isReadOnly := strings.HasPrefix(strings.ToUpper(strings.TrimSpace(req.Sql)), "SELECT")
		assert.True(t, isReadOnly)
	})
}

// ===================================================================================
// TEST: EDGE CASES - PostgreSQL
// ===================================================================================

func TestPostgresEdgeCases(t *testing.T) {
	scenarios := postgres_contract.NewScenarios()
	factory := postgres_contract.NewTestDataFactory()

	// EC-001: Empty Query
	t.Run("EC-001: empty query should be rejectable", func(t *testing.T) {
		req := scenarios.EmptyQuery()

		assert.Empty(t, req.Sql)
	})

	// EC-002: Very Long Query
	t.Run("EC-002: very long query", func(t *testing.T) {
		longQuery := "SELECT " + strings.Repeat("column, ", 1000) + "id FROM table"
		req := factory.MakeQueryRequest(postgres_contract.WithSQL(longQuery))

		assert.Greater(t, len(req.Sql), 5000)
	})

	// EC-005: Large Result Set
	t.Run("EC-005: query that could return large result set", func(t *testing.T) {
		req := factory.MakeQueryRequest(
			postgres_contract.WithSQL("SELECT * FROM large_table"),
		)

		assert.NotContains(t, strings.ToUpper(req.Sql), "LIMIT")
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - PostgreSQL
// ===================================================================================

func TestPostgresMultiTenantIsolation(t *testing.T) {
	scenarios := postgres_contract.NewScenarios()

	t.Run("different tenants have different schemas", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		schema1 := postgres_contract.ExpectedIsolatedSchema(tenant1.Metadata.OrganizationId, tenant1.Metadata.UserId)
		schema2 := postgres_contract.ExpectedIsolatedSchema(tenant2.Metadata.OrganizationId, tenant2.Metadata.UserId)

		assert.NotEqual(t, schema1, schema2)
	})

	t.Run("schema isolation format is correct", func(t *testing.T) {
		schema := postgres_contract.ExpectedIsolatedSchema("acme-corp", "user-001")

		assert.Contains(t, schema, "acme-corp")
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestPostgresAssertionHelpers(t *testing.T) {
	t.Run("ExpectedIsolatedSchema formats correctly", func(t *testing.T) {
		schema := postgres_contract.ExpectedIsolatedSchema("org-001", "user-001")

		assert.Contains(t, schema, "org-001")
		assert.Contains(t, schema, "user-001")
	})
}
