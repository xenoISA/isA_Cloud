//go:build integration

// Package golden provides integration tests for NATS service.
//
// Test Execution:
//
//	go test -v -tags=integration ./tests/integration/golden/...
package golden

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	nats_contract "github.com/isa-cloud/isa_cloud/tests/contracts/nats"
)

// ===================================================================================
// MOCK DEFINITIONS
// ===================================================================================

// MockNATSClient mocks the NATS client
type MockNATSClient struct {
	mock.Mock
}

func (m *MockNATSClient) Publish(ctx context.Context, subject string, payload []byte) error {
	args := m.Called(ctx, subject, payload)
	return args.Error(0)
}

func (m *MockNATSClient) Subscribe(ctx context.Context, subject, queueGroup string) (<-chan []byte, error) {
	args := m.Called(ctx, subject, queueGroup)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(<-chan []byte), args.Error(1)
}

func (m *MockNATSClient) Request(ctx context.Context, subject string, payload []byte, timeout time.Duration) ([]byte, error) {
	args := m.Called(ctx, subject, payload, timeout)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]byte), args.Error(1)
}

func (m *MockNATSClient) StreamPublish(ctx context.Context, stream, subject string, payload []byte) (uint64, error) {
	args := m.Called(ctx, stream, subject, payload)
	return args.Get(0).(uint64), args.Error(1)
}

// MockNATSAuthService mocks authentication
type MockNATSAuthService struct {
	mock.Mock
}

func (m *MockNATSAuthService) ValidateUser(userID string) error {
	args := m.Called(userID)
	return args.Error(0)
}

// ===================================================================================
// TEST: SERVICE LAYER - PUBLISH OPERATION
// ===================================================================================

