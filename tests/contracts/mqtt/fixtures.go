// Package mqtt_contract provides test data factories and fixtures
// for MQTT service contract testing.
package mqtt_contract

import (
	"fmt"
	"time"

	pb "github.com/isa-cloud/isa_cloud/api/proto/mqtt"
)

// ============================================
// Test Data Factory
// ============================================

// TestDataFactory creates test data with sensible defaults
type TestDataFactory struct {
	counter int
}

// NewTestDataFactory creates a new factory instance
func NewTestDataFactory() *TestDataFactory {
	return &TestDataFactory{}
}

func (f *TestDataFactory) nextID() string {
	f.counter++
	return fmt.Sprintf("test-%d-%d", time.Now().UnixNano(), f.counter)
}

// ============================================
// Publish Request Factories
// ============================================

// PublishRequestOption modifies a PublishRequest
type PublishRequestOption func(*pb.PublishRequest)

// MakePublishRequest creates a PublishRequest with sensible defaults
func (f *TestDataFactory) MakePublishRequest(opts ...PublishRequestOption) *pb.PublishRequest {
	req := &pb.PublishRequest{
		UserId:     "test-user-001",
		SessionId:  "test-session-001",
		Topic:      "devices/sensor-001/temperature",
		Payload:    []byte(`{"value": 23.5, "unit": "celsius"}`),
		Qos:        pb.QoSLevel_QOS_AT_LEAST_ONCE,
		Retained:   false,
		Properties: map[string]string{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithTopic sets the topic
func WithTopic(topic string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Topic = topic
	}
}

// WithPayload sets the message payload
func WithPayload(payload []byte) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Payload = payload
	}
}

// WithJSONPayload sets JSON string as payload
func WithJSONPayload(json string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Payload = []byte(json)
	}
}

// WithQoS sets the QoS level
func WithQoS(qos pb.QoSLevel) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Qos = qos
	}
}

// WithRetained sets the retained flag
func WithRetained(retained bool) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Retained = retained
	}
}

// WithPublishUser sets user and session IDs
func WithPublishUser(userID, sessionID string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.UserId = userID
		req.SessionId = sessionID
	}
}

// ============================================
// Subscribe Request Factories
// ============================================

// SubscribeRequestOption modifies a SubscribeRequest
type SubscribeRequestOption func(*pb.SubscribeRequest)

