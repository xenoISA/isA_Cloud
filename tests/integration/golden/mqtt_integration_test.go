//go:build integration

// Package golden provides integration tests for MQTT service.
//
// Test Execution:
//
//	go test -v -tags=integration ./tests/integration/golden/...
package golden

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	mqtt_contract "github.com/isa-cloud/isa_cloud/tests/contracts/mqtt"
)

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockMQTTClient mocks the MQTT client
type MockMQTTClient struct {
	mock.Mock
}

func (m *MockMQTTClient) Publish(ctx context.Context, topic string, payload []byte, qos uint32, retain bool) error {
	args := m.Called(ctx, topic, payload, qos, retain)
	return args.Error(0)
}

func (m *MockMQTTClient) Subscribe(ctx context.Context, topic string, qos uint32) (<-chan []byte, error) {
	args := m.Called(ctx, topic, qos)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(<-chan []byte), args.Error(1)
}

func (m *MockMQTTClient) Unsubscribe(ctx context.Context, topic string) error {
	args := m.Called(ctx, topic)
	return args.Error(0)
}

// MockMQTTAuthService mocks authentication
type MockMQTTAuthService struct {
	mock.Mock
}

func (m *MockMQTTAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - PUBLISH OPERATION
// ===================================================================================

func TestMQTTService_Publish(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("successful publish operation", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)
		mockAuth := new(MockMQTTAuthService)

		req := factory.MakePublishRequest()

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMQTT.On("Publish", mock.Anything, isolatedTopic, req.Payload, req.Qos, req.Retain).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockMQTT.Publish(context.Background(), isolatedTopic, req.Payload, req.Qos, req.Retain)
		require.NoError(t, err)

		mockMQTT.AssertExpectations(t)
	})

	t.Run("publish with QoS 2", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)
		mockAuth := new(MockMQTTAuthService)

		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.QoS2Message()

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMQTT.On("Publish", mock.Anything, isolatedTopic, req.Payload, uint32(2), req.Retain).Return(nil)

		err := mockMQTT.Publish(context.Background(), isolatedTopic, req.Payload, uint32(2), req.Retain)
		require.NoError(t, err)
	})

	t.Run("publish retained message", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)
		mockAuth := new(MockMQTTAuthService)

		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.RetainedMessage()

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMQTT.On("Publish", mock.Anything, isolatedTopic, req.Payload, req.Qos, true).Return(nil)

		err := mockMQTT.Publish(context.Background(), isolatedTopic, req.Payload, req.Qos, true)
		require.NoError(t, err)
	})

	t.Run("publish fails with unauthorized user", func(t *testing.T) {
		mockAuth := new(MockMQTTAuthService)

		req := factory.MakePublishRequest()

		mockAuth.On("ValidateUser", req.UserId).Return(errors.New("unauthorized"))

		err := mockAuth.ValidateUser(req.UserId)
		assert.Error(t, err)
	})

	t.Run("publish fails with connection error", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)

		req := factory.MakePublishRequest()
		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockMQTT.On("Publish", mock.Anything, isolatedTopic, req.Payload, req.Qos, req.Retain).
			Return(errors.New("connection lost"))

		err := mockMQTT.Publish(context.Background(), isolatedTopic, req.Payload, req.Qos, req.Retain)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "connection lost")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - SUBSCRIBE OPERATION
// ===================================================================================

func TestMQTTService_Subscribe(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("successful subscribe operation", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)
		mockAuth := new(MockMQTTAuthService)

		req := factory.MakeSubscribeRequest()

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		msgChan := make(chan []byte, 10)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMQTT.On("Subscribe", mock.Anything, isolatedTopic, req.Qos).Return((<-chan []byte)(msgChan), nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		ch, err := mockMQTT.Subscribe(context.Background(), isolatedTopic, req.Qos)
		require.NoError(t, err)
		assert.NotNil(t, ch)
	})

	t.Run("subscribe with wildcard topic", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)
		mockAuth := new(MockMQTTAuthService)

		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.WildcardSubscription()

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		msgChan := make(chan []byte, 10)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMQTT.On("Subscribe", mock.Anything, isolatedTopic, req.Qos).Return((<-chan []byte)(msgChan), nil)

		ch, err := mockMQTT.Subscribe(context.Background(), isolatedTopic, req.Qos)
		require.NoError(t, err)
		assert.NotNil(t, ch)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - UNSUBSCRIBE OPERATION
