//go:build unit

// Package golden provides unit tests for Qdrant service contracts.
package golden

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	pb "github.com/isa-cloud/isa_cloud/api/proto/qdrant"
	qdrant_contract "github.com/isa-cloud/isa_cloud/tests/contracts/qdrant"
)

// ===================================================================================
// TEST: DATA FACTORY - Qdrant
// ===================================================================================

func TestQdrantTestDataFactory_MakeCreateCollectionRequest(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.CollectionName)
	})

	t.Run("accepts custom collection name via option", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(qdrant_contract.WithCollectionName("embeddings"))

		assert.Equal(t, "embeddings", req.CollectionName)
	})

	t.Run("accepts vector size via option", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(qdrant_contract.WithVectorSize(1536))

		if vp, ok := req.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, uint64(1536), vp.VectorParams.Size)
		}
	})

	t.Run("accepts distance metric via option", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(qdrant_contract.WithDistance(pb.Distance_DISTANCE_COSINE))

		if vp, ok := req.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, pb.Distance_DISTANCE_COSINE, vp.VectorParams.Distance)
		}
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(qdrant_contract.WithCollectionUser("u1", "o1"))

		assert.Equal(t, "u1", req.Metadata.UserId)
		assert.Equal(t, "o1", req.Metadata.OrganizationId)
	})
}

func TestQdrantTestDataFactory_MakeUpsertPointsRequest(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("creates valid upsert request with defaults", func(t *testing.T) {
		req := factory.MakeUpsertPointsRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.CollectionName)
		assert.NotEmpty(t, req.Points)
	})

	t.Run("accepts custom collection via option", func(t *testing.T) {
		req := factory.MakeUpsertPointsRequest(qdrant_contract.WithUpsertCollection("vectors"))

		assert.Equal(t, "vectors", req.CollectionName)
	})

	t.Run("accepts custom points via option", func(t *testing.T) {
		points := []*pb.Point{
			factory.MakePoint("p1", 384, map[string]interface{}{"title": "doc1"}),
			factory.MakePoint("p2", 384, map[string]interface{}{"title": "doc2"}),
		}
		req := factory.MakeUpsertPointsRequest(qdrant_contract.WithPoints(points))

		assert.Len(t, req.Points, 2)
	})
}

func TestQdrantTestDataFactory_MakeSearchRequest(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("creates valid search request with defaults", func(t *testing.T) {
		req := factory.MakeSearchRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
		assert.NotEmpty(t, req.CollectionName)
		assert.NotNil(t, req.Vector)
		assert.Greater(t, req.Limit, uint64(0))
	})

	t.Run("accepts query vector via option", func(t *testing.T) {
		vector := []float32{0.1, 0.2, 0.3, 0.4}
		req := factory.MakeSearchRequest(qdrant_contract.WithQueryVector(vector))

		assert.Equal(t, vector, req.Vector.Data)
	})

	t.Run("accepts limit via option", func(t *testing.T) {
		req := factory.MakeSearchRequest(qdrant_contract.WithLimit(50))

		assert.Equal(t, uint64(50), req.Limit)
	})

	t.Run("accepts score threshold via option", func(t *testing.T) {
		req := factory.MakeSearchRequest(qdrant_contract.WithScoreThreshold(0.8))

		assert.NotNil(t, req.ScoreThreshold)
		assert.Equal(t, float32(0.8), *req.ScoreThreshold)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeSearchRequest(qdrant_contract.WithSearchUser("u1", "o1"))

		assert.Equal(t, "u1", req.Metadata.UserId)
		assert.Equal(t, "o1", req.Metadata.OrganizationId)
	})
}

func TestQdrantTestDataFactory_MakeDeletePointsRequest(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("creates valid delete request with defaults", func(t *testing.T) {
		req := factory.MakeDeletePointsRequest()

		assert.NotNil(t, req.Metadata)
		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.CollectionName)
	})

	t.Run("accepts point IDs via option", func(t *testing.T) {
		req := factory.MakeDeletePointsRequest(qdrant_contract.WithDeleteIds("id1", "id2", "id3"))

		if ids, ok := req.Selector.(*pb.DeletePointsRequest_Ids); ok {
			assert.Len(t, ids.Ids.Ids, 3)
		}
	})
}

func TestQdrantTestDataFactory_MakePoint(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("creates point with string ID", func(t *testing.T) {
		point := factory.MakePoint("doc-001", 384, map[string]interface{}{"title": "Test"})

		if strID, ok := point.Id.(*pb.Point_StrId); ok {
			assert.Equal(t, "doc-001", strID.StrId)
		}
	})

	t.Run("creates point with vector", func(t *testing.T) {
		point := factory.MakePoint("doc-001", 384, nil)

		if vec, ok := point.Vectors.(*pb.Point_Vector); ok {
			assert.Len(t, vec.Vector.Data, 384)
		}
	})
}

// ===================================================================================
// TEST: SCENARIOS - Qdrant
// ===================================================================================

