//go:build unit

// Package golden provides unit tests for MQTT service contracts.
package golden

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	pb "github.com/isa-cloud/isa_cloud/api/proto/mqtt"
	mqtt_contract "github.com/isa-cloud/isa_cloud/tests/contracts/mqtt"
)

// ===================================================================================
// TEST: DATA FACTORY - MQTT
// ===================================================================================

func TestMQTTTestDataFactory_MakePublishRequest(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakePublishRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.SessionId)
		assert.NotEmpty(t, req.Topic)
		assert.NotEmpty(t, req.Payload)
	})

	t.Run("accepts custom topic via option", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithTopic("devices/sensor-001/temp"))

		assert.Equal(t, "devices/sensor-001/temp", req.Topic)
	})

	t.Run("accepts custom payload via option", func(t *testing.T) {
		payload := []byte(`{"temp": 25.5}`)
		req := factory.MakePublishRequest(mqtt_contract.WithPayload(payload))

		assert.Equal(t, payload, req.Payload)
	})

	t.Run("accepts QoS level via option", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithQoS(pb.QoSLevel_QOS_EXACTLY_ONCE))

		assert.Equal(t, pb.QoSLevel_QOS_EXACTLY_ONCE, req.Qos)
	})

	t.Run("accepts retained flag via option", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithRetained(true))

		assert.True(t, req.Retained)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithPublishUser("u1", "session-1"))

		assert.Equal(t, "u1", req.UserId)
		assert.Equal(t, "session-1", req.SessionId)
	})
}

func TestMQTTTestDataFactory_MakeSubscribeRequest(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("creates valid subscribe request", func(t *testing.T) {
		req := factory.MakeSubscribeRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.SessionId)
		assert.NotEmpty(t, req.TopicFilter)
	})

	t.Run("accepts topic filter via option", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(mqtt_contract.WithTopicFilter("devices/+/temperature"))

		assert.Equal(t, "devices/+/temperature", req.TopicFilter)
	})

	t.Run("accepts QoS level via option", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(mqtt_contract.WithSubscribeQoS(pb.QoSLevel_QOS_AT_LEAST_ONCE))

		assert.Equal(t, pb.QoSLevel_QOS_AT_LEAST_ONCE, req.Qos)
	})
}

func TestMQTTTestDataFactory_MakeUnsubscribeRequest(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("creates valid unsubscribe request", func(t *testing.T) {
		req := factory.MakeUnsubscribeRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.SessionId)
		assert.NotEmpty(t, req.TopicFilters)
	})

	t.Run("accepts multiple topics via option", func(t *testing.T) {
		req := factory.MakeUnsubscribeRequest(mqtt_contract.WithUnsubscribeTopics("topic1", "topic2"))

		assert.Contains(t, req.TopicFilters, "topic1")
		assert.Contains(t, req.TopicFilters, "topic2")
	})
}

func TestMQTTTestDataFactory_MakeConnectRequest(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("creates valid connect request", func(t *testing.T) {
		req := factory.MakeConnectRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.ClientId)
	})

	t.Run("accepts client ID via option", func(t *testing.T) {
		req := factory.MakeConnectRequest(mqtt_contract.WithClientID("my-client-123"))

		assert.Equal(t, "my-client-123", req.ClientId)
	})

	t.Run("accepts clean session via option", func(t *testing.T) {
		req := factory.MakeConnectRequest(mqtt_contract.WithCleanSession(false))

		assert.False(t, req.CleanSession)
	})
}

// ===================================================================================
// TEST: SCENARIOS - MQTT
// ===================================================================================

func TestMQTTScenarios(t *testing.T) {
	scenarios := mqtt_contract.NewScenarios()

	t.Run("TemperatureReading returns sensor data", func(t *testing.T) {
		req := scenarios.TemperatureReading("sensor-001", 25.5)

		require.NotNil(t, req)
		assert.Contains(t, req.Topic, "sensor-001")
		assert.Contains(t, req.Topic, "temperature")
	})

	t.Run("DeviceStatus returns status message", func(t *testing.T) {
		req := scenarios.DeviceStatus("device-001", true)

		assert.Contains(t, req.Topic, "status")
		assert.True(t, req.Retained)
	})

	t.Run("SingleLevelWildcardSubscription uses +", func(t *testing.T) {
		req := scenarios.SingleLevelWildcardSubscription()

		assert.Contains(t, req.TopicFilter, "+")
	})

	t.Run("MultiLevelWildcardSubscription uses #", func(t *testing.T) {
		req := scenarios.MultiLevelWildcardSubscription()

		assert.Contains(t, req.TopicFilter, "#")
	})

	t.Run("EmptyTopic for edge case", func(t *testing.T) {
		req := scenarios.EmptyTopic()

		assert.Empty(t, req.Topic)
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.NotEqual(t, tenant1.UserId, tenant2.UserId)
	})
}

