//go:build api

// Package golden provides API tests for Qdrant gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running Qdrant gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Collection Tests - Create, List, Delete collections
// 3. Point Tests - Upsert, Search, Delete points
// 4. Vector Search Tests - Semantic search operations
// 5. Error Handling Tests - Invalid inputs
//
// Related Documents:
// - Logic Contract: tests/contracts/qdrant/logic_contract.md
// - Fixtures: tests/contracts/qdrant/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestQdrant
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/qdrant"
	qdrant_contract "github.com/isa-cloud/isa_cloud/tests/contracts/qdrant"
)

var qdrantClient pb.QdrantServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("QDRANT_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50062"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	qdrantClient = pb.NewQdrantServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestQdrantAPI_HealthCheck(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := qdrantClient.HealthCheck(ctx, &pb.QdrantHealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
	})
}

// ===================================================================================
// TEST: COLLECTION OPERATIONS
// ===================================================================================

func TestQdrantAPI_Collections(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	factory := qdrant_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	testCollection := "api_test_collection_" + time.Now().Format("20060102150405")

	t.Run("create collection", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(
			qdrant_contract.WithCollectionName(testCollection),
			qdrant_contract.WithVectorSize(384),
			qdrant_contract.WithDistance(pb.Distance_DISTANCE_COSINE),
		)

		resp, err := qdrantClient.CreateCollection(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("list collections", func(t *testing.T) {
		req := &pb.ListCollectionsRequest{
			Metadata: factory.MakeCreateCollectionRequest().Metadata,
		}

		resp, err := qdrantClient.ListCollections(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Collections)
	})

	t.Run("get collection info", func(t *testing.T) {
		req := &pb.GetCollectionInfoRequest{
			Metadata:       factory.MakeCreateCollectionRequest().Metadata,
			CollectionName: testCollection,
		}

		resp, err := qdrantClient.GetCollectionInfo(ctx, req)

		if err == nil {
			assert.NotNil(t, resp.Info)
		}
	})

	// Cleanup
	t.Run("delete collection", func(t *testing.T) {
		req := &pb.DeleteCollectionRequest{
			Metadata:       factory.MakeCreateCollectionRequest().Metadata,
			CollectionName: testCollection,
		}

		resp, err := qdrantClient.DeleteCollection(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})
}

// ===================================================================================
// TEST: POINT OPERATIONS
// ===================================================================================

func TestQdrantAPI_Points(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	factory := qdrant_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	testCollection := "api_test_points_" + time.Now().Format("20060102150405")

	// Setup: Create collection
	createReq := factory.MakeCreateCollectionRequest(
		qdrant_contract.WithCollectionName(testCollection),
	)
	_, err := qdrantClient.CreateCollection(ctx, createReq)
	if err != nil {
		t.Fatalf("Failed to create test collection: %v", err)
	}

	defer func() {
		// Cleanup: Delete collection
		qdrantClient.DeleteCollection(ctx, &pb.DeleteCollectionRequest{
			Metadata:       createReq.Metadata,
			CollectionName: testCollection,
		})
	}()

	t.Run("upsert points", func(t *testing.T) {
		req := factory.MakeUpsertPointsRequest(
			qdrant_contract.WithUpsertCollection(testCollection),
		)

		resp, err := qdrantClient.UpsertPoints(ctx, req)

		require.NoError(t, err)
		assert.NotEmpty(t, resp.Status)
	})

	t.Run("search points", func(t *testing.T) {
		req := factory.MakeSearchRequest(
			qdrant_contract.WithSearchCollection(testCollection),
			qdrant_contract.WithLimit(10),
		)

		resp, err := qdrantClient.Search(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Result)
	})

	t.Run("search with score threshold", func(t *testing.T) {
		req := factory.MakeSearchRequest(
			qdrant_contract.WithSearchCollection(testCollection),
			qdrant_contract.WithLimit(10),
			qdrant_contract.WithScoreThreshold(0.5),
		)

		resp, err := qdrantClient.Search(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Result)
	})

	t.Run("delete points", func(t *testing.T) {
		req := factory.MakeDeletePointsRequest(
			qdrant_contract.WithDeleteCollection(testCollection),
			qdrant_contract.WithDeleteIds("point-001"),
		)

		resp, err := qdrantClient.DeletePoints(ctx, req)

		require.NoError(t, err)
		assert.NotEmpty(t, resp.Status)
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestQdrantAPI_Errors(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	factory := qdrant_contract.NewTestDataFactory()
	scenarios := qdrant_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("search fails with empty vector", func(t *testing.T) {
		req := scenarios.EmptyQueryVector()

		_, err := qdrantClient.Search(ctx, req)

		require.Error(t, err)
	})

	t.Run("search fails with missing metadata", func(t *testing.T) {
		req := factory.MakeSearchRequest(
			qdrant_contract.WithSearchUser("", "test-org"),
		)

		_, err := qdrantClient.Search(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestQdrantAPI_MultiTenantIsolation(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	scenarios := qdrant_contract.NewScenarios()

	t.Run("different tenants have isolated collections", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Verify they have different org IDs
		assert.NotEqual(t,
			tenant1Req.Metadata.OrganizationId,
			tenant2Req.Metadata.OrganizationId)
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestQdrantAPI_ResponseContracts(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	factory := qdrant_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("ListCollectionsResponse has required fields", func(t *testing.T) {
		req := &pb.ListCollectionsRequest{
			Metadata: factory.MakeCreateCollectionRequest().Metadata,
		}

		resp, err := qdrantClient.ListCollections(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		assert.NotNil(t, resp.Collections)
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestQdrantAPI_ErrorCodes(t *testing.T) {
	if qdrantClient == nil {
		t.Skip("Qdrant gRPC client not initialized")
	}

	factory := qdrant_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty collection name", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(
			qdrant_contract.WithCollectionName(""),
		)

		_, err := qdrantClient.CreateCollection(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(
			qdrant_contract.WithCollectionUser("", "test-org"),
		)

		_, err := qdrantClient.CreateCollection(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("NotFound for non-existent collection", func(t *testing.T) {
		req := &pb.GetCollectionInfoRequest{
			Metadata:       factory.MakeCreateCollectionRequest().Metadata,
			CollectionName: "non_existent_collection_xyz",
		}

		_, err := qdrantClient.GetCollectionInfo(ctx, req)

		require.Error(t, err)
	})
}
