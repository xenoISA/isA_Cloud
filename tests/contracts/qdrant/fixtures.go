// Package qdrant_contract provides test data factories and fixtures
// for Qdrant service contract testing.
package qdrant_contract

import (
	"fmt"
	"math/rand"
	"time"

	"google.golang.org/protobuf/types/known/structpb"

	common "github.com/isa-cloud/isa_cloud/api/proto/common"
	pb "github.com/isa-cloud/isa_cloud/api/proto/qdrant"
)

// ============================================
// Test Data Factory
// ============================================

// TestDataFactory creates test data with sensible defaults
type TestDataFactory struct {
	counter int
	rng     *rand.Rand
}

// NewTestDataFactory creates a new factory instance
func NewTestDataFactory() *TestDataFactory {
	return &TestDataFactory{
		rng: rand.New(rand.NewSource(time.Now().UnixNano())),
	}
}

func (f *TestDataFactory) nextID() string {
	f.counter++
	return fmt.Sprintf("test-%d-%d", time.Now().UnixNano(), f.counter)
}

func (f *TestDataFactory) makeMetadata() *common.RequestMetadata {
	return &common.RequestMetadata{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		RequestId:      f.nextID(),
	}
}

// GenerateVector creates a random vector of specified dimension
func (f *TestDataFactory) GenerateVector(dimension int) []float32 {
	vec := make([]float32, dimension)
	for i := range vec {
		vec[i] = f.rng.Float32()*2 - 1 // Range -1 to 1
	}
	return vec
}

// ============================================
// Collection Request Factories
// ============================================

// CreateCollectionRequestOption modifies a CreateCollectionRequest
type CreateCollectionRequestOption func(*pb.CreateCollectionRequest)