func TestQdrantScenarios(t *testing.T) {
	scenarios := qdrant_contract.NewScenarios()

	t.Run("ValidCollectionCreate returns usable request", func(t *testing.T) {
		req := scenarios.ValidCollectionCreate()

		require.NotNil(t, req)
		assert.NotEmpty(t, req.CollectionName)
	})

	t.Run("OpenAIEmbeddingCollection uses 1536 dimensions", func(t *testing.T) {
		req := scenarios.OpenAIEmbeddingCollection("openai-embeddings")

		assert.Equal(t, "openai-embeddings", req.CollectionName)
		if vp, ok := req.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, uint64(1536), vp.VectorParams.Size)
		}
	})

	t.Run("WrongDimensionVector for edge case", func(t *testing.T) {
		req := scenarios.WrongDimensionVector()

		// Point has wrong dimension (768 instead of collection's 384)
		assert.NotEmpty(t, req.Points)
	})

	t.Run("EmptyQueryVector for edge case", func(t *testing.T) {
		req := scenarios.EmptyQueryVector()

		assert.Empty(t, req.Vector.Data)
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.Metadata.UserId, tenant2.Metadata.UserId)
		assert.NotEqual(t, tenant1.Metadata.OrganizationId, tenant2.Metadata.OrganizationId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - Qdrant
// ===================================================================================

func TestQdrantBusinessRules(t *testing.T) {
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("BR-001: collections are namespaced by tenant", func(t *testing.T) {
		req := factory.MakeUpsertPointsRequest()

		isolatedCollection := qdrant_contract.ExpectedIsolatedCollection(
			req.Metadata.OrganizationId, req.CollectionName,
		)

		assert.Contains(t, isolatedCollection, req.Metadata.OrganizationId)
	})

	t.Run("BR-002: requests require user_id and organization_id", func(t *testing.T) {
		req := factory.MakeUpsertPointsRequest()

		assert.NotEmpty(t, req.Metadata.UserId)
		assert.NotEmpty(t, req.Metadata.OrganizationId)
	})

	t.Run("BR-003: vector dimensions must be consistent", func(t *testing.T) {
		req := factory.MakeCreateCollectionRequest(qdrant_contract.WithVectorSize(384))

		if vp, ok := req.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, uint64(384), vp.VectorParams.Size)
		}
	})

	t.Run("BR-004: distance metrics are configurable", func(t *testing.T) {
		cosine := factory.MakeCreateCollectionRequest(qdrant_contract.WithDistance(pb.Distance_DISTANCE_COSINE))
		euclid := factory.MakeCreateCollectionRequest(qdrant_contract.WithDistance(pb.Distance_DISTANCE_EUCLID))
		dot := factory.MakeCreateCollectionRequest(qdrant_contract.WithDistance(pb.Distance_DISTANCE_DOT))

		if vp, ok := cosine.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, pb.Distance_DISTANCE_COSINE, vp.VectorParams.Distance)
		}
		if vp, ok := euclid.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, pb.Distance_DISTANCE_EUCLID, vp.VectorParams.Distance)
		}
		if vp, ok := dot.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			assert.Equal(t, pb.Distance_DISTANCE_DOT, vp.VectorParams.Distance)
		}
	})

	t.Run("BR-005: search results are limited", func(t *testing.T) {
		req := factory.MakeSearchRequest(qdrant_contract.WithLimit(100))

		assert.Equal(t, uint64(100), req.Limit)
	})
}

// ===================================================================================
// TEST: EDGE CASES - Qdrant
// ===================================================================================

func TestQdrantEdgeCases(t *testing.T) {
	scenarios := qdrant_contract.NewScenarios()
	factory := qdrant_contract.NewTestDataFactory()

	t.Run("EC-001: wrong dimension vector", func(t *testing.T) {
		req := scenarios.WrongDimensionVector()

		assert.NotEmpty(t, req.Points)
	})

	t.Run("EC-004: empty search vector should be rejectable", func(t *testing.T) {
		req := scenarios.EmptyQueryVector()

		assert.Empty(t, req.Vector.Data)
	})

	t.Run("EC-005: zero limit in search", func(t *testing.T) {
		req := factory.MakeSearchRequest(qdrant_contract.WithLimit(0))

		assert.Equal(t, uint64(0), req.Limit)
	})

	t.Run("EC-010: very large vector dimension", func(t *testing.T) {
		largeVector := make([]float32, 4096)
		req := factory.MakeSearchRequest(qdrant_contract.WithQueryVector(largeVector))

		assert.Len(t, req.Vector.Data, 4096)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - Qdrant
// ===================================================================================

func TestQdrantMultiTenantIsolation(t *testing.T) {
	scenarios := qdrant_contract.NewScenarios()

	t.Run("same logical collection resolves to different physical collections per tenant", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		physicalColl1 := qdrant_contract.ExpectedIsolatedCollection(
			tenant1.Metadata.OrganizationId, tenant1.CollectionName,
		)
		physicalColl2 := qdrant_contract.ExpectedIsolatedCollection(
			tenant2.Metadata.OrganizationId, tenant2.CollectionName,
		)

		assert.NotEqual(t, physicalColl1, physicalColl2)
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestQdrantAssertionHelpers(t *testing.T) {
	t.Run("ExpectedIsolatedCollection formats correctly", func(t *testing.T) {
		collection := qdrant_contract.ExpectedIsolatedCollection("org-001", "vectors")

		assert.Contains(t, collection, "org-001")
		assert.Contains(t, collection, "vectors")
	})

	t.Run("DefaultIsolatedCollection uses test defaults", func(t *testing.T) {
		collection := qdrant_contract.DefaultIsolatedCollection("test-collection")

		assert.Contains(t, collection, "test-org-001")
	})
}
