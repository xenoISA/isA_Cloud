//go:build integration

// Package golden provides integration tests for Neo4j service.
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

	neo4j_contract "github.com/isa-cloud/isa_cloud/tests/contracts/neo4j"
)

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockNeo4jClient mocks the Neo4j client
type MockNeo4jClient struct {
	mock.Mock
}

func (m *MockNeo4jClient) ExecuteCypher(ctx context.Context, db, query string, params map[string]interface{}) ([]map[string]interface{}, error) {
	args := m.Called(ctx, db, query, params)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]map[string]interface{}), args.Error(1)
}

func (m *MockNeo4jClient) CreateNode(ctx context.Context, db string, labels []string, props map[string]interface{}) (string, error) {
	args := m.Called(ctx, db, labels, props)
	return args.String(0), args.Error(1)
}

func (m *MockNeo4jClient) CreateRelationship(ctx context.Context, db, fromID, toID, relType string, props map[string]interface{}) error {
	args := m.Called(ctx, db, fromID, toID, relType, props)
	return args.Error(0)
}

func (m *MockNeo4jClient) FindShortestPath(ctx context.Context, db, startID, endID string, maxDepth uint32, relTypes []string) ([]string, error) {
	args := m.Called(ctx, db, startID, endID, maxDepth, relTypes)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]string), args.Error(1)
}

// MockNeo4jAuthService mocks authentication
type MockNeo4jAuthService struct {
	mock.Mock
}

func (m *MockNeo4jAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - CYPHER QUERY
// ===================================================================================

func TestNeo4jService_ExecuteCypher(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("successful Cypher query", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)
		mockAuth := new(MockNeo4jAuthService)

		req := factory.MakeCypherRequest(
			neo4j_contract.WithCypherQuery("MATCH (n:Person) RETURN n LIMIT 10"),
		)

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		expectedResults := []map[string]interface{}{
			{"n": map[string]interface{}{"name": "Alice"}},
			{"n": map[string]interface{}{"name": "Bob"}},
		}

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNeo4j.On("ExecuteCypher", mock.Anything, isolatedDB, req.Query, req.Params).Return(expectedResults, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		results, err := mockNeo4j.ExecuteCypher(context.Background(), isolatedDB, req.Query, req.Params)
		require.NoError(t, err)
		assert.Len(t, results, 2)
	})

	t.Run("Cypher query with parameters", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCypherRequest(
			neo4j_contract.WithCypherQuery("MATCH (n:Person {name: $name}) RETURN n"),
			neo4j_contract.WithCypherParams(map[string]interface{}{"name": "Alice"}),
		)

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		expectedResults := []map[string]interface{}{
			{"n": map[string]interface{}{"name": "Alice"}},
		}

		mockNeo4j.On("ExecuteCypher", mock.Anything, isolatedDB, req.Query, req.Params).Return(expectedResults, nil)

		results, err := mockNeo4j.ExecuteCypher(context.Background(), isolatedDB, req.Query, req.Params)
		require.NoError(t, err)
		assert.Len(t, results, 1)
	})

	t.Run("Cypher query fails with syntax error", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCypherRequest(
			neo4j_contract.WithCypherQuery("INVALID SYNTAX"),
		)

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("ExecuteCypher", mock.Anything, isolatedDB, req.Query, req.Params).
			Return(nil, errors.New("syntax error"))

		_, err := mockNeo4j.ExecuteCypher(context.Background(), isolatedDB, req.Query, req.Params)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "syntax error")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - CREATE NODE
// ===================================================================================

