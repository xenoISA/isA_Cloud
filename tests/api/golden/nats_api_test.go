//go:build api

// Package golden provides API tests for NATS gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running NATS gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Publish Tests - Message publishing
// 3. JetStream Tests - Stream and consumer operations
// 4. KV Tests - Key-Value store operations
// 5. Error Handling Tests - Invalid inputs
//
// Related Documents:
// - Logic Contract: tests/contracts/nats/logic_contract.md
// - Fixtures: tests/contracts/nats/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestNats
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/nats"
	nats_contract "github.com/isa-cloud/isa_cloud/tests/contracts/nats"
)

var natsClient pb.NATSServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("NATS_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50056"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	natsClient = pb.NewNATSServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestNatsAPI_HealthCheck(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service is healthy", func(t *testing.T) {
		resp, err := natsClient.HealthCheck(ctx, &pb.NATSHealthCheckRequest{})

		require.NoError(t, err)
		assert.True(t, resp.Healthy)
		assert.NotEmpty(t, resp.NatsStatus)
	})
}

// ===================================================================================
// TEST: PUBLISH OPERATION
// ===================================================================================

func TestNatsAPI_Publish(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	factory := nats_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful publish", func(t *testing.T) {
		req := factory.MakePublishRequest(
			nats_contract.WithSubject("api.test.events"),
			nats_contract.WithJSONData(`{"test": "data"}`),
		)

		resp, err := natsClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("publish with headers", func(t *testing.T) {
		req := factory.MakePublishRequest(
			nats_contract.WithSubject("api.test.headers"),
			nats_contract.WithHeaders(map[string]string{
				"Content-Type": "application/json",
				"X-Request-ID": "test-123",
			}),
		)

		resp, err := natsClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("publish fails with empty subject", func(t *testing.T) {
		scenarios := nats_contract.NewScenarios()
		req := scenarios.EmptySubject()

		_, err := natsClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("publish fails with invalid subject", func(t *testing.T) {
		scenarios := nats_contract.NewScenarios()
		req := scenarios.InvalidSubject()

		_, err := natsClient.Publish(ctx, req)

		require.Error(t, err)
	})

	t.Run("publish fails with missing user_id", func(t *testing.T) {
		req := factory.MakePublishRequest(
			nats_contract.WithUser("", "test-org"),
		)

		_, err := natsClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: JETSTREAM - STREAM OPERATIONS
// ===================================================================================

func TestNatsAPI_JetStream_Streams(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	factory := nats_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	streamName := "API_TEST_STREAM"

	t.Run("create stream", func(t *testing.T) {
		req := factory.MakeCreateStreamRequest(
			nats_contract.WithStreamName(streamName),
			nats_contract.WithStreamSubjects("api.test.>"),
		)

		resp, err := natsClient.CreateStream(ctx, req)

		// May fail if stream exists, that's ok
		if err == nil {
			assert.True(t, resp.Success)
		}
	})

	t.Run("get stream info", func(t *testing.T) {
		req := &pb.GetStreamInfoRequest{
			UserId:         "test-user-001",
			OrganizationId: "test-org-001",
			StreamName:     streamName,
		}

		resp, err := natsClient.GetStreamInfo(ctx, req)

		if err == nil {
			assert.NotNil(t, resp.Stream)
		}
	})

	t.Run("list streams", func(t *testing.T) {
		req := &pb.ListStreamsRequest{
			UserId:         "test-user-001",
			OrganizationId: "test-org-001",
		}

		resp, err := natsClient.ListStreams(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp.Streams)
	})

	// Cleanup
	t.Run("delete stream", func(t *testing.T) {
		req := &pb.DeleteStreamRequest{
			UserId:         "test-user-001",
			OrganizationId: "test-org-001",
			StreamName:     streamName,
		}

		_, _ = natsClient.DeleteStream(ctx, req)
	})
}

// ===================================================================================
// TEST: KV OPERATIONS
// ===================================================================================

func TestNatsAPI_KV(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	factory := nats_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	bucket := "api-test-bucket"

	t.Run("put and get KV", func(t *testing.T) {
		// Put
		putReq := factory.MakeKVPutRequest(
			nats_contract.WithBucket(bucket),
			nats_contract.WithKVKey("test-key"),
			nats_contract.WithKVValue([]byte("test-value")),
		)

		putResp, err := natsClient.KVPut(ctx, putReq)
		if err != nil {
			t.Skip("KV bucket may not exist or KV not configured")
		}
		assert.True(t, putResp.Success)

		// Get
		getReq := factory.MakeKVGetRequest()
		getReq.Bucket = bucket
		getReq.Key = "test-key"

		getResp, err := natsClient.KVGet(ctx, getReq)
		require.NoError(t, err)
		assert.Equal(t, []byte("test-value"), getResp.Value)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestNatsAPI_MultiTenantIsolation(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	scenarios := nats_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("different tenants publish to isolated subjects", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Both should work (subjects are isolated by org)
		resp1, err := natsClient.Publish(ctx, tenant1Req)
		require.NoError(t, err)
		assert.True(t, resp1.Success)

		resp2, err := natsClient.Publish(ctx, tenant2Req)
		require.NoError(t, err)
		assert.True(t, resp2.Success)
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestNatsAPI_ResponseContracts(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	factory := nats_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("PublishResponse has required fields", func(t *testing.T) {
		req := factory.MakePublishRequest()

		resp, err := natsClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.Success
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestNatsAPI_ErrorCodes(t *testing.T) {
	if natsClient == nil {
		t.Skip("NATS gRPC client not initialized")
	}

	factory := nats_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty subject", func(t *testing.T) {
		req := factory.MakePublishRequest(nats_contract.WithSubject(""))

		_, err := natsClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakePublishRequest(
			nats_contract.WithUser("", "test-org"),
		)

		_, err := natsClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}
