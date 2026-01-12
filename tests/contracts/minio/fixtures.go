// Package minio_contract provides test data factories and fixtures
// for MinIO service contract testing.
package minio_contract

import (
	"fmt"
	"time"

	pb "github.com/isa-cloud/isa_cloud/api/proto/minio"
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
// Bucket Request Factories
// ============================================

// CreateBucketRequestOption modifies a CreateBucketRequest
type CreateBucketRequestOption func(*pb.CreateBucketRequest)

// MakeCreateBucketRequest creates a CreateBucketRequest with defaults
func (f *TestDataFactory) MakeCreateBucketRequest(opts ...CreateBucketRequestOption) *pb.CreateBucketRequest {
	req := &pb.CreateBucketRequest{
		BucketName:     "test-bucket",
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		Region:         "us-east-1",
		ObjectLocking:  false,
		Tags:           map[string]string{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithBucketName sets the bucket name
func WithBucketName(name string) CreateBucketRequestOption {
	return func(req *pb.CreateBucketRequest) {
		req.BucketName = name
	}
}

// WithBucketUser sets user and org IDs
func WithBucketUser(userID, orgID string) CreateBucketRequestOption {
	return func(req *pb.CreateBucketRequest) {
		req.UserId = userID
		req.OrganizationId = orgID
	}
}

// WithBucketTags sets the bucket tags
func WithBucketTags(tags map[string]string) CreateBucketRequestOption {
	return func(req *pb.CreateBucketRequest) {
		req.Tags = tags
	}
}

// ListBucketsRequestOption modifies a ListBucketsRequest
type ListBucketsRequestOption func(*pb.ListBucketsRequest)

// MakeListBucketsRequest creates a ListBucketsRequest with defaults
func (f *TestDataFactory) MakeListBucketsRequest(opts ...ListBucketsRequestOption) *pb.ListBucketsRequest {
	req := &pb.ListBucketsRequest{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// ============================================
// GetObject Request Factories
// ============================================

// GetObjectRequestOption modifies a GetObjectRequest
type GetObjectRequestOption func(*pb.GetObjectRequest)

// MakeGetObjectRequest creates a GetObjectRequest with defaults
func (f *TestDataFactory) MakeGetObjectRequest(opts ...GetObjectRequestOption) *pb.GetObjectRequest {
	req := &pb.GetObjectRequest{
		BucketName: "test-bucket",
		ObjectKey:  "test-object.txt",
		UserId:     "test-user-001",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithGetObjectKey sets the object key
func WithGetObjectKey(key string) GetObjectRequestOption {
	return func(req *pb.GetObjectRequest) {
		req.ObjectKey = key
	}
}

// WithGetObjectBucket sets the bucket name
func WithGetObjectBucket(bucket string) GetObjectRequestOption {
	return func(req *pb.GetObjectRequest) {
		req.BucketName = bucket
	}
}

// ============================================
// DeleteObject Request Factories
// ============================================

// DeleteObjectRequestOption modifies a DeleteObjectRequest
type DeleteObjectRequestOption func(*pb.DeleteObjectRequest)

// MakeDeleteObjectRequest creates a DeleteObjectRequest with defaults
func (f *TestDataFactory) MakeDeleteObjectRequest(opts ...DeleteObjectRequestOption) *pb.DeleteObjectRequest {
	req := &pb.DeleteObjectRequest{
		BucketName: "test-bucket",
		ObjectKey:  "test-object.txt",
		UserId:     "test-user-001",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithDeleteObjectKey sets the object key
func WithDeleteObjectKey(key string) DeleteObjectRequestOption {
	return func(req *pb.DeleteObjectRequest) {
		req.ObjectKey = key
	}
}

// ============================================
// Presigned URL Request Factories
// ============================================

// GetPresignedURLRequestOption modifies a GetPresignedURLRequest
type GetPresignedURLRequestOption func(*pb.GetPresignedURLRequest)

// MakeGetPresignedURLRequest creates a GetPresignedURLRequest with defaults
func (f *TestDataFactory) MakeGetPresignedURLRequest(opts ...GetPresignedURLRequestOption) *pb.GetPresignedURLRequest {
	req := &pb.GetPresignedURLRequest{
		BucketName:    "test-bucket",
		ObjectKey:     "test-object.txt",
		UserId:        "test-user-001",
		ExpirySeconds: 900, // 15 minutes
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithPresignedExpiry sets the expiry in seconds
func WithPresignedExpiry(seconds int32) GetPresignedURLRequestOption {
	return func(req *pb.GetPresignedURLRequest) {
		req.ExpirySeconds = seconds
	}
}

// WithPresignedKey sets the object key
func WithPresignedKey(key string) GetPresignedURLRequestOption {
	return func(req *pb.GetPresignedURLRequest) {
		req.ObjectKey = key
	}
}

// WithPresignedBucket sets the bucket name
func WithPresignedBucket(bucket string) GetPresignedURLRequestOption {
	return func(req *pb.GetPresignedURLRequest) {
		req.BucketName = bucket
	}
}

// ============================================
// List Objects Request Factory
// ============================================

// ListObjectsRequestOption modifies a ListObjectsRequest
type ListObjectsRequestOption func(*pb.ListObjectsRequest)

// MakeListObjectsRequest creates a ListObjectsRequest with defaults
func (f *TestDataFactory) MakeListObjectsRequest(opts ...ListObjectsRequestOption) *pb.ListObjectsRequest {
	req := &pb.ListObjectsRequest{
		BucketName: "test-bucket",
		UserId:     "test-user-001",
		Prefix:     "",
		MaxKeys:    1000,
		Recursive:  true,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithListPrefix sets the prefix filter
func WithListPrefix(prefix string) ListObjectsRequestOption {
	return func(req *pb.ListObjectsRequest) {
		req.Prefix = prefix
	}
}

// WithMaxKeys sets the max keys per page
func WithMaxKeys(maxKeys int32) ListObjectsRequestOption {
	return func(req *pb.ListObjectsRequest) {
		req.MaxKeys = maxKeys
	}
}

// WithListBucket sets the bucket name
func WithListBucket(bucket string) ListObjectsRequestOption {
	return func(req *pb.ListObjectsRequest) {
		req.BucketName = bucket
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

// ValidBucketCreate returns a valid bucket creation request
func (s *Scenarios) ValidBucketCreate() *pb.CreateBucketRequest {
	return s.factory.MakeCreateBucketRequest()
}

// InvalidBucketName returns bucket with invalid name (EC-001)
func (s *Scenarios) InvalidBucketName() *pb.CreateBucketRequest {
	return s.factory.MakeCreateBucketRequest(WithBucketName("AB")) // Too short, uppercase
}

// PresignedUploadURL returns a presigned PUT URL request
func (s *Scenarios) PresignedUploadURL(key string) *pb.GetPresignedURLRequest {
	return s.factory.MakeGetPresignedURLRequest(
		WithPresignedKey(key),
	)
}

// PresignedDownloadURL returns a presigned GET URL request
func (s *Scenarios) PresignedDownloadURL(key string) *pb.GetPresignedURLRequest {
	return s.factory.MakeGetPresignedURLRequest(
		WithPresignedKey(key),
	)
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.CreateBucketRequest) {
	tenant1Req = s.factory.MakeCreateBucketRequest(
		WithBucketUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakeCreateBucketRequest(
		WithBucketUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedIsolatedBucket returns the expected isolated bucket name
func ExpectedIsolatedBucket(orgID, bucket string) string {
	return fmt.Sprintf("%s-%s", orgID, bucket)
}

// DefaultIsolatedBucket returns isolated bucket for default test org
func DefaultIsolatedBucket(bucket string) string {
	return ExpectedIsolatedBucket("test-org-001", bucket)
}

// ExpectedObjectPath returns the full object path
func ExpectedObjectPath(orgID, bucket, key string) string {
	return fmt.Sprintf("%s-%s/%s", orgID, bucket, key)
}