// MakeCreateCollectionRequest creates a CreateCollectionRequest with defaults
func (f *TestDataFactory) MakeCreateCollectionRequest(opts ...CreateCollectionRequestOption) *pb.CreateCollectionRequest {
	req := &pb.CreateCollectionRequest{
		Metadata:       f.makeMetadata(),
		CollectionName: "test-collection",
		VectorsConfig: &pb.CreateCollectionRequest_VectorParams{
			VectorParams: &pb.VectorParams{
				Size:     384,
				Distance: pb.Distance_DISTANCE_COSINE,
			},
		},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithCollectionName sets the collection name
func WithCollectionName(name string) CreateCollectionRequestOption {
	return func(req *pb.CreateCollectionRequest) {
		req.CollectionName = name
	}
}

// WithVectorSize sets the vector dimension
func WithVectorSize(size uint64) CreateCollectionRequestOption {
	return func(req *pb.CreateCollectionRequest) {
		if vp, ok := req.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			vp.VectorParams.Size = size
		}
	}
}

// WithDistance sets the distance metric
func WithDistance(distance pb.Distance) CreateCollectionRequestOption {
	return func(req *pb.CreateCollectionRequest) {
		if vp, ok := req.VectorsConfig.(*pb.CreateCollectionRequest_VectorParams); ok {
			vp.VectorParams.Distance = distance
		}
	}
}

// WithCollectionUser sets user and org IDs in metadata
func WithCollectionUser(userID, orgID string) CreateCollectionRequestOption {
	return func(req *pb.CreateCollectionRequest) {
		req.Metadata.UserId = userID
		req.Metadata.OrganizationId = orgID
	}
}

// ============================================
// Upsert Request Factories
// ============================================

// UpsertPointsRequestOption modifies an UpsertPointsRequest
type UpsertPointsRequestOption func(*pb.UpsertPointsRequest)

// MakeUpsertPointsRequest creates an UpsertPointsRequest with defaults
func (f *TestDataFactory) MakeUpsertPointsRequest(opts ...UpsertPointsRequestOption) *pb.UpsertPointsRequest {
	wait := true
	payload, _ := structpb.NewStruct(map[string]interface{}{
		"title": "Test Document",
	})
	req := &pb.UpsertPointsRequest{
		Metadata:       f.makeMetadata(),
		CollectionName: "test-collection",
		Points: []*pb.Point{
			{
				Id: &pb.Point_StrId{StrId: "point-001"},
				Vectors: &pb.Point_Vector{
					Vector: &pb.Vector{
						Data: f.GenerateVector(384),
					},
				},
				Payload: payload,
			},
		},
		Wait: &wait,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithPoints sets the points to upsert
func WithPoints(points []*pb.Point) UpsertPointsRequestOption {
	return func(req *pb.UpsertPointsRequest) {
		req.Points = points
	}
}

// WithUpsertCollection sets the collection name
func WithUpsertCollection(name string) UpsertPointsRequestOption {
	return func(req *pb.UpsertPointsRequest) {
		req.CollectionName = name
	}
}

// MakePoint creates a single point with string ID
func (f *TestDataFactory) MakePoint(id string, dimension int, payloadMap map[string]interface{}) *pb.Point {
	payload, _ := structpb.NewStruct(payloadMap)
	return &pb.Point{
		Id: &pb.Point_StrId{StrId: id},
		Vectors: &pb.Point_Vector{
			Vector: &pb.Vector{
				Data: f.GenerateVector(dimension),
			},
		},
		Payload: payload,
	}
}

// MakePointWithVector creates a point with specific vector
func (f *TestDataFactory) MakePointWithVector(id string, vector []float32, payloadMap map[string]interface{}) *pb.Point {
	payload, _ := structpb.NewStruct(payloadMap)
	return &pb.Point{
		Id: &pb.Point_StrId{StrId: id},
		Vectors: &pb.Point_Vector{
			Vector: &pb.Vector{
				Data: vector,
			},
		},
		Payload: payload,
	}
}

// ============================================
// Search Request Factories
// ============================================

// SearchRequestOption modifies a SearchRequest
type SearchRequestOption func(*pb.SearchRequest)

// MakeSearchRequest creates a SearchRequest with defaults
func (f *TestDataFactory) MakeSearchRequest(opts ...SearchRequestOption) *pb.SearchRequest {
	withPayload := true
	withVectors := false
	req := &pb.SearchRequest{
		Metadata:       f.makeMetadata(),
		CollectionName: "test-collection",
		Vector: &pb.Vector{
			Data: f.GenerateVector(384),
		},
		Limit:       10,
		WithPayload: &withPayload,
		WithVectors: &withVectors,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithQueryVector sets the query vector
func WithQueryVector(vector []float32) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.Vector = &pb.Vector{Data: vector}
	}
}

// WithLimit sets the number of results
func WithLimit(limit uint64) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.Limit = limit
	}
}

// WithScoreThreshold sets minimum similarity score
func WithScoreThreshold(threshold float32) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.ScoreThreshold = &threshold
	}
}

// WithFilter sets the payload filter
func WithFilter(filter *pb.Filter) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.Filter = filter
	}
}

// WithSearchCollection sets the collection name
func WithSearchCollection(name string) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.CollectionName = name
	}
}

// WithPayload enables/disables payload in results
func WithPayload(include bool) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.WithPayload = &include
	}
}

// WithSearchUser sets user and org IDs in metadata
func WithSearchUser(userID, orgID string) SearchRequestOption {
	return func(req *pb.SearchRequest) {
		req.Metadata.UserId = userID
		req.Metadata.OrganizationId = orgID
	}
}

// ============================================
// Delete Request Factories
// ============================================

// DeletePointsRequestOption modifies a DeletePointsRequest
type DeletePointsRequestOption func(*pb.DeletePointsRequest)

