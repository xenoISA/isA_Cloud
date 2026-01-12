// Package nats_contract provides test data factories and fixtures
// for NATS service contract testing.
package nats_contract

import (
	"fmt"
	"time"

	pb "github.com/isa-cloud/isa_cloud/api/proto/nats"
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
// Publish Request Factory
// ============================================

// PublishRequestOption modifies a PublishRequest
type PublishRequestOption func(*pb.PublishRequest)

// MakePublishRequest creates a PublishRequest with sensible defaults
func (f *TestDataFactory) MakePublishRequest(opts ...PublishRequestOption) *pb.PublishRequest {
	req := &pb.PublishRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Subject:        "test.events",
		Data:           []byte(`{"event": "test"}`),
		Headers:        map[string]string{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithSubject sets the subject
func WithSubject(subject string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Subject = subject
	}
}

// WithData sets the message data
func WithData(data []byte) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Data = data
	}
}

// WithJSONData sets JSON string as message data
func WithJSONData(json string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Data = []byte(json)
	}
}

// WithHeaders sets the headers
func WithHeaders(headers map[string]string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.Headers = headers
	}
}

// WithUser sets user_id and organization_id
func WithUser(userID, orgID string) PublishRequestOption {
	return func(req *pb.PublishRequest) {
		req.UserId = userID
		req.OrganizationId = orgID
	}
}

// ============================================
// Subscribe Request Factory
// ============================================

// SubscribeRequestOption modifies a SubscribeRequest
type SubscribeRequestOption func(*pb.SubscribeRequest)

