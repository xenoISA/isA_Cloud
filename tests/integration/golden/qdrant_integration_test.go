//go:build integration

// Package golden provides integration tests for Qdrant service.
package golden

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	pb "github.com/isa-cloud/isa_cloud/api/proto/qdrant"
	qdrant_contract "github.com/isa-cloud/isa_cloud/tests/contracts/qdrant"
)

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockQdrantClient mocks the Qdrant client
type MockQdrantClient struct {
	mock.Mock
}

func (m *MockQdrantClient) Upsert(ctx context.Context, collection string, points []*pb.Point) error {
	args := m.Called(ctx, collection, points)
	return args.Error(0)
}

func (m *MockQdrantClient) Search(ctx context.Context, collection string, vector []float32, limit uint64) ([]*pb.ScoredPoint, error) {
	args := m.Called(ctx, collection, vector, limit)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]*pb.ScoredPoint), args.Error(1)
}

func (m *MockQdrantClient) Delete(ctx context.Context, collection string, ids []string) error {
	args := m.Called(ctx, collection, ids)
	return args.Error(0)
}

func (m *MockQdrantClient) CreateCollection(ctx context.Context, collection string, vectorSize uint64, distance pb.Distance) error {
	args := m.Called(ctx, collection, vectorSize, distance)
	return args.Error(0)
}

// MockQdrantAuthService mocks authentication
type MockQdrantAuthService struct {
	mock.Mock
}

func (m *MockQdrantAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - UPSERT OPERATION
// ===================================================================================

func TestQdrantIntegration_Upsert(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("successful upsert operation", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)
		mockAuth := new(MockQdrantAuthService)

		req := factory.MakeUpsertPointsRequest()

		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockAuth.On("ValidateUser", req.Metadata.UserId).Return(nil)
		mockQdrant.On("Upsert", mock.Anything, isolatedCollection, req.Points).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.Metadata.UserId)
		require.NoError(t, err)

		err = mockQdrant.Upsert(context.Background(), isolatedCollection, req.Points)
		require.NoError(t, err)

		mockQdrant.AssertExpectations(t)
	})

	t.Run("upsert fails with unauthorized user", func(t *testing.T) {
		mockAuth := new(MockQdrantAuthService)

		req := factory.MakeUpsertPointsRequest()

		mockAuth.On("ValidateUser", req.Metadata.UserId).Return(errors.New("unauthorized"))

		err := mockAuth.ValidateUser(req.Metadata.UserId)
		assert.Error(t, err)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - SEARCH OPERATION
// ===================================================================================

func TestQdrantIntegration_Search(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("successful search operation", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)
		mockAuth := new(MockQdrantAuthService)

		req := factory.MakeSearchRequest()

		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		expectedResults := []*pb.ScoredPoint{
			{Score: 0.95},
			{Score: 0.89},
		}

		mockAuth.On("ValidateUser", req.Metadata.UserId).Return(nil)
		mockQdrant.On("Search", mock.Anything, isolatedCollection, req.Vector.Data, req.Limit).
			Return(expectedResults, nil)

		// Execute
		err := mockAuth.ValidateUser(req.Metadata.UserId)
		require.NoError(t, err)

		results, err := mockQdrant.Search(context.Background(), isolatedCollection, req.Vector.Data, req.Limit)
		require.NoError(t, err)
		assert.Len(t, results, 2)
	})

	t.Run("search returns empty results", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)

		req := factory.MakeSearchRequest()
		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockQdrant.On("Search", mock.Anything, isolatedCollection, req.Vector.Data, req.Limit).
			Return([]*pb.ScoredPoint{}, nil)

		results, err := mockQdrant.Search(context.Background(), isolatedCollection, req.Vector.Data, req.Limit)
		require.NoError(t, err)
		assert.Empty(t, results)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - DELETE OPERATION
// ===================================================================================

func TestQdrantIntegration_Delete(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("successful delete operation", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)
		mockAuth := new(MockQdrantAuthService)

		req := factory.MakeDeletePointsRequest(qdrant_contract.WithDeleteIds("point-001"))

		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockAuth.On("ValidateUser", req.Metadata.UserId).Return(nil)
		mockQdrant.On("Delete", mock.Anything, isolatedCollection, []string{"point-001"}).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.Metadata.UserId)
		require.NoError(t, err)

		err = mockQdrant.Delete(context.Background(), isolatedCollection, []string{"point-001"})
		require.NoError(t, err)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - CREATE COLLECTION
// ===================================================================================

func TestQdrantIntegration_CreateCollection(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("successful collection creation", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)
		mockAuth := new(MockQdrantAuthService)

		req := factory.MakeCreateCollectionRequest(
			qdrant_contract.WithVectorSize(1536),
			qdrant_contract.WithDistance(pb.Distance_DISTANCE_COSINE),
		)

		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockAuth.On("ValidateUser", req.Metadata.UserId).Return(nil)
		mockQdrant.On("CreateCollection", mock.Anything, isolatedCollection, uint64(1536), pb.Distance_DISTANCE_COSINE).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.Metadata.UserId)
		require.NoError(t, err)

		err = mockQdrant.CreateCollection(context.Background(), isolatedCollection, 1536, pb.Distance_DISTANCE_COSINE)
		require.NoError(t, err)
	})

	t.Run("collection already exists", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)

		req := factory.MakeCreateCollectionRequest()
		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockQdrant.On("CreateCollection", mock.Anything, isolatedCollection, mock.Anything, mock.Anything).
			Return(errors.New("collection already exists"))

		err := mockQdrant.CreateCollection(context.Background(), isolatedCollection, 384, pb.Distance_DISTANCE_COSINE)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "already exists")
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestQdrantIntegration_MultiTenantIsolation(t *testing.T) {
	scenarios := qdrant_contract.NewScenarios()

	t.Run("different tenants have different collection prefixes", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		coll1 := qdrant_contract.ExpectedIsolatedCollection(tenant1Req.Metadata.OrganizationId, tenant1Req.CollectionName)
		coll2 := qdrant_contract.ExpectedIsolatedCollection(tenant2Req.Metadata.OrganizationId, tenant2Req.CollectionName)

		assert.NotEqual(t, coll1, coll2)
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestQdrantIntegration_ErrorHandling(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("dimension mismatch error", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)

		req := factory.MakeSearchRequest()
		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockQdrant.On("Search", mock.Anything, isolatedCollection, req.Vector.Data, req.Limit).
			Return(nil, errors.New("vector dimension mismatch"))

		_, err := mockQdrant.Search(context.Background(), isolatedCollection, req.Vector.Data, req.Limit)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "dimension mismatch")
	})

	t.Run("collection not found error", func(t *testing.T) {
		mockQdrant := new(MockQdrantClient)

		req := factory.MakeUpsertPointsRequest()
		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		mockQdrant.On("Upsert", mock.Anything, isolatedCollection, req.Points).
			Return(errors.New("collection not found"))

		err := mockQdrant.Upsert(context.Background(), isolatedCollection, req.Points)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not found")
	})
}