// MakeDeletePointsRequest creates a DeletePointsRequest with defaults
func (f *TestDataFactory) MakeDeletePointsRequest(opts ...DeletePointsRequestOption) *pb.DeletePointsRequest {
	wait := true
	req := &pb.DeletePointsRequest{
		Metadata:       f.makeMetadata(),
		CollectionName: "test-collection",
		Selector: &pb.DeletePointsRequest_Ids{
			Ids: &pb.PointIdList{
				Ids: []*pb.PointId{
					{Id: &pb.PointId_Str{Str: "point-001"}},
				},
			},
		},
		Wait: &wait,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithDeleteIds sets the IDs to delete
func WithDeleteIds(ids ...string) DeletePointsRequestOption {
	return func(req *pb.DeletePointsRequest) {
		pointIds := make([]*pb.PointId, len(ids))
		for i, id := range ids {
			pointIds[i] = &pb.PointId{Id: &pb.PointId_Str{Str: id}}
		}
		req.Selector = &pb.DeletePointsRequest_Ids{
			Ids: &pb.PointIdList{Ids: pointIds},
		}
	}
}

// WithDeleteCollection sets the collection name
func WithDeleteCollection(name string) DeletePointsRequestOption {
	return func(req *pb.DeletePointsRequest) {
		req.CollectionName = name
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

// ValidCollectionCreate returns a valid collection creation request
func (s *Scenarios) ValidCollectionCreate() *pb.CreateCollectionRequest {
	return s.factory.MakeCreateCollectionRequest()
}

// OpenAIEmbeddingCollection returns a collection for OpenAI embeddings
func (s *Scenarios) OpenAIEmbeddingCollection(name string) *pb.CreateCollectionRequest {
	return s.factory.MakeCreateCollectionRequest(
		WithCollectionName(name),
		WithVectorSize(1536), // OpenAI ada-002
		WithDistance(pb.Distance_DISTANCE_COSINE),
	)
}

// DocumentEmbeddings returns upsert request with document embeddings
func (s *Scenarios) DocumentEmbeddings(docs []struct {
	ID    string
	Title string
}) *pb.UpsertPointsRequest {
	points := make([]*pb.Point, len(docs))
	for i, doc := range docs {
		points[i] = s.factory.MakePoint(doc.ID, 384, map[string]interface{}{
			"title": doc.Title,
		})
	}
	return s.factory.MakeUpsertPointsRequest(WithPoints(points))
}

// SemanticSearch returns a semantic search request
func (s *Scenarios) SemanticSearch(queryVector []float32, limit uint64) *pb.SearchRequest {
	return s.factory.MakeSearchRequest(
		WithQueryVector(queryVector),
		WithLimit(limit),
	)
}

// FilteredSearch returns a search with payload filter
func (s *Scenarios) FilteredSearch(filter *pb.Filter) *pb.SearchRequest {
	return s.factory.MakeSearchRequest(WithFilter(filter))
}

// WrongDimensionVector returns upsert with wrong dimension (EC-001)
func (s *Scenarios) WrongDimensionVector() *pb.UpsertPointsRequest {
	wrongDimPoints := []*pb.Point{
		s.factory.MakePoint("wrong-dim", 768, map[string]interface{}{}), // Wrong dimension
	}
	return s.factory.MakeUpsertPointsRequest(WithPoints(wrongDimPoints))
}

// EmptyQueryVector returns search with empty vector (EC-004)
func (s *Scenarios) EmptyQueryVector() *pb.SearchRequest {
	return s.factory.MakeSearchRequest(WithQueryVector([]float32{}))
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.SearchRequest) {
	tenant1Req = s.factory.MakeSearchRequest(
		WithSearchUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakeSearchRequest(
		WithSearchUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedIsolatedCollection returns the expected isolated collection name
func ExpectedIsolatedCollection(orgID, collection string) string {
	return fmt.Sprintf("%s_%s", orgID, collection)
}

// DefaultIsolatedCollection returns isolated collection for default test org
func DefaultIsolatedCollection(collection string) string {
	return ExpectedIsolatedCollection("test-org-001", collection)
}

// NormalizeVector normalizes a vector to unit length (for cosine similarity)
func NormalizeVector(vec []float32) []float32 {
	var sum float32
	for _, v := range vec {
		sum += v * v
	}
	magnitude := float32(1.0)
	if sum > 0 {
		magnitude = float32(1.0 / float64(sum))
	}
	result := make([]float32, len(vec))
	for i, v := range vec {
		result[i] = v * magnitude
	}
	return result
}