// MakeSubscribeRequest creates a SubscribeRequest with defaults
func (f *TestDataFactory) MakeSubscribeRequest(opts ...SubscribeRequestOption) *pb.SubscribeRequest {
	req := &pb.SubscribeRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Subject:        "test.events",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithSubscribeSubject sets the subject for subscription
func WithSubscribeSubject(subject string) SubscribeRequestOption {
	return func(req *pb.SubscribeRequest) {
		req.Subject = subject
	}
}

// WithQueueGroup sets the queue group
func WithQueueGroup(queueGroup string) SubscribeRequestOption {
	return func(req *pb.SubscribeRequest) {
		req.QueueGroup = queueGroup
	}
}

// ============================================
// JetStream Request Factories
// ============================================

// CreateStreamRequestOption modifies a CreateStreamRequest
type CreateStreamRequestOption func(*pb.CreateStreamRequest)

// MakeCreateStreamRequest creates a stream creation request
func (f *TestDataFactory) MakeCreateStreamRequest(opts ...CreateStreamRequestOption) *pb.CreateStreamRequest {
	req := &pb.CreateStreamRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Config: &pb.StreamConfig{
			Name:     "TEST_STREAM",
			Subjects: []string{"test.>"},
			Storage:  pb.StorageType_STORAGE_FILE,
			MaxMsgs:  10000,
		},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithStreamName sets the stream name in config
func WithStreamName(name string) CreateStreamRequestOption {
	return func(req *pb.CreateStreamRequest) {
		if req.Config != nil {
			req.Config.Name = name
		}
	}
}

// WithStreamSubjects sets the subjects for the stream
func WithStreamSubjects(subjects ...string) CreateStreamRequestOption {
	return func(req *pb.CreateStreamRequest) {
		if req.Config != nil {
			req.Config.Subjects = subjects
		}
	}
}

// WithStreamConfig sets the stream config
func WithStreamConfig(config *pb.StreamConfig) CreateStreamRequestOption {
	return func(req *pb.CreateStreamRequest) {
		req.Config = config
	}
}

// CreateConsumerRequestOption modifies a CreateConsumerRequest
type CreateConsumerRequestOption func(*pb.CreateConsumerRequest)

// MakeCreateConsumerRequest creates a consumer creation request
func (f *TestDataFactory) MakeCreateConsumerRequest(streamName string, opts ...CreateConsumerRequestOption) *pb.CreateConsumerRequest {
	req := &pb.CreateConsumerRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		StreamName:     streamName,
		Config: &pb.ConsumerConfig{
			Name:           "test-consumer",
			DurableName:    "test-durable",
			DeliveryPolicy: pb.DeliveryPolicy_DELIVERY_ALL,
			AckPolicy:      pb.AckPolicy_ACK_EXPLICIT,
		},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithConsumerName sets the consumer name in config
func WithConsumerName(name string) CreateConsumerRequestOption {
	return func(req *pb.CreateConsumerRequest) {
		if req.Config != nil {
			req.Config.Name = name
		}
	}
}

// WithConsumerConfig sets the consumer config
func WithConsumerConfig(config *pb.ConsumerConfig) CreateConsumerRequestOption {
	return func(req *pb.CreateConsumerRequest) {
		req.Config = config
	}
}

// ============================================
// KV Request Factories
// ============================================

// KVPutRequestOption modifies a KVPutRequest
type KVPutRequestOption func(*pb.KVPutRequest)

// MakeKVPutRequest creates a KV put request
func (f *TestDataFactory) MakeKVPutRequest(opts ...KVPutRequestOption) *pb.KVPutRequest {
	req := &pb.KVPutRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Bucket:         "test-bucket",
		Key:            "test-key",
		Value:          []byte("test-value"),
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithBucket sets the bucket name
func WithBucket(bucket string) KVPutRequestOption {
	return func(req *pb.KVPutRequest) {
		req.Bucket = bucket
	}
}

// WithKVKey sets the key
func WithKVKey(key string) KVPutRequestOption {
	return func(req *pb.KVPutRequest) {
		req.Key = key
	}
}

// WithKVValue sets the value
func WithKVValue(value []byte) KVPutRequestOption {
	return func(req *pb.KVPutRequest) {
		req.Value = value
	}
}

// KVGetRequestOption modifies a KVGetRequest
type KVGetRequestOption func(*pb.KVGetRequest)

// MakeKVGetRequest creates a KV get request
func (f *TestDataFactory) MakeKVGetRequest(opts ...KVGetRequestOption) *pb.KVGetRequest {
	req := &pb.KVGetRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Bucket:         "test-bucket",
		Key:            "test-key",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
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

// SimplePublish returns a basic publish request
func (s *Scenarios) SimplePublish() *pb.PublishRequest {
	return s.factory.MakePublishRequest()
}

// OrderCreatedEvent returns an order created event
func (s *Scenarios) OrderCreatedEvent(orderID string) *pb.PublishRequest {
	return s.factory.MakePublishRequest(
		WithSubject("orders.created"),
		WithJSONData(fmt.Sprintf(`{"order_id": "%s", "status": "created"}`, orderID)),
	)
}

// EmptySubject returns a publish request with empty subject (EC-001)
func (s *Scenarios) EmptySubject() *pb.PublishRequest {
	return s.factory.MakePublishRequest(WithSubject(""))
}

// InvalidSubject returns a publish request with invalid characters (EC-002)
func (s *Scenarios) InvalidSubject() *pb.PublishRequest {
	return s.factory.MakePublishRequest(WithSubject("invalid subject with spaces"))
}

// OversizedMessage returns a message > 1MB (EC-003)
func (s *Scenarios) OversizedMessage() *pb.PublishRequest {
	largeData := make([]byte, 2*1024*1024) // 2MB
	return s.factory.MakePublishRequest(WithData(largeData))
}

// WildcardSubscription returns a wildcard subscription
func (s *Scenarios) WildcardSubscription() *pb.SubscribeRequest {
	return s.factory.MakeSubscribeRequest(WithSubscribeSubject("orders.>"))
}

// MultiTenantScenario returns publish requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.PublishRequest) {
	tenant1Req = s.factory.MakePublishRequest(
		WithSubject("events.test"),
		WithUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakePublishRequest(
		WithSubject("events.test"),
		WithUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedIsolatedSubject returns the expected isolated subject
func ExpectedIsolatedSubject(orgID, subject string) string {
	return fmt.Sprintf("%s.%s", orgID, subject)
}

// DefaultIsolatedSubject returns isolated subject for default test org
func DefaultIsolatedSubject(subject string) string {
	return ExpectedIsolatedSubject("test-org-001", subject)
}
