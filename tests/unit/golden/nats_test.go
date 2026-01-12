//go:build unit

// Package golden provides unit tests for NATS service contracts.
package golden

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	nats_contract "github.com/isa-cloud/isa_cloud/tests/contracts/nats"
)

// ===================================================================================
// TEST: DATA FACTORY - NATS
// ===================================================================================

func TestNATSTestDataFactory_MakePublishRequest(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakePublishRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Subject)
		assert.NotEmpty(t, req.Data)
	})

	t.Run("accepts custom subject via option", func(t *testing.T) {
		customSubject := "events.user.created"
		req := factory.MakePublishRequest(nats_contract.WithSubject(customSubject))

		assert.Equal(t, customSubject, req.Subject)
	})

	t.Run("accepts custom data via option", func(t *testing.T) {
		customData := []byte(`{"event":"test"}`)
		req := factory.MakePublishRequest(nats_contract.WithData(customData))

		assert.Equal(t, customData, req.Data)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakePublishRequest(nats_contract.WithUser("u1", "o1"))

		assert.Equal(t, "u1", req.UserId)
		assert.Equal(t, "o1", req.OrganizationId)
	})

	t.Run("supports multiple options chained", func(t *testing.T) {
		req := factory.MakePublishRequest(
			nats_contract.WithSubject("test.subject"),
			nats_contract.WithData([]byte("test")),
			nats_contract.WithUser("user-x", "org-x"),
		)

		assert.Equal(t, "test.subject", req.Subject)
		assert.Equal(t, []byte("test"), req.Data)
		assert.Equal(t, "user-x", req.UserId)
	})
}

func TestNATSTestDataFactory_MakeSubscribeRequest(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("creates valid subscribe request", func(t *testing.T) {
		req := factory.MakeSubscribeRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Subject)
	})

	t.Run("accepts wildcard subject", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(nats_contract.WithSubscribeSubject("events.*"))

		assert.Equal(t, "events.*", req.Subject)
	})

	t.Run("accepts queue group", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(nats_contract.WithQueueGroup("workers"))

		assert.Equal(t, "workers", req.QueueGroup)
	})
}

func TestNATSTestDataFactory_MakeCreateStreamRequest(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("creates valid JetStream stream request", func(t *testing.T) {
		req := factory.MakeCreateStreamRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotNil(t, req.Config)
		assert.NotEmpty(t, req.Config.Name)
	})

	t.Run("accepts stream name override", func(t *testing.T) {
		req := factory.MakeCreateStreamRequest(nats_contract.WithStreamName("ORDERS"))

		assert.Equal(t, "ORDERS", req.Config.Name)
	})

	t.Run("accepts stream subjects", func(t *testing.T) {
		req := factory.MakeCreateStreamRequest(nats_contract.WithStreamSubjects("orders.>", "payments.>"))

		assert.Contains(t, req.Config.Subjects, "orders.>")
		assert.Contains(t, req.Config.Subjects, "payments.>")
	})
}

func TestNATSTestDataFactory_MakeCreateConsumerRequest(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("creates valid JetStream consumer request", func(t *testing.T) {
		req := factory.MakeCreateConsumerRequest("TEST_STREAM")

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.Equal(t, "TEST_STREAM", req.StreamName)
		assert.NotNil(t, req.Config)
	})

	t.Run("accepts consumer name override", func(t *testing.T) {
		req := factory.MakeCreateConsumerRequest("EVENTS", nats_contract.WithConsumerName("my-consumer"))

		assert.Equal(t, "my-consumer", req.Config.Name)
	})
}

func TestNATSTestDataFactory_MakeKVPutRequest(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("creates valid KV put request", func(t *testing.T) {
		req := factory.MakeKVPutRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Bucket)
		assert.NotEmpty(t, req.Key)
	})

	t.Run("accepts bucket override", func(t *testing.T) {
		req := factory.MakeKVPutRequest(nats_contract.WithBucket("my-bucket"))

		assert.Equal(t, "my-bucket", req.Bucket)
	})

	t.Run("accepts key and value", func(t *testing.T) {
		req := factory.MakeKVPutRequest(
			nats_contract.WithKVKey("config-key"),
			nats_contract.WithKVValue([]byte("config-value")),
		)

		assert.Equal(t, "config-key", req.Key)
		assert.Equal(t, []byte("config-value"), req.Value)
	})
}

