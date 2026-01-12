// Package redis_contract provides test data factories and fixtures
// for Redis service contract testing.
//
// Usage:
//
//	factory := NewTestDataFactory()
//	req := factory.MakeSetRequest(
//	    WithKey("custom-key"),
//	    WithValue("custom-value"),
//	)
package redis_contract

import (
	"fmt"
	"time"

	pb "github.com/isa-cloud/isa_cloud/api/proto/redis"
)

// ============================================
// Test Data Factory
// ============================================

// TestDataFactory creates test data with sensible defaults
type TestDataFactory struct {
	// Counter for generating unique IDs
	counter int
}

// NewTestDataFactory creates a new factory instance
func NewTestDataFactory() *TestDataFactory {
	return &TestDataFactory{}
}

// nextID generates a unique ID for test data
func (f *TestDataFactory) nextID() string {
	f.counter++
	return fmt.Sprintf("test-%d-%d", time.Now().UnixNano(), f.counter)
}

// ============================================
// SetRequest Factory
// ============================================

// SetRequestOption modifies a SetRequest
type SetRequestOption func(*pb.SetRequest)

// MakeSetRequest creates a SetRequest with sensible defaults
func (f *TestDataFactory) MakeSetRequest(opts ...SetRequestOption) *pb.SetRequest {
	req := &pb.SetRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Key:            "test-key",
		Value:          "test-value",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithKey sets the key on SetRequest
func WithKey(key string) SetRequestOption {
	return func(req *pb.SetRequest) {
		req.Key = key
	}
}

// WithValue sets the value on SetRequest
func WithValue(value string) SetRequestOption {
	return func(req *pb.SetRequest) {
		req.Value = value
	}
}

// WithUser sets user_id and organization_id on SetRequest
func WithUser(userID, orgID string) SetRequestOption {
	return func(req *pb.SetRequest) {
		req.UserId = userID
		req.OrganizationId = orgID
	}
}

// WithRandomKey generates a unique key for isolation in tests
func (f *TestDataFactory) WithRandomKey() SetRequestOption {
	key := f.nextID()
	return func(req *pb.SetRequest) {
		req.Key = key
	}
}

// ============================================
// GetRequest Factory
// ============================================

// GetRequestOption modifies a GetRequest
type GetRequestOption func(*pb.GetRequest)

// MakeGetRequest creates a GetRequest with sensible defaults
func (f *TestDataFactory) MakeGetRequest(opts ...GetRequestOption) *pb.GetRequest {
	req := &pb.GetRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Key:            "test-key",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithGetKey sets the key on GetRequest
func WithGetKey(key string) GetRequestOption {
	return func(req *pb.GetRequest) {
		req.Key = key
	}
}

// WithGetUser sets user_id and organization_id on GetRequest
func WithGetUser(userID, orgID string) GetRequestOption {
	return func(req *pb.GetRequest) {
		req.UserId = userID
		req.OrganizationId = orgID
	}
}

// ============================================
// DeleteRequest Factory
// ============================================

// DeleteRequestOption modifies a DeleteRequest
type DeleteRequestOption func(*pb.DeleteRequest)

// MakeDeleteRequest creates a DeleteRequest with sensible defaults
func (f *TestDataFactory) MakeDeleteRequest(opts ...DeleteRequestOption) *pb.DeleteRequest {
	req := &pb.DeleteRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Key:            "test-key",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithDeleteKey sets the key on DeleteRequest
func WithDeleteKey(key string) DeleteRequestOption {
	return func(req *pb.DeleteRequest) {
		req.Key = key
	}
}

// ============================================
// DeleteMultipleRequest Factory
// ============================================

// DeleteMultipleRequestOption modifies a DeleteMultipleRequest
type DeleteMultipleRequestOption func(*pb.DeleteMultipleRequest)

// MakeDeleteMultipleRequest creates a DeleteMultipleRequest with sensible defaults
func (f *TestDataFactory) MakeDeleteMultipleRequest(opts ...DeleteMultipleRequestOption) *pb.DeleteMultipleRequest {
	req := &pb.DeleteMultipleRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Keys:           []string{"test-key-1", "test-key-2"},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithDeleteKeys sets the keys on DeleteMultipleRequest
func WithDeleteKeys(keys ...string) DeleteMultipleRequestOption {
	return func(req *pb.DeleteMultipleRequest) {
		req.Keys = keys
	}
}

// ============================================
// HSetRequest Factory (Hash operations)
// ============================================

// HSetRequestOption modifies an HSetRequest
type HSetRequestOption func(*pb.HSetRequest)

// MakeHSetRequest creates an HSetRequest with sensible defaults
func (f *TestDataFactory) MakeHSetRequest(opts ...HSetRequestOption) *pb.HSetRequest {
	req := &pb.HSetRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Key:            "test-hash",
		Fields: []*pb.HashField{
			{Field: "field1", Value: "value1"},
		},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithHashKey sets the key on HSetRequest
func WithHashKey(key string) HSetRequestOption {
	return func(req *pb.HSetRequest) {
		req.Key = key
	}
}

// WithFields sets the fields on HSetRequest
func WithFields(fields []*pb.HashField) HSetRequestOption {
	return func(req *pb.HSetRequest) {
		req.Fields = fields
	}
}

// WithFieldsFromMap creates HashFields from a map
func WithFieldsFromMap(m map[string]string) HSetRequestOption {
	return func(req *pb.HSetRequest) {
		fields := make([]*pb.HashField, 0, len(m))
		for k, v := range m {
			fields = append(fields, &pb.HashField{Field: k, Value: v})
		}
		req.Fields = fields
	}
}

// ============================================
// Test Scenarios (Pre-built combinations)
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

// ValidSetRequest returns a valid SetRequest for happy path testing
func (s *Scenarios) ValidSetRequest() *pb.SetRequest {
	return s.factory.MakeSetRequest()
}

// SetRequestEmptyKey returns a SetRequest with empty key (for EC-001)
func (s *Scenarios) SetRequestEmptyKey() *pb.SetRequest {
	return s.factory.MakeSetRequest(WithKey(""))
}

// SetRequestLongKey returns a SetRequest with key > 1024 chars (for EC-002)
func (s *Scenarios) SetRequestLongKey() *pb.SetRequest {
	longKey := make([]byte, 1025)
	for i := range longKey {
		longKey[i] = 'x'
	}
	return s.factory.MakeSetRequest(WithKey(string(longKey)))
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.SetRequest) {
	tenant1Req = s.factory.MakeSetRequest(
		WithKey("shared-key"),
		WithValue("tenant1-value"),
		WithUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakeSetRequest(
		WithKey("shared-key"),
		WithValue("tenant2-value"),
		WithUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedIsolatedKey returns the expected isolated key format
func ExpectedIsolatedKey(orgID, userID, key string) string {
	return fmt.Sprintf("%s:%s:%s", orgID, userID, key)
}

// DefaultIsolatedKey returns isolated key for default test user
func DefaultIsolatedKey(key string) string {
	return ExpectedIsolatedKey("test-org-001", "test-user-001", key)
}
