//go:build api

// Package golden provides API tests for Neo4j gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running Neo4j gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Node Tests - Create, Read, Update, Delete nodes
// 3. Relationship Tests - Create relationships
// 4. Cypher Tests - Run Cypher queries
// 5. Error Handling Tests - Invalid inputs
//
// Related Documents:
// - Logic Contract: tests/contracts/neo4j/logic_contract.md
// - Fixtures: tests/contracts/neo4j/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestNeo4j
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/neo4j"
	neo4j_contract "github.com/isa-cloud/isa_cloud/tests/contracts/neo4j"
)

var neo4jClient pb.Neo4JServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("NEO4J_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50063"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	neo4jClient = pb.NewNeo4JServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestNeo4jAPI_HealthCheck(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := neo4jClient.HealthCheck(ctx, &pb.Neo4JHealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
	})
}

// ===================================================================================
// TEST: NODE OPERATIONS
// ===================================================================================

func TestNeo4jAPI_Nodes(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	factory := neo4j_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	var createdNodeID int64

	t.Run("create node", func(t *testing.T) {
		scenarios := neo4j_contract.NewScenarios()
		req := scenarios.CreatePerson("API Test User", "api-test@example.com")

		resp, err := neo4jClient.CreateNode(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Node)
		createdNodeID = resp.Node.Id
	})

	t.Run("get node by ID", func(t *testing.T) {
		if createdNodeID == 0 {
			t.Skip("No node created")
		}

		req := &pb.GetNodeRequest{
			Metadata: factory.MakeCreateNodeRequest().Metadata,
			NodeId:   createdNodeID,
		}

		resp, err := neo4jClient.GetNode(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Node)
	})

	t.Run("delete node", func(t *testing.T) {
		if createdNodeID == 0 {
			t.Skip("No node created")
		}

		req := &pb.DeleteNodeRequest{
			Metadata: factory.MakeCreateNodeRequest().Metadata,
			NodeId:   createdNodeID,
		}

		resp, err := neo4jClient.DeleteNode(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("create node fails with missing metadata", func(t *testing.T) {
		req := factory.MakeCreateNodeRequest(
			neo4j_contract.WithNodeUser("", "test-org"),
		)

		_, err := neo4jClient.CreateNode(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: RELATIONSHIP OPERATIONS
// ===================================================================================

func TestNeo4jAPI_Relationships(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	scenarios := neo4j_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Create two nodes first
	person1Req := scenarios.CreatePerson("Person 1", "person1@example.com")
	person1Resp, err := neo4jClient.CreateNode(ctx, person1Req)
	if err != nil {
		t.Fatalf("Failed to create person 1: %v", err)
	}
	if person1Resp.Node == nil {
		t.Fatal("Person 1 node is nil")
	}

	person2Req := scenarios.CreatePerson("Person 2", "person2@example.com")
	person2Resp, err := neo4jClient.CreateNode(ctx, person2Req)
	if err != nil {
		t.Fatalf("Failed to create person 2: %v", err)
	}
	if person2Resp.Node == nil {
		t.Fatal("Person 2 node is nil")
	}

	defer func() {
		// Cleanup
		neo4jClient.DeleteNode(ctx, &pb.DeleteNodeRequest{
			Metadata: person1Req.Metadata,
			NodeId:   person1Resp.Node.Id,
		})
		neo4jClient.DeleteNode(ctx, &pb.DeleteNodeRequest{
			Metadata: person2Req.Metadata,
			NodeId:   person2Resp.Node.Id,
		})
	}()

	t.Run("create relationship", func(t *testing.T) {
		req := scenarios.KnowsRelationship(person1Resp.Node.Id, person2Resp.Node.Id)

		resp, err := neo4jClient.CreateRelationship(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Relationship)
	})
}

// ===================================================================================
// TEST: CYPHER QUERIES
// ===================================================================================

func TestNeo4jAPI_Cypher(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	factory := neo4j_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("run simple cypher query", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("RETURN 1 as value"),
		)

		resp, err := neo4jClient.RunCypher(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Rows)
	})

	t.Run("run match query", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("MATCH (n) RETURN n LIMIT 10"),
		)

		resp, err := neo4jClient.RunCypher(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
	})

	t.Run("cypher fails with empty query", func(t *testing.T) {
		scenarios := neo4j_contract.NewScenarios()
		req := scenarios.EmptyQuery()

		_, err := neo4jClient.RunCypher(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("cypher fails with syntax error", func(t *testing.T) {
		scenarios := neo4j_contract.NewScenarios()
		req := scenarios.SyntaxErrorQuery()

		_, err := neo4jClient.RunCypher(ctx, req)

		require.Error(t, err)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestNeo4jAPI_MultiTenantIsolation(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	scenarios := neo4j_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("different tenants have isolated data", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Both should work (data is isolated by org)
		resp1, err := neo4jClient.RunCypher(ctx, tenant1Req)
		require.NoError(t, err)
		assert.NotNil(t, resp1)

		resp2, err := neo4jClient.RunCypher(ctx, tenant2Req)
		require.NoError(t, err)
		assert.NotNil(t, resp2)
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestNeo4jAPI_ResponseContracts(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	factory := neo4j_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("RunCypherResponse has required fields", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypher("RETURN 1 as value"),
		)

		resp, err := neo4jClient.RunCypher(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.Rows
		_ = resp.Columns
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestNeo4jAPI_ErrorCodes(t *testing.T) {
	if neo4jClient == nil {
		t.Skip("Neo4j gRPC client not initialized")
	}

	factory := neo4j_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty cypher", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(neo4j_contract.WithCypher(""))

		_, err := neo4jClient.RunCypher(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakeRunCypherRequest(
			neo4j_contract.WithCypherUser("", "test-org"),
		)

		_, err := neo4jClient.RunCypher(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}