// ===================================================================================
// TEST: BUSINESS RULES - MQTT
// ===================================================================================

func TestMQTTBusinessRules(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("BR-001: topics are namespaced by tenant", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithTopic("devices/sensor/temp"))

		isolatedTopic := mqtt_contract.ExpectedIsolatedTopic("test-org-001", req.Topic)
		assert.Contains(t, isolatedTopic, "test-org-001")
	})

	t.Run("BR-002: requests require user_id and session_id", func(t *testing.T) {
		req := factory.MakePublishRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.SessionId)
	})

	t.Run("BR-003: QoS levels are supported", func(t *testing.T) {
		qosLevels := []pb.QoSLevel{
			pb.QoSLevel_QOS_AT_MOST_ONCE,
			pb.QoSLevel_QOS_AT_LEAST_ONCE,
			pb.QoSLevel_QOS_EXACTLY_ONCE,
		}

		for _, qos := range qosLevels {
			req := factory.MakePublishRequest(mqtt_contract.WithQoS(qos))
			assert.Equal(t, qos, req.Qos)
		}
	})

	t.Run("BR-004: retained messages are supported", func(t *testing.T) {
		scenarios := mqtt_contract.NewScenarios()
		req := scenarios.RetainedMessage("device/status")

		assert.True(t, req.Retained)
	})
}

// ===================================================================================
// TEST: EDGE CASES - MQTT
// ===================================================================================

func TestMQTTEdgeCases(t *testing.T) {
	scenarios := mqtt_contract.NewScenarios()
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("EC-001: empty topic should be rejectable", func(t *testing.T) {
		req := scenarios.EmptyTopic()

		assert.Empty(t, req.Topic)
	})

	t.Run("EC-002: topic with null characters should be rejectable", func(t *testing.T) {
		req := scenarios.InvalidTopic()

		assert.Contains(t, req.Topic, "\x00")
	})

	t.Run("EC-003: topic exceeding length limit", func(t *testing.T) {
		req := scenarios.TopicTooLong()

		assert.Greater(t, len(req.Topic), 65535)
	})

	t.Run("EC-004: empty payload may be valid", func(t *testing.T) {
		req := factory.MakePublishRequest(mqtt_contract.WithPayload([]byte{}))

		assert.Empty(t, req.Payload)
	})

	t.Run("EC-005: wildcard in publish topic should be rejectable", func(t *testing.T) {
		req := scenarios.WildcardInPublish()

		assert.Contains(t, req.Topic, "+")
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION - MQTT
// ===================================================================================

func TestMQTTMultiTenantIsolation(t *testing.T) {
	scenarios := mqtt_contract.NewScenarios()

	t.Run("same logical topic resolves to different physical topics per tenant", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.Equal(t, tenant1.Topic, tenant2.Topic)

		physicalTopic1 := mqtt_contract.ExpectedIsolatedTopic("org-001", tenant1.Topic)
		physicalTopic2 := mqtt_contract.ExpectedIsolatedTopic("org-002", tenant2.Topic)

		assert.NotEqual(t, physicalTopic1, physicalTopic2)
	})
}

// ===================================================================================
// TEST: WILDCARD SUBSCRIPTIONS
// ===================================================================================

func TestMQTTWildcardSubscriptions(t *testing.T) {
	factory := mqtt_contract.NewTestDataFactory()

	t.Run("single level wildcard (+)", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(mqtt_contract.WithTopicFilter("devices/+/temperature"))

		assert.Contains(t, req.TopicFilter, "+")
		parts := strings.Split(req.TopicFilter, "/")
		assert.Equal(t, "+", parts[1])
	})

	t.Run("multi level wildcard (#)", func(t *testing.T) {
		req := factory.MakeSubscribeRequest(mqtt_contract.WithTopicFilter("devices/#"))

		assert.True(t, strings.HasSuffix(req.TopicFilter, "#"))
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestMQTTAssertionHelpers(t *testing.T) {
	t.Run("ExpectedIsolatedTopic formats correctly", func(t *testing.T) {
		topic := mqtt_contract.ExpectedIsolatedTopic("org-001", "devices/temp")

		assert.Contains(t, topic, "org-001")
		assert.Contains(t, topic, "devices/temp")
	})

	t.Run("DefaultIsolatedTopic uses test defaults", func(t *testing.T) {
		topic := mqtt_contract.DefaultIsolatedTopic("sensors/data")

		assert.Contains(t, topic, "test-org-001")
	})
}
