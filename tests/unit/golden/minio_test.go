//go:build unit

// Package golden provides unit tests for MinIO service contracts.
package golden

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	minio_contract "github.com/isa-cloud/isa_cloud/tests/contracts/minio"
)

// ===================================================================================
// TEST: DATA FACTORY - MinIO
// ===================================================================================

func TestMinIOTestDataFactory_MakeCreateBucketRequest(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.BucketName)
	})

	t.Run("accepts custom bucket name via option", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest(minio_contract.WithBucketName("my-bucket"))

		assert.Equal(t, "my-bucket", req.BucketName)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest(minio_contract.WithBucketUser("u1", "o1"))

		assert.Equal(t, "u1", req.UserId)
		assert.Equal(t, "o1", req.OrganizationId)
	})

	t.Run("accepts tags via option", func(t *testing.T) {
		tags := map[string]string{"env": "test", "team": "platform"}
		req := factory.MakeCreateBucketRequest(minio_contract.WithBucketTags(tags))

		assert.Equal(t, tags, req.Tags)
	})
}

func TestMinIOTestDataFactory_MakeGetObjectRequest(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeGetObjectRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.BucketName)
		assert.NotEmpty(t, req.ObjectKey)
	})

	t.Run("accepts custom object key via option", func(t *testing.T) {
		req := factory.MakeGetObjectRequest(minio_contract.WithGetObjectKey("path/to/file.txt"))

		assert.Equal(t, "path/to/file.txt", req.ObjectKey)
	})

	t.Run("accepts custom bucket via option", func(t *testing.T) {
		req := factory.MakeGetObjectRequest(minio_contract.WithGetObjectBucket("custom-bucket"))

		assert.Equal(t, "custom-bucket", req.BucketName)
	})
}

func TestMinIOTestDataFactory_MakeDeleteObjectRequest(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeDeleteObjectRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.BucketName)
		assert.NotEmpty(t, req.ObjectKey)
	})

	t.Run("accepts custom object key via option", func(t *testing.T) {
		req := factory.MakeDeleteObjectRequest(minio_contract.WithDeleteObjectKey("to-delete.txt"))

		assert.Equal(t, "to-delete.txt", req.ObjectKey)
	})
}

func TestMinIOTestDataFactory_MakeGetPresignedURLRequest(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeGetPresignedURLRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.BucketName)
		assert.NotEmpty(t, req.ObjectKey)
		assert.Greater(t, req.ExpirySeconds, int32(0))
	})

	t.Run("accepts custom expiry via option", func(t *testing.T) {
		req := factory.MakeGetPresignedURLRequest(minio_contract.WithPresignedExpiry(3600))

		assert.Equal(t, int32(3600), req.ExpirySeconds)
	})

	t.Run("accepts custom key via option", func(t *testing.T) {
		req := factory.MakeGetPresignedURLRequest(minio_contract.WithPresignedKey("upload/file.pdf"))

		assert.Equal(t, "upload/file.pdf", req.ObjectKey)
	})
}

func TestMinIOTestDataFactory_MakeListObjectsRequest(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeListObjectsRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.BucketName)
	})

	t.Run("accepts prefix filter via option", func(t *testing.T) {
		req := factory.MakeListObjectsRequest(minio_contract.WithListPrefix("uploads/"))

		assert.Equal(t, "uploads/", req.Prefix)
	})

	t.Run("accepts max keys via option", func(t *testing.T) {
		req := factory.MakeListObjectsRequest(minio_contract.WithMaxKeys(100))

		assert.Equal(t, int32(100), req.MaxKeys)
	})
}

// ===================================================================================
// TEST: SCENARIOS - MinIO
// ===================================================================================

func TestMinIOScenarios(t *testing.T) {
	scenarios := minio_contract.NewScenarios()

	t.Run("ValidBucketCreate returns usable request", func(t *testing.T) {
		req := scenarios.ValidBucketCreate()

		require.NotNil(t, req)
		assert.NotEmpty(t, req.BucketName)
	})

	t.Run("InvalidBucketName for edge case", func(t *testing.T) {
		req := scenarios.InvalidBucketName()

		assert.Len(t, req.BucketName, 2)
	})

	t.Run("PresignedUploadURL returns presigned request", func(t *testing.T) {
		req := scenarios.PresignedUploadURL("upload/test.pdf")

		assert.Equal(t, "upload/test.pdf", req.ObjectKey)
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.UserId, tenant2.UserId)
		assert.NotEqual(t, tenant1.OrganizationId, tenant2.OrganizationId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - MinIO
// ===================================================================================

func TestMinIOBusinessRules(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("BR-001: buckets are isolated by tenant", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest()

		isolatedBucket := minio_contract.ExpectedIsolatedBucket(req.OrganizationId, req.BucketName)

		assert.Contains(t, isolatedBucket, req.OrganizationId)
	})

	t.Run("BR-002: requests require user_id and organization_id", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
	})

	t.Run("BR-003: presigned URLs have expiry", func(t *testing.T) {
		req := factory.MakeGetPresignedURLRequest()

		assert.Greater(t, req.ExpirySeconds, int32(0))
	})
}

// ===================================================================================
// TEST: EDGE CASES - MinIO
// ===================================================================================

func TestMinIOEdgeCases(t *testing.T) {
	scenarios := minio_contract.NewScenarios()
	factory := minio_contract.NewTestDataFactory()

	t.Run("EC-001: invalid bucket name should be rejectable", func(t *testing.T) {
		req := scenarios.InvalidBucketName()

		assert.Less(t, len(req.BucketName), 3)
	})

	t.Run("EC-002: empty object key", func(t *testing.T) {
		req := factory.MakeGetObjectRequest(minio_contract.WithGetObjectKey(""))

		assert.Empty(t, req.ObjectKey)
	})

	t.Run("EC-004: zero expiry for presigned URL", func(t *testing.T) {
		req := factory.MakeGetPresignedURLRequest(minio_contract.WithPresignedExpiry(0))

		assert.Equal(t, int32(0), req.ExpirySeconds)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - MinIO
// ===================================================================================

func TestMinIOMultiTenantIsolation(t *testing.T) {
	scenarios := minio_contract.NewScenarios()

	t.Run("same logical bucket resolves to different physical buckets per tenant", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		physicalBucket1 := minio_contract.ExpectedIsolatedBucket(tenant1.OrganizationId, tenant1.BucketName)
		physicalBucket2 := minio_contract.ExpectedIsolatedBucket(tenant2.OrganizationId, tenant2.BucketName)

		assert.NotEqual(t, physicalBucket1, physicalBucket2)
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestMinIOAssertionHelpers(t *testing.T) {
	t.Run("ExpectedIsolatedBucket formats correctly", func(t *testing.T) {
		bucket := minio_contract.ExpectedIsolatedBucket("org-001", "my-bucket")

		assert.Contains(t, bucket, "org-001")
		assert.Contains(t, bucket, "my-bucket")
	})

	t.Run("DefaultIsolatedBucket uses test defaults", func(t *testing.T) {
		bucket := minio_contract.DefaultIsolatedBucket("test-bucket")

		assert.Contains(t, bucket, "test-org-001")
	})
}