// MakeSubscribeRequest creates a SubscribeRequest with defaults
func (f *TestDataFactory) MakeSubscribeRequest(opts ...SubscribeRequestOption) *pb.SubscribeRequest {
	req := &pb.SubscribeRequest{
		UserId:      "test-user-001",
		SessionId:   "test-session-001",
		TopicFilter: "devices/+/temperature",
		Qos:         pb.QoSLevel_QOS_AT_LEAST_ONCE,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithTopicFilter sets the subscription topic filter
func WithTopicFilter(topicFilter string) SubscribeRequestOption {
	return func(req *pb.SubscribeRequest) {
		req.TopicFilter = topicFilter
	}
}

// WithSubscribeQoS sets the subscription QoS
func WithSubscribeQoS(qos pb.QoSLevel) SubscribeRequestOption {
	return func(req *pb.SubscribeRequest) {
		req.Qos = qos
	}
}

// WithSubscribeUser sets user and session IDs
func WithSubscribeUser(userID, sessionID string) SubscribeRequestOption {
	return func(req *pb.SubscribeRequest) {
		req.UserId = userID
		req.SessionId = sessionID
	}
}

// ============================================
// Unsubscribe Request Factories
// ============================================

// UnsubscribeRequestOption modifies an UnsubscribeRequest
type UnsubscribeRequestOption func(*pb.UnsubscribeRequest)

// MakeUnsubscribeRequest creates an UnsubscribeRequest with defaults
func (f *TestDataFactory) MakeUnsubscribeRequest(opts ...UnsubscribeRequestOption) *pb.UnsubscribeRequest {
	req := &pb.UnsubscribeRequest{
		UserId:       "test-user-001",
		SessionId:    "test-session-001",
		TopicFilters: []string{"devices/+/temperature"},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithUnsubscribeTopics sets the topics to unsubscribe
func WithUnsubscribeTopics(topics ...string) UnsubscribeRequestOption {
	return func(req *pb.UnsubscribeRequest) {
		req.TopicFilters = topics
	}
}

// ============================================
// Connect Request Factories
// ============================================

// ConnectRequestOption modifies a ConnectRequest
type ConnectRequestOption func(*pb.ConnectRequest)

// MakeConnectRequest creates a ConnectRequest with defaults
func (f *TestDataFactory) MakeConnectRequest(opts ...ConnectRequestOption) *pb.ConnectRequest {
	req := &pb.ConnectRequest{
		UserId:       "test-user-001",
		ClientId:     f.nextID(),
		CleanSession: true,
		KeepAlive:    60,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithClientID sets the client ID
func WithClientID(clientID string) ConnectRequestOption {
	return func(req *pb.ConnectRequest) {
		req.ClientId = clientID
	}
}

// WithCleanSession sets the clean session flag
func WithCleanSession(cleanSession bool) ConnectRequestOption {
	return func(req *pb.ConnectRequest) {
		req.CleanSession = cleanSession
	}
}

// ============================================
// Test Scenarios
// ============================================

// Scenarios provides pre-built test scenarios
type Scenarios struct {
	factory *TestDataFactory
}

// NewScenarios creates a scenarios helper
func NewScenarios() *Scenarios {
	return &Scenarios{
		factory: NewTestDataFactory(),
	}
}

// TemperatureReading returns a temperature sensor reading
func (s *Scenarios) TemperatureReading(deviceID string, value float64) *pb.PublishRequest {
	return s.factory.MakePublishRequest(
		WithTopic(fmt.Sprintf("devices/%s/temperature", deviceID)),
		WithJSONPayload(fmt.Sprintf(`{"value": %.2f, "unit": "celsius", "timestamp": "%s"}`,
			value, time.Now().Format(time.RFC3339))),
		WithQoS(pb.QoSLevel_QOS_AT_LEAST_ONCE),
	)
}

// DeviceStatus returns a device status message
func (s *Scenarios) DeviceStatus(deviceID string, online bool) *pb.PublishRequest {
	status := "offline"
	if online {
		status = "online"
	}
	return s.factory.MakePublishRequest(
		WithTopic(fmt.Sprintf("devices/%s/status", deviceID)),
		WithJSONPayload(fmt.Sprintf(`{"status": "%s"}`, status)),
		WithQoS(pb.QoSLevel_QOS_AT_LEAST_ONCE),
		WithRetained(true),
	)
}

// CommandMessage returns a command to device
func (s *Scenarios) CommandMessage(deviceID string, command string) *pb.PublishRequest {
	return s.factory.MakePublishRequest(
		WithTopic(fmt.Sprintf("devices/%s/commands", deviceID)),
		WithJSONPayload(fmt.Sprintf(`{"command": "%s"}`, command)),
		WithQoS(pb.QoSLevel_QOS_EXACTLY_ONCE),
	)
}

// SingleLevelWildcardSubscription returns subscription with +
func (s *Scenarios) SingleLevelWildcardSubscription() *pb.SubscribeRequest {
	return s.factory.MakeSubscribeRequest(
		WithTopicFilter("devices/+/temperature"),
	)
}

// MultiLevelWildcardSubscription returns subscription with #
func (s *Scenarios) MultiLevelWildcardSubscription() *pb.SubscribeRequest {
	return s.factory.MakeSubscribeRequest(
		WithTopicFilter("devices/#"),
	)
}

// EmptyTopic returns publish with empty topic (EC-001)
func (s *Scenarios) EmptyTopic() *pb.PublishRequest {
	return s.factory.MakePublishRequest(WithTopic(""))
}

// InvalidTopic returns publish with invalid characters (EC-002)
func (s *Scenarios) InvalidTopic() *pb.PublishRequest {
	return s.factory.MakePublishRequest(WithTopic("topic\x00with\x00nulls"))
}

// TopicTooLong returns publish with oversized topic (EC-003)
func (s *Scenarios) TopicTooLong() *pb.PublishRequest {
	longTopic := make([]byte, 70000)
	for i := range longTopic {
		longTopic[i] = 'x'
	}
	return s.factory.MakePublishRequest(WithTopic(string(longTopic)))
}

// WildcardInPublish returns publish with wildcard (EC-005)
func (s *Scenarios) WildcardInPublish() *pb.PublishRequest {
	return s.factory.MakePublishRequest(WithTopic("devices/+/temperature"))
}

// RetainedMessage returns a message with retain flag
func (s *Scenarios) RetainedMessage(topic string) *pb.PublishRequest {
	return s.factory.MakePublishRequest(
		WithTopic(topic),
		WithRetained(true),
	)
}

// ClearRetainedMessage returns empty payload to clear retained
func (s *Scenarios) ClearRetainedMessage(topic string) *pb.PublishRequest {
	return s.factory.MakePublishRequest(
		WithTopic(topic),
		WithPayload([]byte{}),
		WithRetained(true),
	)
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.PublishRequest) {
	tenant1Req = s.factory.MakePublishRequest(
		WithTopic("devices/shared/temp"),
		WithPublishUser("user-001", "session-001"),
	)
	tenant2Req = s.factory.MakePublishRequest(
		WithTopic("devices/shared/temp"),
		WithPublishUser("user-002", "session-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedIsolatedTopic returns the expected isolated topic
func ExpectedIsolatedTopic(orgID, topic string) string {
	return fmt.Sprintf("%s/%s", orgID, topic)
}

// DefaultIsolatedTopic returns isolated topic for default test org
func DefaultIsolatedTopic(topic string) string {
	return ExpectedIsolatedTopic("test-org-001", topic)
}
