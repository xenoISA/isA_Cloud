//go:build unit

// Package golden provides unit tests for Neo4j service contracts.
package golden

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"

	neo4j_contract "github.com/isa-cloud/isa_cloud/tests/contracts/neo4j"
)

// ===================================================================================
// TEST: DATA FACTORY - Neo4j
// ===================================================================================

func TestNeo4jTestDataFactory_MakeRunCypherRequest(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeRunCypherRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.Cypher)
	})

	t.Run("accepts custom query via option", func(t *testing.T) {
		customQuery := "MATCH (n:Person) RETURN n LIMIT 10"
		req := factory.MakeRunCypherRequest(neo4j_contract.WithCypher(customQuery))

		assert.Equal(t, customQuery, req.Cypher)
	})

	t.Run("accepts parameters via option", func(t *testing.T) {
		params := map[string]interface{}{
			"name": "Alice",
			"age":  30,
		}
		req := factory.MakeRunCypherRequest(neo4j_contract.WithCypherParams(params))

		assert.NotEmpty(t, req.Parameters)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(neo4j_contract.WithCypherUser("u1", "o1"))

		assert.Equal(t, "u1", req.Metadata.UserId)
		assert.Equal(t, "o1", req.Metadata.OrganizationId)
	})

	t.Run("supports multiple options chained", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("MATCH (n) RETURN n"),
			neo4j_contract.WithCypherUser("user-x", "org-x"),
		)

		assert.Equal(t, "MATCH (n) RETURN n", req.Cypher)
		assert.Equal(t, "user-x", req.Metadata.UserId)
	})
}

func TestNeo4jTestDataFactory_MakeCreateNodeRequest(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("creates valid node request", func(t *testing.T) {
		req := factory.MakeCreateNodeRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.Labels)
		assert.NotNil(t, req.Properties)
	})

	t.Run("accepts labels via option", func(t *testing.T) {
		req := factory.MakeCreateNodeRequest(neo4j_contract.WithLabels("Person", "Employee"))

		assert.Contains(t, req.Labels, "Person")
		assert.Contains(t, req.Labels, "Employee")
	})

	t.Run("accepts properties via option", func(t *testing.T) {
		props := map[string]interface{}{
			"name":  "Alice",
			"email": "alice@example.com",
		}
		req := factory.MakeCreateNodeRequest(neo4j_contract.WithProperties(props))

		assert.NotNil(t, req.Properties)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeCreateNodeRequest(neo4j_contract.WithNodeUser("u1", "o1"))

		assert.Equal(t, "u1", req.Metadata.UserId)
		assert.Equal(t, "o1", req.Metadata.OrganizationId)
	})
}

func TestNeo4jTestDataFactory_MakeCreateRelationshipRequest(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("creates valid relationship request", func(t *testing.T) {
		req := factory.MakeCreateRelationshipRequest(1, 2, "KNOWS")

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.Equal(t, int64(1), req.StartNodeId)
		assert.Equal(t, int64(2), req.EndNodeId)
		assert.Equal(t, "KNOWS", req.Type)
	})

	t.Run("accepts relationship properties via option", func(t *testing.T) {
		props := map[string]interface{}{
			"since":  "2024-01-01",
			"weight": 0.8,
		}
		req := factory.MakeCreateRelationshipRequest(1, 2, "WORKS_WITH",
			neo4j_contract.WithRelationshipProperties(props))

		assert.NotNil(t, req.Properties)
	})
}

func TestNeo4jTestDataFactory_MakeGetShortestPathRequest(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("creates valid path query request", func(t *testing.T) {
		req := factory.MakeGetShortestPathRequest(1, 2)

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.Equal(t, int64(1), req.StartNodeId)
		assert.Equal(t, int64(2), req.EndNodeId)
	})

	t.Run("accepts max depth via option", func(t *testing.T) {
		req := factory.MakeGetShortestPathRequest(1, 2, neo4j_contract.WithMaxDepth(5))

		assert.NotNil(t, req.MaxDepth)
		assert.Equal(t, int32(5), *req.MaxDepth)
	})
}

// ===================================================================================
// TEST: SCENARIOS - Neo4j
// ===================================================================================