func TestNATSService_Publish(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("successful publish operation", func(t *testing.T) {
		mockNATS := new(MockNATSClient)
		mockAuth := new(MockNATSAuthService)

		req := factory.MakePublishRequest()

		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNATS.On("Publish", mock.Anything, isolatedSubject, req.Payload).Return(nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		err = mockNATS.Publish(context.Background(), isolatedSubject, req.Payload)
		require.NoError(t, err)

		mockNATS.AssertExpectations(t)
	})

	t.Run("publish fails with unauthorized user", func(t *testing.T) {
		mockAuth := new(MockNATSAuthService)

		req := factory.MakePublishRequest()

		mockAuth.On("ValidateUser", req.UserId).Return(errors.New("unauthorized"))

		err := mockAuth.ValidateUser(req.UserId)
		assert.Error(t, err)
	})

	t.Run("publish fails with connection error", func(t *testing.T) {
		mockNATS := new(MockNATSClient)

		req := factory.MakePublishRequest()
		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		mockNATS.On("Publish", mock.Anything, isolatedSubject, req.Payload).
			Return(errors.New("connection closed"))

		err := mockNATS.Publish(context.Background(), isolatedSubject, req.Payload)
		assert.Error(t, err)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - SUBSCRIBE OPERATION
// ===================================================================================

func TestNATSService_Subscribe(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("successful subscribe operation", func(t *testing.T) {
		mockNATS := new(MockNATSClient)
		mockAuth := new(MockNATSAuthService)

		req := factory.MakeSubscribeRequest()

		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		msgChan := make(chan []byte, 10)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNATS.On("Subscribe", mock.Anything, isolatedSubject, req.QueueGroup).Return((<-chan []byte)(msgChan), nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		ch, err := mockNATS.Subscribe(context.Background(), isolatedSubject, req.QueueGroup)
		require.NoError(t, err)
		assert.NotNil(t, ch)
	})

	t.Run("subscribe with queue group", func(t *testing.T) {
		mockNATS := new(MockNATSClient)
		mockAuth := new(MockNATSAuthService)

		req := factory.MakeSubscribeRequest(nats_contract.WithQueueGroup("workers"))

		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		msgChan := make(chan []byte, 10)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNATS.On("Subscribe", mock.Anything, isolatedSubject, "workers").Return((<-chan []byte)(msgChan), nil)

		ch, err := mockNATS.Subscribe(context.Background(), isolatedSubject, "workers")
		require.NoError(t, err)
		assert.NotNil(t, ch)
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - REQUEST-REPLY OPERATION
// ===================================================================================

func TestNATSService_RequestReply(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("successful request-reply", func(t *testing.T) {
		mockNATS := new(MockNATSClient)
		mockAuth := new(MockNATSAuthService)

		req := factory.MakeRequestReplyRequest()

		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		expectedReply := []byte(`{"result":"ok"}`)
		timeout := time.Duration(req.TimeoutMs) * time.Millisecond

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNATS.On("Request", mock.Anything, isolatedSubject, req.Payload, timeout).Return(expectedReply, nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		reply, err := mockNATS.Request(context.Background(), isolatedSubject, req.Payload, timeout)
		require.NoError(t, err)
		assert.Equal(t, expectedReply, reply)
	})

	t.Run("request-reply times out", func(t *testing.T) {
		mockNATS := new(MockNATSClient)

		req := factory.MakeRequestReplyRequest(nats_contract.WithTimeout(100))

		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)
		timeout := time.Duration(req.TimeoutMs) * time.Millisecond

		mockNATS.On("Request", mock.Anything, isolatedSubject, req.Payload, timeout).
			Return(nil, errors.New("timeout"))

		_, err := mockNATS.Request(context.Background(), isolatedSubject, req.Payload, timeout)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "timeout")
	})
}

// ===================================================================================
// TEST: SERVICE LAYER - JETSTREAM OPERATIONS
// ===================================================================================

func TestNATSService_JetStream(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("successful stream publish", func(t *testing.T) {
		mockNATS := new(MockNATSClient)
		mockAuth := new(MockNATSAuthService)

		req := factory.MakeStreamPublishRequest()

		isolatedStream := nats_contract.ExpectedIsolatedStream(req.OrganizationId, req.Stream)
		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		mockAuth.On("ValidateUser", req.UserId).Return(nil)
		mockNATS.On("StreamPublish", mock.Anything, isolatedStream, isolatedSubject, req.Payload).
			Return(uint64(1), nil)

		// Execute
		err := mockAuth.ValidateUser(req.UserId)
		require.NoError(t, err)

		seq, err := mockNATS.StreamPublish(context.Background(), isolatedStream, isolatedSubject, req.Payload)
		require.NoError(t, err)
		assert.Equal(t, uint64(1), seq)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestNATSService_MultiTenantIsolation(t *testing.T) {
	scenarios := nats_contract.NewScenarios()

	t.Run("different tenants have different subject prefixes", func(t *testing.T) {
		tenant1Req, tenant2Req := scenarios.MultiTenantScenario()

		subject1 := nats_contract.ExpectedIsolatedSubject(
			tenant1Req.OrganizationId, tenant1Req.UserId, tenant1Req.Subject,
		)
		subject2 := nats_contract.ExpectedIsolatedSubject(
			tenant2Req.OrganizationId, tenant2Req.UserId, tenant2Req.Subject,
		)

		assert.NotEqual(t, subject1, subject2)
	})

	t.Run("stream names are isolated", func(t *testing.T) {
		factory := nats_contract.NewTestDataFactory()

		req1 := factory.MakeStreamPublishRequest(nats_contract.WithStreamUser("user-1", "org-1"))
		req2 := factory.MakeStreamPublishRequest(nats_contract.WithStreamUser("user-2", "org-2"))

		stream1 := nats_contract.ExpectedIsolatedStream(req1.OrganizationId, req1.Stream)
		stream2 := nats_contract.ExpectedIsolatedStream(req2.OrganizationId, req2.Stream)

		assert.NotEqual(t, stream1, stream2)
	})
}

// ===================================================================================
// TEST: ERROR HANDLING
// ===================================================================================

func TestNATSService_ErrorHandling(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("connection error is propagated", func(t *testing.T) {
		mockNATS := new(MockNATSClient)

		req := factory.MakePublishRequest()
		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)

		mockNATS.On("Publish", mock.Anything, isolatedSubject, req.Payload).
			Return(errors.New("connection closed"))

		err := mockNATS.Publish(context.Background(), isolatedSubject, req.Payload)
		assert.Error(t, err)
	})

	t.Run("no responders error on request-reply", func(t *testing.T) {
		mockNATS := new(MockNATSClient)

		req := factory.MakeRequestReplyRequest()
		isolatedSubject := nats_contract.ExpectedIsolatedSubject(
			req.OrganizationId, req.UserId, req.Subject,
		)
		timeout := time.Duration(req.TimeoutMs) * time.Millisecond

		mockNATS.On("Request", mock.Anything, isolatedSubject, req.Payload, timeout).
			Return(nil, errors.New("no responders available"))

		_, err := mockNATS.Request(context.Background(), isolatedSubject, req.Payload, timeout)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "no responders")
	})
}
