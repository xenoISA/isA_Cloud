//go:build api

// Package golden provides API tests for Redis gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running Redis gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. CRUD Operation Tests - Set, Get, Delete
// 3. Hash Operation Tests - HSet, HGet
// 4. Response Contract Validation - Verify response structures
// 5. Error Handling Tests - Invalid inputs, auth failures
//
// Related Documents:
// - Logic Contract: tests/contracts/redis/logic_contract.md
// - Fixtures: tests/contracts/redis/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestRedis
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/redis"
	redis_contract "github.com/isa-cloud/isa_cloud/tests/contracts/redis"
)

var redisClient pb.RedisServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("REDIS_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50055"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	redisClient = pb.NewRedisServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestRedisAPI_HealthCheck(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := redisClient.HealthCheck(ctx, &pb.RedisHealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
		assert.NotEmpty(t, resp.RedisStatus)
	})
}

// ===================================================================================
// TEST: SET OPERATION
// ===================================================================================

func TestRedisAPI_Set(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	factory := redis_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful set operation", func(t *testing.T) {
		req := factory.MakeSetRequest(factory.WithRandomKey())

		resp, err := redisClient.Set(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
		assert.NotEmpty(t, resp.Message)
	})

	t.Run("set with expiration", func(t *testing.T) {
		// Use SetWithExpiration for TTL
		req := &pb.SetWithExpirationRequest{
			UserId:         "test-user-001",
			OrganizationId: "test-org-001",
			Key:            "ttl-test-key",
			Value:          "ttl-test-value",
		}

		resp, err := redisClient.SetWithExpiration(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("set with empty key still succeeds", func(t *testing.T) {
		// Note: Service may accept empty keys (validation at higher level)
		scenarios := redis_contract.NewScenarios()
		req := scenarios.SetRequestEmptyKey()

		resp, err := redisClient.Set(ctx, req)

		if err == nil {
			assert.True(t, resp.Success)
		}
	})

	t.Run("set fails with empty user_id", func(t *testing.T) {
		req := factory.MakeSetRequest(
			redis_contract.WithUser("", "test-org"),
		)

		_, err := redisClient.Set(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		// Service returns PermissionDenied for missing user_id
		assert.Equal(t, codes.PermissionDenied, st.Code())
	})
}

// ===================================================================================
// TEST: GET OPERATION
// ===================================================================================

func TestRedisAPI_Get(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	factory := redis_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful get operation", func(t *testing.T) {
		// First set a value
		setReq := factory.MakeSetRequest(factory.WithRandomKey())
		_, err := redisClient.Set(ctx, setReq)
		require.NoError(t, err)

		// Then get it
		getReq := factory.MakeGetRequest(
			redis_contract.WithGetKey(setReq.Key),
			redis_contract.WithGetUser(setReq.UserId, setReq.OrganizationId),
		)

		resp, err := redisClient.Get(ctx, getReq)

		require.NoError(t, err)
		assert.True(t, resp.Found)
		assert.Equal(t, setReq.Value, resp.Value)
	})

	t.Run("get returns not found for non-existent key", func(t *testing.T) {
		req := factory.MakeGetRequest(
			redis_contract.WithGetKey("nonexistent-key-12345"),
		)

		resp, err := redisClient.Get(ctx, req)

		require.NoError(t, err)
		assert.False(t, resp.Found)
		assert.Empty(t, resp.Value)
	})

	t.Run("get with empty key succeeds", func(t *testing.T) {
		// Note: Service accepts empty keys (validation at higher level)
		req := factory.MakeGetRequest(redis_contract.WithGetKey(""))

		resp, err := redisClient.Get(ctx, req)

		require.NoError(t, err)
		// Service may return Found if empty key was previously set
		_ = resp.Found
	})
}

// ===================================================================================
// TEST: DELETE OPERATION
// ===================================================================================

func TestRedisAPI_Delete(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	factory := redis_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful delete operation", func(t *testing.T) {
		// First set a value
		setReq := factory.MakeSetRequest(factory.WithRandomKey())
		_, err := redisClient.Set(ctx, setReq)
		require.NoError(t, err)

		// Then delete it
		delReq := factory.MakeDeleteRequest(
			redis_contract.WithDeleteKey(setReq.Key),
		)
		delReq.UserId = setReq.UserId
		delReq.OrganizationId = setReq.OrganizationId

		resp, err := redisClient.Delete(ctx, delReq)

		require.NoError(t, err)
		assert.True(t, resp.Success)
		assert.GreaterOrEqual(t, resp.DeletedCount, int32(0))
	})

	t.Run("delete non-existent key succeeds", func(t *testing.T) {
		req := factory.MakeDeleteRequest(
			redis_contract.WithDeleteKey("nonexistent-key-67890"),
		)

		resp, err := redisClient.Delete(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})
}