func TestNeo4jScenarios(t *testing.T) {
	scenarios := neo4j_contract.NewScenarios()

	t.Run("CreatePerson returns node creation request", func(t *testing.T) {
		req := scenarios.CreatePerson("Alice", "alice@example.com")

		assert.Contains(t, req.Labels, "Person")
	})

	t.Run("CreateCompany returns company node", func(t *testing.T) {
		req := scenarios.CreateCompany("Acme Corp")

		assert.Contains(t, req.Labels, "Company")
	})

	t.Run("KnowsRelationship returns KNOWS relationship", func(t *testing.T) {
		req := scenarios.KnowsRelationship(1, 2)

		assert.Equal(t, "KNOWS", req.Type)
	})

	t.Run("WorksAtRelationship returns WORKS_AT relationship", func(t *testing.T) {
		req := scenarios.WorksAtRelationship(1, 2)

		assert.Equal(t, "WORKS_AT", req.Type)
	})

	t.Run("FindPersonByName returns parameterized query", func(t *testing.T) {
		req := scenarios.FindPersonByName("Alice")

		assert.Contains(t, req.Cypher, "$name")
		assert.NotEmpty(t, req.Parameters)
	})

	t.Run("EmptyQuery for edge case", func(t *testing.T) {
		req := scenarios.EmptyQuery()

		assert.Empty(t, req.Cypher)
	})

	t.Run("SyntaxErrorQuery for edge case", func(t *testing.T) {
		req := scenarios.SyntaxErrorQuery()

		// Contains intentional typos
		assert.Contains(t, req.Cypher, "MTCH")
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.Metadata.UserId, tenant2.Metadata.UserId)
		assert.NotEqual(t, tenant1.Metadata.OrganizationId, tenant2.Metadata.OrganizationId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - Neo4j
// ===================================================================================

func TestNeo4jBusinessRules(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("BR-001: graphs are namespaced by tenant", func(t *testing.T) {
		req := factory.MakeRunCypherRequest()

		isolatedLabel := neo4j_contract.ExpectedOrgLabel(req.Metadata.OrganizationId)

		assert.Contains(t, isolatedLabel, req.Metadata.OrganizationId)
	})

	t.Run("BR-002: requests require user_id and organization_id", func(t *testing.T) {
		req := factory.MakeRunCypherRequest()

		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
	})

	t.Run("BR-003: queries support parameterized values", func(t *testing.T) {
		params := map[string]interface{}{"name": "Alice"}
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("MATCH (n:Person {name: $name}) RETURN n"),
			neo4j_contract.WithCypherParams(params),
		)

		assert.Contains(t, req.Cypher, "$name")
		assert.NotEmpty(t, req.Parameters)
	})

	t.Run("BR-004: nodes can have multiple labels", func(t *testing.T) {
		req := factory.MakeCreateNodeRequest(neo4j_contract.WithLabels("Person", "Employee", "Manager"))

		assert.Len(t, req.Labels, 3)
	})
}

// ===================================================================================
// TEST: EDGE CASES - Neo4j
// ===================================================================================

func TestNeo4jEdgeCases(t *testing.T) {
	scenarios := neo4j_contract.NewScenarios()
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("EC-001: empty query should be rejectable", func(t *testing.T) {
		req := scenarios.EmptyQuery()

		assert.Empty(t, req.Cypher)
	})

	t.Run("EC-002: syntax error query should be rejectable", func(t *testing.T) {
		req := scenarios.SyntaxErrorQuery()

		assert.NotEmpty(t, req.Cypher)
	})

	t.Run("EC-003: very long Cypher query", func(t *testing.T) {
		longQuery := "MATCH " + strings.Repeat("(n)-[:KNOWS]->(m), ", 100) + "(end) RETURN end"
		req := factory.MakeRunCypherRequest(neo4j_contract.WithCypher(longQuery))

		assert.Greater(t, len(req.Cypher), 1000)
	})

	t.Run("EC-008: invalid label with spaces", func(t *testing.T) {
		req := scenarios.InvalidLabel()

		assert.Contains(t, req.Labels[0], " ")
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - Neo4j
// ===================================================================================

func TestNeo4jMultiTenantIsolation(t *testing.T) {
	scenarios := neo4j_contract.NewScenarios()

	t.Run("different tenants have different labels", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		label1 := neo4j_contract.ExpectedOrgLabel(tenant1.Metadata.OrganizationId)
		label2 := neo4j_contract.ExpectedOrgLabel(tenant2.Metadata.OrganizationId)

		assert.NotEqual(t, label1, label2)
	})
}

// ===================================================================================
// TEST: CYPHER QUERY PATTERNS
// ===================================================================================

func TestNeo4jCypherPatterns(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("MATCH query pattern", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("MATCH (n:Person) RETURN n"),
		)

		assert.Contains(t, strings.ToUpper(req.Cypher), "MATCH")
	})

	t.Run("CREATE query pattern", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("CREATE (n:Person {name: $name}) RETURN n"),
		)

		assert.Contains(t, strings.ToUpper(req.Cypher), "CREATE")
	})

	t.Run("relationship traversal pattern", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("MATCH (a:Person)-[:KNOWS*1..3]->(b:Person) RETURN a, b"),
		)

		assert.Contains(t, req.Cypher, "KNOWS")
		assert.Contains(t, req.Cypher, "1..3")
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestNeo4jAssertionHelpers(t *testing.T) {
	t.Run("ExpectedOrgLabel formats correctly", func(t *testing.T) {
		label := neo4j_contract.ExpectedOrgLabel("org-001")

		assert.Contains(t, label, "org-001")
	})

	t.Run("DefaultOrgLabel uses test defaults", func(t *testing.T) {
		label := neo4j_contract.DefaultOrgLabel()

		assert.Contains(t, label, "test-org-001")
	})
}
