// Package neo4j_contract provides test data factories and fixtures
// for Neo4j service contract testing.
package neo4j_contract

import (
	"fmt"
	"time"

	"google.golang.org/protobuf/types/known/structpb"

	common "github.com/isa-cloud/isa_cloud/api/proto/common"
	pb "github.com/isa-cloud/isa_cloud/api/proto/neo4j"
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
	return fmt.Sprintf("node-%d-%d", time.Now().UnixNano(), f.counter)
}

func (f *TestDataFactory) makeMetadata() *common.RequestMetadata {
	return &common.RequestMetadata{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		RequestId:      f.nextID(),
	}
}

// ============================================
// Node Request Factories
// ============================================

// CreateNodeRequestOption modifies a CreateNodeRequest
type CreateNodeRequestOption func(*pb.CreateNodeRequest)

// MakeCreateNodeRequest creates a CreateNodeRequest with defaults
func (f *TestDataFactory) MakeCreateNodeRequest(opts ...CreateNodeRequestOption) *pb.CreateNodeRequest {
	props, _ := structpb.NewStruct(map[string]interface{}{
		"id":    f.nextID(),
		"name":  "Test Person",
		"email": "test@example.com",
	})
	req := &pb.CreateNodeRequest{
		Metadata:   f.makeMetadata(),
		Labels:     []string{"Person"},
		Properties: props,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithLabels sets the node labels
func WithLabels(labels ...string) CreateNodeRequestOption {
	return func(req *pb.CreateNodeRequest) {
		req.Labels = labels
	}
}

// WithProperties sets the node properties
func WithProperties(props map[string]interface{}) CreateNodeRequestOption {
	return func(req *pb.CreateNodeRequest) {
		s, _ := structpb.NewStruct(props)
		req.Properties = s
	}
}

// WithNodeUser sets user and org IDs in metadata
func WithNodeUser(userID, orgID string) CreateNodeRequestOption {
	return func(req *pb.CreateNodeRequest) {
		req.Metadata.UserId = userID
		req.Metadata.OrganizationId = orgID
	}
}

// ============================================
// Relationship Request Factories
// ============================================

// CreateRelationshipRequestOption modifies a CreateRelationshipRequest
type CreateRelationshipRequestOption func(*pb.CreateRelationshipRequest)

// MakeCreateRelationshipRequest creates a relationship request
func (f *TestDataFactory) MakeCreateRelationshipRequest(fromID, toID int64, relType string, opts ...CreateRelationshipRequestOption) *pb.CreateRelationshipRequest {
	props, _ := structpb.NewStruct(map[string]interface{}{
		"since": time.Now().Format("2006-01-02"),
	})
	req := &pb.CreateRelationshipRequest{
		Metadata:    f.makeMetadata(),
		StartNodeId: fromID,
		EndNodeId:   toID,
		Type:        relType,
		Properties:  props,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithRelationshipProperties sets relationship properties
func WithRelationshipProperties(props map[string]interface{}) CreateRelationshipRequestOption {
	return func(req *pb.CreateRelationshipRequest) {
		s, _ := structpb.NewStruct(props)
		req.Properties = s
	}
}

// ============================================
// Cypher Query Request Factories
// ============================================

// RunCypherRequestOption modifies a RunCypherRequest
type RunCypherRequestOption func(*pb.RunCypherRequest)

// MakeRunCypherRequest creates a RunCypherRequest with defaults
func (f *TestDataFactory) MakeRunCypherRequest(opts ...RunCypherRequestOption) *pb.RunCypherRequest {
	req := &pb.RunCypherRequest{
		Metadata:   f.makeMetadata(),
		Cypher:     "MATCH (n) RETURN n LIMIT 10",
		Parameters: map[string]*structpb.Value{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithCypher sets the Cypher query
func WithCypher(cypher string) RunCypherRequestOption {
	return func(req *pb.RunCypherRequest) {
		req.Cypher = cypher
	}
}

// WithCypherParams sets query parameters
func WithCypherParams(params map[string]interface{}) RunCypherRequestOption {
	return func(req *pb.RunCypherRequest) {
		paramValues := make(map[string]*structpb.Value)
		for k, v := range params {
			val, _ := structpb.NewValue(v)
			paramValues[k] = val
		}
		req.Parameters = paramValues
	}
}

// WithDatabase sets the database name
func WithDatabase(database string) RunCypherRequestOption {
	return func(req *pb.RunCypherRequest) {
		req.Database = &database
	}
}

// WithCypherUser sets user and org IDs in metadata
func WithCypherUser(userID, orgID string) RunCypherRequestOption {
	return func(req *pb.RunCypherRequest) {
		req.Metadata.UserId = userID
		req.Metadata.OrganizationId = orgID
	}
}

// ============================================
// Shortest Path Request Factories
// ============================================

// GetShortestPathRequestOption modifies a GetShortestPathRequest
type GetShortestPathRequestOption func(*pb.GetShortestPathRequest)

// MakeGetShortestPathRequest creates a GetShortestPathRequest with defaults
func (f *TestDataFactory) MakeGetShortestPathRequest(fromID, toID int64, opts ...GetShortestPathRequestOption) *pb.GetShortestPathRequest {
	maxDepth := int32(5)
	req := &pb.GetShortestPathRequest{
		Metadata:    f.makeMetadata(),
		StartNodeId: fromID,
		EndNodeId:   toID,
		MaxDepth:    &maxDepth,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithMaxDepth sets the max depth
func WithMaxDepth(depth int32) GetShortestPathRequestOption {
	return func(req *pb.GetShortestPathRequest) {
		req.MaxDepth = &depth
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

// CreatePerson returns a request to create a Person node
func (s *Scenarios) CreatePerson(name, email string) *pb.CreateNodeRequest {
	return s.factory.MakeCreateNodeRequest(
		WithLabels("Person"),
		WithProperties(map[string]interface{}{
			"id":    s.factory.nextID(),
			"name":  name,
			"email": email,
		}),
	)
}

// CreateCompany returns a request to create a Company node
func (s *Scenarios) CreateCompany(name string) *pb.CreateNodeRequest {
	return s.factory.MakeCreateNodeRequest(
		WithLabels("Company"),
		WithProperties(map[string]interface{}{
			"id":   s.factory.nextID(),
			"name": name,
		}),
	)
}

// KnowsRelationship returns a KNOWS relationship request
func (s *Scenarios) KnowsRelationship(fromID, toID int64) *pb.CreateRelationshipRequest {
	return s.factory.MakeCreateRelationshipRequest(
		fromID, toID, "KNOWS",
		WithRelationshipProperties(map[string]interface{}{
			"since": time.Now().Format("2006-01-02"),
		}),
	)
}

// WorksAtRelationship returns a WORKS_AT relationship request
func (s *Scenarios) WorksAtRelationship(personID, companyID int64) *pb.CreateRelationshipRequest {
	return s.factory.MakeCreateRelationshipRequest(
		personID, companyID, "WORKS_AT",
		WithRelationshipProperties(map[string]interface{}{
			"role": "Employee",
		}),
	)
}

// FindPersonByName returns a query to find person by name
func (s *Scenarios) FindPersonByName(name string) *pb.RunCypherRequest {
	return s.factory.MakeRunCypherRequest(
		WithCypher("MATCH (p:Person {name: $name}) RETURN p"),
		WithCypherParams(map[string]interface{}{"name": name}),
	)
}

// FriendsOfFriends returns a 2-hop traversal query
func (s *Scenarios) FriendsOfFriends(personID string) *pb.RunCypherRequest {
	return s.factory.MakeRunCypherRequest(
		WithCypher("MATCH (a:Person {id: $id})-[:KNOWS*2]->(b:Person) RETURN DISTINCT b"),
		WithCypherParams(map[string]interface{}{"id": personID}),
	)
}

// ShortestPath returns a shortest path query
func (s *Scenarios) ShortestPath(fromID, toID string) *pb.RunCypherRequest {
	return s.factory.MakeRunCypherRequest(
		WithCypher("MATCH p = shortestPath((a:Person {id: $from})-[*]-(b:Person {id: $to})) RETURN p"),
		WithCypherParams(map[string]interface{}{"from": fromID, "to": toID}),
	)
}

// EmptyQuery returns query with empty string (EC-001)
func (s *Scenarios) EmptyQuery() *pb.RunCypherRequest {
	return s.factory.MakeRunCypherRequest(WithCypher(""))
}

// SyntaxErrorQuery returns malformed Cypher (EC-002)
func (s *Scenarios) SyntaxErrorQuery() *pb.RunCypherRequest {
	return s.factory.MakeRunCypherRequest(WithCypher("MTCH (n) RETRUN n"))
}

// InvalidLabel returns node with invalid label (EC-008)
func (s *Scenarios) InvalidLabel() *pb.CreateNodeRequest {
	return s.factory.MakeCreateNodeRequest(
		WithLabels("Invalid Label With Spaces"),
	)
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.RunCypherRequest) {
	tenant1Req = s.factory.MakeRunCypherRequest(
		WithCypherUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakeRunCypherRequest(
		WithCypherUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedOrgLabel returns the expected org isolation label
func ExpectedOrgLabel(orgID string) string {
	return fmt.Sprintf("_org_%s", orgID)
}

// DefaultOrgLabel returns org label for default test org
func DefaultOrgLabel() string {
	return ExpectedOrgLabel("test-org-001")
}

// CypherWithOrgFilter returns query with org filter injected
func CypherWithOrgFilter(query, orgID string) string {
	// This is a simplified example - actual implementation would parse Cypher
	return fmt.Sprintf("// Org: %s\n%s", orgID, query)
}