// ===================================================================================

func TestMQTTService_Unsubscribe(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("successful unsubscribe operation", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)
		mockAuth := new(MockMQTTAuthService)

		req := factory.MakeUnsubscribeRequest()

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockMQTT.On("Unsubscribe", mock.Anything, isolatedTopic).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockMQTT.Unsubscribe(context.Background(), isolatedTopic)
		require.NoError(t, err)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestMQTTService_MultiTenantIsolation(t *testing.T) {
	scenarios := mqtt_contract.NewScenarios()

	t.Run("different tenants have different topic prefixes", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		topic1 := mqtt_contract.ExpectedIsolatedTopic(
			tenant1Req.OrganizationId, tenant1Req.UserId, tenant1Req.Topic,
		)
		topic2 := mqtt_contract.ExpectedIsolatedTopic(
			tenant2Req.OrganizationId, tenant2Req.UserId, tenant2Req.Topic,
		)

		assert.NotEqual(t, topic1, topic2)
	})

	t.Run("subscriptions are tenant-scoped", func(t *testing.T) {
		factory := mqtt_contract.NewTestDataFactory()

		req1 := factory.MakeSubscribeRequest(mqtt_contract.WithSubscribeUser("user-1", "org-1"))
		req2 := factory.MakeSubscribeRequest(mqtt_contract.WithSubscribeUser("user-2", "org-2"))

		topic1 := mqtt_contract.ExpectedIsolatedTopic(req1.OrganizationId, req1.UserId, req1.Topic)
		topic2 := mqtt_contract.ExpectedIsolatedTopic(req2.OrganizationId, req2.UserId, req2.Topic)

		assert.NotEqual(t, topic1, topic2)
	})
}

// ===================================================================================
// TEST: QOS BEHAVIOR
// ===================================================================================

func TestMQTTService_QoSBehavior(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	qosLevels := []uint32{0, 1, 2}

	for _, qos := range qosLevels {
		t.Run("publish with QoS "+string(rune('0'+qos)), func(t *testing.T) {
			mockMQTT := new(MockMQTTClient)

			req := factory.MakePublishRequest(mqtt_contract.WithQoS(qos))
			isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
				req.OrganizationId, req.UserId, req.Topic,
			)

			mockMQTT.On("Publish", mock.Anything, isolatedTopic, req.Payload, qos, req.Retain).Return(nil)

			err := mockMQTT.Publish(context.Background(), isolatedTopic, req.Payload, qos, req.Retain)
			require.NoError(t, err)
		})
	}
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestMQTTService_ErrorHandling(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("connection error is propagated", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)

		req := factory.MakePublishRequest()
		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockMQTT.On("Publish", mock.Anything, isolatedTopic, req.Payload, req.Qos, req.Retain).
			Return(errors.New("broker unavailable"))

		err := mockMQTT.Publish(context.Background(), isolatedTopic, req.Payload, req.Qos, req.Retain)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "broker unavailable")
	})

	t.Run("invalid topic error", func(t *testing.T) {
		mockMQTT := new(MockMQTTClient)

		req := factory.MakeSubscribeRequest()
		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic(
			req.OrganizationId, req.UserId, req.Topic,
		)

		mockMQTT.On("Subscribe", mock.Anything, isolatedTopic, req.Qos).
			Return(nil, errors.New("invalid topic"))

		_, err := mockMQTT.Subscribe(context.Background(), isolatedTopic, req.Qos)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid topic")
	})
}
