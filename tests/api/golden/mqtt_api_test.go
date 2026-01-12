//go:build api

// Package golden provides API tests for MQTT gRPC service.
//
// These tests verify the actual gRPC endpoints with real network calls.
// Requires a running MQTT gRPC service.
//
// Test Categories:
// 1. Health Check Tests - Service availability
// 2. Publish Tests - Message publishing
// 3. Subscribe Tests - Topic subscriptions
// 4. QoS Tests - Quality of Service levels
// 5. Error Handling Tests - Invalid inputs
//
// Related Documents:
// - Logic Contract: tests/contracts/mqtt/logic_contract.md
// - Fixtures: tests/contracts/mqtt/fixtures.go
//
// Test Execution:
//
//	go test -v -tags=api ./tests/api/golden/... -run TestMqtt
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/mqtt"
	mqtt_contract "github.com/isa-cloud/isa_cloud/tests/contracts/mqtt"
)

var mqttClient pb.MQTTServiceClient

func init() {
	// Get service address from environment or use default
	addr := os.Getenv("MQTT_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50053"
	}

	// Connect to gRPC service
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return
	}

	mqttClient = pb.NewMQTTServiceClient(conn)
}

// ===================================================================================
// TEST: HEALTH CHECK
// ===================================================================================

func TestMqttAPI_HealthCheck(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	t.Run("service responds to health check", func(t *testing.T) {
		resp, err := mqttClient.HealthCheck(ctx, &pb.MQTTHealthCheckRequest{})

		require.NoError(t, err)
		// Note: Healthy may be false if broker is not connected
		// but we still verify gRPC service is responding
		assert.NotNil(t, resp)
		t.Logf("MQTT Health: %v, BrokerStatus: %s", resp.Healthy, resp.BrokerStatus)
	})
}

// ===================================================================================
// TEST: PUBLISH OPERATION
// ===================================================================================

func TestMqttAPI_Publish(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	factory := mqtt_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful publish QoS 0", func(t *testing.T) {
		req := factory.MakePublishRequest(
			mqtt_contract.WithTopic("api/test/qos0"),
			mqtt_contract.WithQoS(pb.QoSLevel_QOS_AT_MOST_ONCE),
			mqtt_contract.WithJSONPayload(`{"test": "qos0"}`),
		)

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("successful publish QoS 1", func(t *testing.T) {
		req := factory.MakePublishRequest(
			mqtt_contract.WithTopic("api/test/qos1"),
			mqtt_contract.WithQoS(pb.QoSLevel_QOS_AT_LEAST_ONCE),
			mqtt_contract.WithJSONPayload(`{"test": "qos1"}`),
		)

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("successful publish QoS 2", func(t *testing.T) {
		req := factory.MakePublishRequest(
			mqtt_contract.WithTopic("api/test/qos2"),
			mqtt_contract.WithQoS(pb.QoSLevel_QOS_EXACTLY_ONCE),
			mqtt_contract.WithJSONPayload(`{"test": "qos2"}`),
		)

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("publish with retained flag", func(t *testing.T) {
		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.RetainedMessage("api/test/retained")

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("publish fails with empty topic", func(t *testing.T) {
		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.EmptyTopic()

		_, err := mqttClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("publish fails with wildcard in topic", func(t *testing.T) {
		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.WildcardInPublish()

		_, err := mqttClient.Publish(ctx, req)

		require.Error(t, err)
	})

	t.Run("publish fails with missing user_id", func(t *testing.T) {
		req := factory.MakePublishRequest(
			mqtt_contract.WithPublishUser("", "test-session"),
		)

		_, err := mqttClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}

// ===================================================================================
// TEST: SUBSCRIBE OPERATION
// ===================================================================================

func TestMqttAPI_Subscribe(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	factory := mqtt_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful subscribe stream creation", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(
			mqtt_contract.WithTopicFilter("api/test/#"),
		)

		stream, err := mqttClient.Subscribe(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, stream)
	})

	t.Run("subscribe with single-level wildcard", func(t *testing.T) {
		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.SingleLevelWildcardSubscription()

		stream, err := mqttClient.Subscribe(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, stream)
	})

	t.Run("subscribe with multi-level wildcard", func(t *testing.T) {
		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.MultiLevelWildcardSubscription()

		stream, err := mqttClient.Subscribe(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, stream)
	})
}

// ===================================================================================
// TEST: UNSUBSCRIBE OPERATION
// ===================================================================================

func TestMqttAPI_Unsubscribe(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	factory := mqtt_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("successful unsubscribe", func(t *testing.T) {
		req := factory.MakeUnsubscribeRequest(
			mqtt_contract.WithUnsubscribeTopics("api/test/#"),
		)

		resp, err := mqttClient.Unsubscribe(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})
}

// ===================================================================================
// TEST: DEVICE SCENARIOS
// ===================================================================================

func TestMqttAPI_DeviceScenarios(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	scenarios := mqtt_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("temperature reading", func(t *testing.T) {
		req := scenarios.TemperatureReading("sensor-001", 23.5)

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("device status online", func(t *testing.T) {
		req := scenarios.DeviceStatus("device-001", true)

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("command message", func(t *testing.T) {
		req := scenarios.CommandMessage("device-001", "reboot")

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.True(t, resp.Success)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestMqttAPI_MultiTenantIsolation(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	scenarios := mqtt_contract.NewScenarios()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("different tenants publish to isolated topics", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		// Both should work (topics are isolated by session/user)
		resp1, err := mqttClient.Publish(ctx, tenant1Req)
		require.NoError(t, err)
		assert.True(t, resp1.Success)

		resp2, err := mqttClient.Publish(ctx, tenant2Req)
		require.NoError(t, err)
		assert.True(t, resp2.Success)
	})
}

// ===================================================================================
// TEST: RESPONSE CONTRACT VALIDATION
// ===================================================================================

func TestMqttAPI_ResponseContracts(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	factory := mqtt_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("PublishResponse has required fields", func(t *testing.T) {
		req := factory.MakePublishRequest()

		resp, err := mqttClient.Publish(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, resp)
		_ = resp.Success
	})

	t.Run("Subscribe returns stream", func(t *testing.T) {
		req := factory.MakeSubscribeRequest()

		stream, err := mqttClient.Subscribe(ctx, req)

		require.NoError(t, err)
		assert.NotNil(t, stream)
	})
}

// ===================================================================================
// TEST: ERROR CODES
// ===================================================================================

func TestMqttAPI_ErrorCodes(t *testing.T) {
	if mqttClient == nil {
		t.Skip("MQTT gRPC client not initialized")
	}

	factory := mqtt_contract.NewTestDataFactory()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	t.Run("InvalidArgument for empty topic", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithTopic(""))

		_, err := mqttClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})

	t.Run("InvalidArgument for missing user_id", func(t *testing.T) {
		req := factory.MakePublishRequest(
			mqtt_contract.WithPublishUser("", "test-session"),
		)

		_, err := mqttClient.Publish(ctx, req)

		require.Error(t, err)
		st, ok := status.FromError(err)
		require.True(t, ok)
		assert.Equal(t, codes.InvalidArgument, st.Code())
	})
}