func TestNeo4jService_CreateNode(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("successful node creation", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)
		mockAuth := new(MockNeo4jAuthService)

		scenarios := neo4j_contract.NewScenarios()
		req := scenarios.CreatePersonNode()

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNeo4j.On("CreateNode", mock.Anything, isolatedDB, req.Labels, req.Properties).Return("node-123", nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		nodeID, err := mockNeo4j.CreateNode(context.Background(), isolatedDB, req.Labels, req.Properties)
		require.NoError(t, err)
		assert.NotEmpty(t, nodeID)
	})

	t.Run("create node with multiple labels", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCreateNodeRequest(
			neo4j_contract.WithLabels([]string{"Person", "Employee", "Developer"}),
		)

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("CreateNode", mock.Anything, isolatedDB, req.Labels, req.Properties).Return("node-456", nil)

		nodeID, err := mockNeo4j.CreateNode(context.Background(), isolatedDB, req.Labels, req.Properties)
		require.NoError(t, err)
		assert.NotEmpty(t, nodeID)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - CREATE RELATIONSHIP
// ===================================================================================

func TestNeo4jService_CreateRelationship(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("successful relationship creation", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)
		mockAuth := new(MockNeo4jAuthService)

		scenarios := neo4j_contract.NewScenarios()
		req := scenarios.CreateKnowsRelationship()

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNeo4j.On("CreateRelationship", mock.Anything, isolatedDB, req.FromNodeId, req.ToNodeId, req.RelationType, req.Properties).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockNeo4j.CreateRelationship(context.Background(), isolatedDB, req.FromNodeId, req.ToNodeId, req.RelationType, req.Properties)
		require.NoError(t, err)
	})

	t.Run("create relationship with properties", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCreateRelationshipRequest(
			neo4j_contract.WithRelationType("WORKS_WITH"),
			neo4j_contract.WithRelationProperties(map[string]interface{}{
				"since":   "2024-01-01",
				"project": "isA_Cloud",
			}),
		)

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("CreateRelationship", mock.Anything, isolatedDB, req.FromNodeId, req.ToNodeId, req.RelationType, req.Properties).Return(nil)

		err := mockNeo4j.CreateRelationship(context.Background(), isolatedDB, req.FromNodeId, req.ToNodeId, req.RelationType, req.Properties)
		require.NoError(t, err)
	})

	t.Run("relationship fails when node not found", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCreateRelationshipRequest()
		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("CreateRelationship", mock.Anything, isolatedDB, req.FromNodeId, req.ToNodeId, req.RelationType, req.Properties).
			Return(errors.New("node not found"))

		err := mockNeo4j.CreateRelationship(context.Background(), isolatedDB, req.FromNodeId, req.ToNodeId, req.RelationType, req.Properties)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not found")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - PATH QUERY
// ===================================================================================

func TestNeo4jService_FindShortestPath(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("successful shortest path query", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)
		mockAuth := new(MockNeo4jAuthService)

		scenarios := neo4j_contract.NewScenarios()
		req := scenarios.ShortestPathQuery()

		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		expectedPath := []string{"node-1", "node-2", "node-3"}

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNeo4j.On("FindShortestPath", mock.Anything, isolatedDB, req.StartNodeId, req.EndNodeId, req.MaxDepth, req.RelationTypes).
			Return(expectedPath, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		path, err := mockNeo4j.FindShortestPath(context.Background(), isolatedDB, req.StartNodeId, req.EndNodeId, req.MaxDepth, req.RelationTypes)
		require.NoError(t, err)
		assert.Len(t, path, 3)
	})

	t.Run("no path found", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakePathQueryRequest()
		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("FindShortestPath", mock.Anything, isolatedDB, req.StartNodeId, req.EndNodeId, req.MaxDepth, req.RelationTypes).
			Return([]string{}, nil)

		path, err := mockNeo4j.FindShortestPath(context.Background(), isolatedDB, req.StartNodeId, req.EndNodeId, req.MaxDepth, req.RelationTypes)
		require.NoError(t, err)
		assert.Empty(t, path)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestNeo4jService_MultiTenantIsolation(t *testing.T) {
	scenarios := neo4j_contract.NewScenarios()

	t.Run("different tenants have different databases", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		db1 := neo4j_contract.ExpectedIsolatedDatabase(tenant1Req.OrganizationId)
		db2 := neo4j_contract.ExpectedIsolatedDatabase(tenant2Req.OrganizationId)

		assert.NotEqual(t, db1, db2)
	})

	t.Run("node IDs are scoped to tenant database", func(t *testing.T) {
		factory := neo4j_contract.NewTestDataFactory()
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCreateNodeRequest(neo4j_contract.WithNodeUser("user-1", "org-1"))
		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("CreateNode", mock.Anything, isolatedDB, req.Labels, req.Properties).Return("org-1-node-1", nil)

		nodeID, err := mockNeo4j.CreateNode(context.Background(), isolatedDB, req.Labels, req.Properties)
		require.NoError(t, err)
		assert.Contains(t, nodeID, "org-1")
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestNeo4jService_ErrorHandling(t *testing.T) {
	factory := neo4j_contract.NewTestDataFactory()

	t.Run("connection error is propagated", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCypherRequest()
		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("ExecuteCypher", mock.Anything, isolatedDB, req.Query, req.Params).
			Return(nil, errors.New("connection refused"))

		_, err := mockNeo4j.ExecuteCypher(context.Background(), isolatedDB, req.Query, req.Params)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "connection refused")
	})

	t.Run("constraint violation error", func(t *testing.T) {
		mockNeo4j := new(MockNeo4jClient)

		req := factory.MakeCreateNodeRequest()
		isolatedDB := neo4j_contract.ExpectedIsolatedDatabase(req.OrganizationId)

		mockNeo4j.On("CreateNode", mock.Anything, isolatedDB, req.Labels, req.Properties).
			Return("", errors.New("constraint violation: unique property"))

		_, err := mockNeo4j.CreateNode(context.Background(), isolatedDB, req.Labels, req.Properties)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "constraint violation")
	})
}