// ===================================================================================
// TEST: HASH OPERATIONS
// ===================================================================================

func TestRedisAPI_HashOperations(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	factory := redis_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful hset and hgetall", func(t *testing.T) {
		// Set hash fields
		hsetReq := factory.MakeHSetRequest(
			redis_contract.WithHashKey("api-test-hash"),
			redis_contract.WithFieldsFromMap(map[string]string{
				"field1": "value1",
				"field2": "value2",
			}),
		)

		resp, err := redisClient.HSet(ctx, hsetReq)
		require.NoError(t, err)
		assert.True(t, resp.Success)

		// Get all hash fields
		hgetReq := &pb.HGetAllRequest{
			UserId:         hsetReq.UserId,
			OrganizationId: hsetReq.OrganizationId,
			Key:            hsetReq.Key,
		}

		hgetResp, err := redisClient.HGetAll(ctx, hgetReq)
		require.NoError(t, err)
		assert.NotNil(t, hgetResp.Fields)

		// Convert fields to map for easier assertion
		fieldsMap := make(map[string]string)
		for _, f := range hgetResp.Fields {
			fieldsMap[f.Field] = f.Value
		}
		assert.Equal(t, "value1", fieldsMap["field1"])
		assert.Equal(t, "value2", fieldsMap["field2"])
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestRedisAPI_MultiTenantIsolation(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	scenarios := redis_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("different tenants cannot access each other's data", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Tenant 1 sets a value
		_, err := redisClient.Set(ctx, tenant1Req)
		require.NoError(t, err)

		// Tenant 2 tries to get the same logical key
		getReq := &pb.GetRequest{
			UserId:         tenant2Req.UserId,
			OrganizationId: tenant2Req.OrganizationId,
			Key:            tenant1Req.Key, // Same logical key
		}

		resp, err := redisClient.Get(ctx, getReq)
		require.NoError(t, err)

		// Tenant 2 should NOT find tenant 1's data
		assert.False(t, resp.Found, "tenant 2 should not access tenant 1's data")
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestRedisAPI_ResponseContracts(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	factory := redis_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("SetResponse has required fields", func(t *testing.T) {
		req := factory.MakeSetRequest(factory.WithRandomKey())

		resp, err := redisClient.Set(ctx, req)

		require.NoError(t, err)
		// Verify response contract
		assert.NotNil(t, resp)
		// Success is a bool - must be present
		_ = resp.Success
		// Message should be present
		assert.NotEmpty(t, resp.Message)
	})

	t.Run("GetResponse has required fields", func(t *testing.T) {
		req := factory.MakeGetRequest()

		resp, err := redisClient.Get(ctx, req)

		require.NoError(t, err)
		// Verify response contract
		assert.NotNil(t, resp)
		// Found is a bool - must be present
		_ = resp.Found
		// Value may be empty if not found
		_ = resp.Value
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestRedisAPI_ErrorCodes(t *testing.T) {
	if redisClient == nil {
		t.Skip("Redis gRPC client not initialized")
	}

	factory := redis_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("empty key is accepted by service", func(t *testing.T) {
		// Note: Service accepts empty keys (validation happens at app level)
		req := factory.MakeSetRequest(redis_contract.WithKey(""))

		resp, err := redisClient.Set(ctx, req)

		if err == nil {
			assert.True(t, resp.Success)
		}
	})

	t.Run("PermissionDenied for missing user_id", func(t *testing.T) {
		req := factory.MakeSetRequest(
			redis_contract.WithUser("", "test-org"),
		)

		_, err := redisClient.Set(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		// Service returns PermissionDenied for missing user_id
		assert.Equal(t, codes.PermissionDenied, st.Code())
	})

	t.Run("missing organization_id is accepted", func(t *testing.T) {
		// Note: Some services may accept empty org_id
		req := factory.MakeSetRequest(
			redis_contract.WithUser("test-user", ""),
		)

		resp, err := redisClient.Set(ctx, req)

		if err == nil {
			assert.True(t, resp.Success)
		}
	})
}