// ===================================================================================
// TEST: SCENARIOS - NATS
// ===================================================================================

func TestNATSScenarios(t *testing.T) {
	scenarios := nats_contract.NewScenarios()
	factory := nats_contract.NewTestDataFactory()

	t.Run("OrderCreatedEvent returns usable request", func(t *testing.T) {
		req := scenarios.OrderCreatedEvent("order-123")

		require.NotNil(t, req)
		assert.Contains(t, req.Subject, "orders")
		assert.NotEmpty(t, req.Data)
	})

	t.Run("WildcardSubscription uses wildcard", func(t *testing.T) {
		req := scenarios.WildcardSubscription()

		assert.True(t, strings.Contains(req.Subject, "*") || strings.Contains(req.Subject, ">"))
	})

	t.Run("QueueSubscription includes queue group", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(nats_contract.WithQueueGroup("workers"))

		assert.NotEmpty(t, req.QueueGroup)
	})

	t.Run("EmptySubject for edge case", func(t *testing.T) {
		req := scenarios.EmptySubject()

		assert.Empty(t, req.Subject)
	})

	t.Run("OversizedMessage creates large message", func(t *testing.T) {
		req := scenarios.OversizedMessage()

		assert.Greater(t, len(req.Data), 1024*1024)
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.UserId, tenant2.UserId)
		assert.NotEqual(t, tenant1.OrganizationId, tenant2.OrganizationId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - NATS
// ===================================================================================

func TestNATSBusinessRules(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	// BR-001: Subject Namespace Isolation
	t.Run("BR-001: subjects are namespaced by tenant", func(t *testing.T) {
		req := factory.MakePublishRequest(nats_contract.WithSubject("events.user.created"))

		isolatedSubject := nats_contract.ExpectedIsolatedSubject(req.OrganizationId, req.Subject)

		assert.Contains(t, isolatedSubject, req.OrganizationId)
		assert.Contains(t, isolatedSubject, req.Subject)
	})

	// BR-002: Required Auth Fields
	t.Run("BR-002: requests require user_id and organization_id", func(t *testing.T) {
		req := factory.MakePublishRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
	})

	// BR-003: Subject Hierarchy
	t.Run("BR-003: subject follows dot-notation hierarchy", func(t *testing.T) {
		subject := "events.user.created"
		req := factory.MakePublishRequest(nats_contract.WithSubject(subject))

		parts := strings.Split(req.Subject, ".")
		assert.GreaterOrEqual(t, len(parts), 2, "subject should have hierarchy")
	})

	// BR-004: Wildcard Subscriptions
	t.Run("BR-004: wildcard subscriptions are supported", func(t *testing.T) {
		scenarios := nats_contract.NewScenarios()
		req := scenarios.WildcardSubscription()

		hasWildcard := strings.Contains(req.Subject, "*") || strings.Contains(req.Subject, ">")
		assert.True(t, hasWildcard)
	})

	// BR-005: Queue Groups
	t.Run("BR-005: queue groups enable load balancing", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(nats_contract.WithQueueGroup("workers"))

		assert.NotEmpty(t, req.QueueGroup)
	})
}

// ===================================================================================
// TEST: EDGE CASES - NATS
// ===================================================================================

func TestNATSEdgeCases(t *testing.T) {
	scenarios := nats_contract.NewScenarios()
	factory := nats_contract.NewTestDataFactory()

	// EC-001: Empty Subject
	t.Run("EC-001: empty subject should be rejectable", func(t *testing.T) {
		req := scenarios.EmptySubject()

		assert.Empty(t, req.Subject)
	})

	// EC-002: Invalid Subject Characters
	t.Run("EC-002: subject with spaces should be rejectable", func(t *testing.T) {
		req := factory.MakePublishRequest(nats_contract.WithSubject("invalid subject"))

		assert.Contains(t, req.Subject, " ")
	})

	// EC-003: Large Payload
	t.Run("EC-003: payload exceeding size limit", func(t *testing.T) {
		req := scenarios.OversizedMessage()

		assert.Greater(t, len(req.Data), 1024*1024)
	})

	// EC-004: Empty Payload
	t.Run("EC-004: empty payload may be valid", func(t *testing.T) {
		req := factory.MakePublishRequest(nats_contract.WithData([]byte{}))

		assert.Empty(t, req.Data)
	})

	// EC-005: Very Long Subject
	t.Run("EC-005: very long subject", func(t *testing.T) {
		longSubject := strings.Repeat("segment.", 100) + "end"
		req := factory.MakePublishRequest(nats_contract.WithSubject(longSubject))

		assert.Greater(t, len(req.Subject), 500)
	})

	// EC-006: Binary Payload
	t.Run("EC-006: binary payload", func(t *testing.T) {
		binaryData := []byte{0x00, 0x01, 0x02, 0xFF, 0xFE}
		req := factory.MakePublishRequest(nats_contract.WithData(binaryData))

		assert.Equal(t, binaryData, req.Data)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - NATS
// ===================================================================================

func TestNATSMultiTenantIsolation(t *testing.T) {
	scenarios := nats_contract.NewScenarios()

	t.Run("same logical subject resolves to different physical subjects per tenant", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		physicalSubject1 := nats_contract.ExpectedIsolatedSubject(tenant1.OrganizationId, tenant1.Subject)
		physicalSubject2 := nats_contract.ExpectedIsolatedSubject(tenant2.OrganizationId, tenant2.Subject)

		assert.NotEqual(t, physicalSubject1, physicalSubject2)
	})

	t.Run("stream names are isolated per tenant", func(t *testing.T) {
		factory := nats_contract.NewTestDataFactory()

		req1 := factory.MakeCreateStreamRequest(nats_contract.WithStreamName("EVENTS"))
		req2 := factory.MakeCreateStreamRequest(nats_contract.WithStreamName("EVENTS"))

		// Override orgs for testing
		req1.OrganizationId = "org-1"
		req2.OrganizationId = "org-2"

		// Use ExpectedIsolatedSubject for stream isolation (same pattern)
		stream1 := nats_contract.ExpectedIsolatedSubject(req1.OrganizationId, req1.Config.Name)
		stream2 := nats_contract.ExpectedIsolatedSubject(req2.OrganizationId, req2.Config.Name)

		assert.NotEqual(t, stream1, stream2)
	})
}

// ===================================================================================
// TEST: JETSTREAM
// ===================================================================================

func TestNATSJetStream(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("stream creation includes stream config", func(t *testing.T) {
		req := factory.MakeCreateStreamRequest(nats_contract.WithStreamName("EVENTS"))

		assert.Equal(t, "EVENTS", req.Config.Name)
		assert.NotEmpty(t, req.Config.Subjects)
	})

	t.Run("consumer request has required fields", func(t *testing.T) {
		req := factory.MakeCreateConsumerRequest("TEST_STREAM")

		assert.NotEmpty(t, req.StreamName)
		assert.NotNil(t, req.Config)
	})
}

// ===================================================================================
// TEST: KV STORE
// ===================================================================================

func TestNATSKVStore(t *testing.T) {
	factory := nats_contract.NewTestDataFactory()

	t.Run("KV put request has required fields", func(t *testing.T) {
		req := factory.MakeKVPutRequest()

		assert.NotEmpty(t, req.Bucket)
		assert.NotEmpty(t, req.Key)
	})

	t.Run("KV get request has required fields", func(t *testing.T) {
		req := factory.MakeKVGetRequest()

		assert.NotEmpty(t, req.Bucket)
		assert.NotEmpty(t, req.Key)
	})
}
