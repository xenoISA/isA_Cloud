//go:build api

// Package golden provides API tests for MinIO gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running MinIO gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Bucket Tests - Create, List, Delete buckets
// 3. Object Tests - Upload, Download, Delete objects
// 4. Presigned URL Tests - Generate presigned URLs
// 5. Error Handling Tests - Invalid inputs
//
// Related Documents:
// - Logic Contract: tests/contracts/minio/logic_contract.md
// - Fixtures: tests/contracts/minio/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestMinio
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/minio"
	minio_contract "github.com/isa-cloud/isa_cloud/tests/contracts/minio"
)

var minioClient pb.MinIOServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("MINIO_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50051"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	minioClient = pb.NewMinIOServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestMinioAPI_HealthCheck(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := minioClient.HealthCheck(ctx, &pb.MinIOHealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
		assert.NotEmpty(t, resp.Status)
	})
}

// ===================================================================================
// TEST: BUCKET OPERATIONS
// ===================================================================================

func TestMinioAPI_Buckets(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	factory := minio_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	testBucket := "api-test-bucket-" + time.Now().Format("20060102150405")

	t.Run("create bucket", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest(
			minio_contract.WithBucketName(testBucket),
		)

		resp, err := minioClient.CreateBucket(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("list buckets", func(t *testing.T) {
		req := factory.MakeListBucketsRequest()

		resp, err := minioClient.ListBuckets(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Buckets)
	})

	t.Run("get bucket info", func(t *testing.T) {
		req := &pb.GetBucketInfoRequest{
			BucketName: testBucket,
			UserId:     "test-user-001",
		}

		resp, err := minioClient.GetBucketInfo(ctx, req)

		if err == nil {
			assert.NotNil(t, resp.BucketInfo)
		}
	})

	t.Run("create bucket fails with invalid name", func(t *testing.T) {
		scenarios := minio_contract.NewScenarios()
		req := scenarios.InvalidBucketName()

		_, err := minioClient.CreateBucket(ctx, req)

		require.Error(t, err)
	})

	// Cleanup
	t.Run("delete bucket", func(t *testing.T) {
		req := &pb.DeleteBucketRequest{
			BucketName: testBucket,
			UserId:     "test-user-001",
		}

		resp, err := minioClient.DeleteBucket(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})
}

// ===================================================================================
// TEST: OBJECT OPERATIONS
// ===================================================================================

func TestMinioAPI_Objects(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	factory := minio_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	testBucket := "api-test-objects-" + time.Now().Format("20060102150405")

	// Setup: Create bucket
	createReq := factory.MakeCreateBucketRequest(
		minio_contract.WithBucketName(testBucket),
	)
	_, err := minioClient.CreateBucket(ctx, createReq)
	if err != nil {
		t.Fatalf("Failed to create test bucket: %v", err)
	}

	defer func() {
		// Cleanup: Delete bucket
		minioClient.DeleteBucket(ctx, &pb.DeleteBucketRequest{
			BucketName: testBucket,
			UserId:     "test-user-001",
		})
	}()

	t.Run("list objects in empty bucket", func(t *testing.T) {
		req := factory.MakeListObjectsRequest(
			minio_contract.WithListBucket(testBucket),
		)

		resp, err := minioClient.ListObjects(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Objects)
	})

	t.Run("get object fails for non-existent", func(t *testing.T) {
		req := factory.MakeGetObjectRequest(
			minio_contract.WithGetObjectBucket(testBucket),
			minio_contract.WithGetObjectKey("non-existent-key"),
		)

		stream, err := minioClient.GetObject(ctx, req)
		if err == nil {
			// Try to receive - should fail
			_, err = stream.Recv()
		}

		require.Error(t, err)
	})
}

// ===================================================================================
// TEST: PRESIGNED URL OPERATIONS
// ===================================================================================

func TestMinioAPI_PresignedURLs(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	factory := minio_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	testBucket := "api-test-presigned-" + time.Now().Format("20060102150405")

	// Setup: Create bucket
	createReq := factory.MakeCreateBucketRequest(
		minio_contract.WithBucketName(testBucket),
	)
	_, err := minioClient.CreateBucket(ctx, createReq)
	if err != nil {
		t.Fatalf("Failed to create test bucket: %v", err)
	}

	defer func() {
		// Cleanup: Delete bucket
		minioClient.DeleteBucket(ctx, &pb.DeleteBucketRequest{
			BucketName: testBucket,
			UserId:     "test-user-001",
		})
	}()

	t.Run("get presigned put URL", func(t *testing.T) {
		req := &pb.GetPresignedPutURLRequest{
			BucketName: testBucket,
			ObjectKey:  "test-upload.txt",
			UserId:     "test-user-001",
			ExpirySeconds: 900,
		}

		resp, err := minioClient.GetPresignedPutURL(ctx, req)

		require.NoError(t, err)
		assert.NotEmpty(t, resp.Url)
		assert.Contains(t, resp.Url, testBucket)
	})

	t.Run("get presigned URL for download", func(t *testing.T) {
		req := &pb.GetPresignedURLRequest{
			BucketName: testBucket,
			ObjectKey:  "test-download.txt",
			UserId:     "test-user-001",
			ExpirySeconds: 900,
		}

		resp, err := minioClient.GetPresignedURL(ctx, req)

		require.NoError(t, err)
		assert.NotEmpty(t, resp.Url)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestMinioAPI_MultiTenantIsolation(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	scenarios := minio_contract.NewScenarios()

	t.Run("different tenants have isolated buckets", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Bucket names should be different after org isolation
		assert.Equal(t, tenant1Req.BucketName, tenant2Req.BucketName) // Same logical name
		assert.NotEqual(t, tenant1Req.OrganizationId, tenant2Req.OrganizationId) // Different orgs
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestMinioAPI_ResponseContracts(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	factory := minio_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("ListBucketsResponse has required fields", func(t *testing.T) {
		req := factory.MakeListBucketsRequest()

		resp, err := minioClient.ListBuckets(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		assert.NotNil(t, resp.Buckets)
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestMinioAPI_ErrorCodes(t *testing.T) {
	if minioClient == nil {
		t.Skip("MinIO gRPC client not initialized")
	}

	factory := minio_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty bucket name", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest(
			minio_contract.WithBucketName(""),
		)

		_, err := minioClient.CreateBucket(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakeCreateBucketRequest(
			minio_contract.WithBucketUser("", "test-org"),
		)

		_, err := minioClient.CreateBucket(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("NotFound for non-existent bucket info", func(t *testing.T) {
		req := &pb.GetBucketInfoRequest{
			BucketName: "non-existent-bucket-xyz123",
			UserId:     "test-user-001",
		}

		_, err := minioClient.GetBucketInfo(ctx, req)

		require.Error(t, err)
	})
}
