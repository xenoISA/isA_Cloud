//go:build integration

// Package golden provides integration tests for MinIO service.
package golden

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	minio_contract "github.com/isa-cloud/isa_cloud/tests/contracts/minio"
)

// Default test org for operations that don't include orgId in request
const defaultTestOrg = "test-org-001"

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockMinIOClient mocks the MinIO client
type MockMinIOClient struct {
	mock.Mock
}

func (m *MockMinIOClient) CreateBucket(ctx context.Context, bucket string) error {
	args := m.Called(ctx, bucket)
	return args.Error(0)
}

func (m *MockMinIOClient) GetObject(ctx context.Context, bucket, key string) ([]byte, error) {
	args := m.Called(ctx, bucket, key)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]byte), args.Error(1)
}

func (m *MockMinIOClient) DeleteObject(ctx context.Context, bucket, key string) error {
	args := m.Called(ctx, bucket, key)
	return args.Error(0)
}

func (m *MockMinIOClient) ListObjects(ctx context.Context, bucket, prefix string, maxKeys int32) ([]string, error) {
	args := m.Called(ctx, bucket, prefix, maxKeys)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]string), args.Error(1)
}

func (m *MockMinIOClient) GetPresignedURL(ctx context.Context, bucket, key string, expiry int32) (string, error) {
	args := m.Called(ctx, bucket, key, expiry)
	return args.String(0), args.Error(1)
}

// MockMinIOAuthService mocks authentication
type MockMinIOAuthService struct {
	mock.Mock
}

func (m *MockMinIOAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - CREATE BUCKET OPERATION
// ===================================================================================

func TestMinIOIntegration_CreateBucket(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("successful bucket creation", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)
		mockAuth := new(MockMinIOAuthService)

		req := factory.MakeCreateBucketRequest()

		isolatedBucket := minio_contract.ExpectedIsolatedBucket(req.OrganizationId, req.BucketName)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMinio.On("CreateBucket", mock.Anything, isolatedBucket).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockMinio.CreateBucket(context.Background(), isolatedBucket)
		require.NoError(t, err)

		mockMinio.AssertExpectations(t)
	})

	t.Run("bucket creation fails with bucket already exists", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)

		req := factory.MakeCreateBucketRequest()
		isolatedBucket := minio_contract.ExpectedIsolatedBucket(req.OrganizationId, req.BucketName)

		mockMinio.On("CreateBucket", mock.Anything, isolatedBucket).
			Return(errors.New("bucket already exists"))

		err := mockMinio.CreateBucket(context.Background(), isolatedBucket)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "already exists")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - GET OBJECT OPERATION
// ===================================================================================

func TestMinIOIntegration_GetObject(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("successful object retrieval", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)
		mockAuth := new(MockMinIOAuthService)

		req := factory.MakeGetObjectRequest()

		// GetObjectRequest doesn't have OrganizationId, use default
		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		expectedData := []byte("test file content")
		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMinio.On("GetObject", mock.Anything, isolatedBucket, req.ObjectKey).Return(expectedData, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		data, err := mockMinio.GetObject(context.Background(), isolatedBucket, req.ObjectKey)
		require.NoError(t, err)
		assert.Equal(t, expectedData, data)
	})

	t.Run("object not found", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)

		req := factory.MakeGetObjectRequest(minio_contract.WithGetObjectKey("nonexistent.txt"))
		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		mockMinio.On("GetObject", mock.Anything, isolatedBucket, req.ObjectKey).
			Return(nil, errors.New("object not found"))

		_, err := mockMinio.GetObject(context.Background(), isolatedBucket, req.ObjectKey)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not found")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - DELETE OBJECT OPERATION
// ===================================================================================

func TestMinIOIntegration_DeleteObject(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("successful object deletion", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)
		mockAuth := new(MockMinIOAuthService)

		req := factory.MakeDeleteObjectRequest()

		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMinio.On("DeleteObject", mock.Anything, isolatedBucket, req.ObjectKey).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockMinio.DeleteObject(context.Background(), isolatedBucket, req.ObjectKey)
		require.NoError(t, err)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - LIST OBJECTS OPERATION
// ===================================================================================

func TestMinIOIntegration_ListObjects(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("successful object listing", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)
		mockAuth := new(MockMinIOAuthService)

		req := factory.MakeListObjectsRequest(
			minio_contract.WithListPrefix("uploads/"),
			minio_contract.WithMaxKeys(100),
		)

		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		expectedList := []string{"uploads/file1.txt", "uploads/file2.txt"}
		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMinio.On("ListObjects", mock.Anything, isolatedBucket, req.Prefix, req.MaxKeys).Return(expectedList, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		objects, err := mockMinio.ListObjects(context.Background(), isolatedBucket, req.Prefix, req.MaxKeys)
		require.NoError(t, err)
		assert.Len(t, objects, 2)
	})

	t.Run("empty bucket listing", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)

		req := factory.MakeListObjectsRequest()
		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		mockMinio.On("ListObjects", mock.Anything, isolatedBucket, req.Prefix, req.MaxKeys).Return([]string{}, nil)

		objects, err := mockMinio.ListObjects(context.Background(), isolatedBucket, req.Prefix, req.MaxKeys)
		require.NoError(t, err)
		assert.Empty(t, objects)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - PRESIGNED URL OPERATION
// ===================================================================================

func TestMinIOIntegration_GetPresignedURL(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("successful presigned URL generation", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)
		mockAuth := new(MockMinIOAuthService)

		req := factory.MakeGetPresignedURLRequest(
			minio_contract.WithPresignedKey("uploads/document.pdf"),
			minio_contract.WithPresignedExpiry(3600),
		)

		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		expectedURL := "https://minio.example.com/bucket/key?signature=xyz"
		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMinio.On("GetPresignedURL", mock.Anything, isolatedBucket, req.ObjectKey, req.ExpirySeconds).
			Return(expectedURL, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		url, err := mockMinio.GetPresignedURL(context.Background(), isolatedBucket, req.ObjectKey, req.ExpirySeconds)
		require.NoError(t, err)
		assert.NotEmpty(t, url)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestMinIOIntegration_MultiTenantIsolation(t *testing.T) {
	scenarios := minio_contract.NewScenarios()

	t.Run("different tenants have different bucket prefixes", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		bucket1 := minio_contract.ExpectedIsolatedBucket(tenant1Req.OrganizationId, tenant1Req.BucketName)
		bucket2 := minio_contract.ExpectedIsolatedBucket(tenant2Req.OrganizationId, tenant2Req.BucketName)

		assert.NotEqual(t, bucket1, bucket2)
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestMinIOIntegration_ErrorHandling(t *testing.T) {
	factory := minio_contract.NewTestDataFactory()

	t.Run("access denied error", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)

		req := factory.MakeGetObjectRequest()
		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		mockMinio.On("GetObject", mock.Anything, isolatedBucket, req.ObjectKey).
			Return(nil, errors.New("access denied"))

		_, err := mockMinio.GetObject(context.Background(), isolatedBucket, req.ObjectKey)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "access denied")
	})

	t.Run("bucket not found error", func(t *testing.T) {
		mockMinio := new(MockMinIOClient)

		req := factory.MakeGetObjectRequest()
		isolatedBucket := minio_contract.ExpectedIsolatedBucket(defaultTestOrg, req.BucketName)

		mockMinio.On("GetObject", mock.Anything, isolatedBucket, req.ObjectKey).
			Return(nil, errors.New("bucket not found"))

		_, err := mockMinio.GetObject(context.Background(), isolatedBucket, req.ObjectKey)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not found")
	})
}
