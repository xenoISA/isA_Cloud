// Package postgres_contract provides test data factories and fixtures
// for PostgreSQL service contract testing.
package postgres_contract

import (
	"fmt"
	"time"

	"google.golang.org/protobuf/types/known/structpb"

	common "github.com/isa-cloud/isa_cloud/api/proto/common"
	pb "github.com/isa-cloud/isa_cloud/api/proto/postgres"
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

func (f *TestDataFactory) makeMetadata() *common.RequestMetadata {
	return &common.RequestMetadata{
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		RequestId:      f.nextID(),
	}
}

// ============================================
// QueryRequest Factory
// ============================================

// QueryRequestOption modifies a QueryRequest
type QueryRequestOption func(*pb.QueryRequest)

// MakeQueryRequest creates a QueryRequest with sensible defaults
func (f *TestDataFactory) MakeQueryRequest(opts ...QueryRequestOption) *pb.QueryRequest {
	req := &pb.QueryRequest{
		Metadata: f.makeMetadata(),
		Sql:      "SELECT * FROM users WHERE id = $1",
		Params:   []*structpb.Value{},
		Schema:   "public",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithSQL sets the SQL query
func WithSQL(sql string) QueryRequestOption {
	return func(req *pb.QueryRequest) {
		req.Sql = sql
	}
}

// WithParams sets the query parameters
func WithParams(params ...*structpb.Value) QueryRequestOption {
	return func(req *pb.QueryRequest) {
		req.Params = params
	}
}

// WithSchema sets the database schema
func WithSchema(schema string) QueryRequestOption {
	return func(req *pb.QueryRequest) {
		req.Schema = schema
	}
}

// WithQueryUser sets user_id and organization_id in metadata
func WithQueryUser(userID, orgID string) QueryRequestOption {
	return func(req *pb.QueryRequest) {
		req.Metadata.UserId = userID
		req.Metadata.OrganizationId = orgID
	}
}

// ============================================
// ExecuteRequest Factory
// ============================================

// ExecuteRequestOption modifies an ExecuteRequest
type ExecuteRequestOption func(*pb.ExecuteRequest)

// MakeExecuteRequest creates an ExecuteRequest with sensible defaults
func (f *TestDataFactory) MakeExecuteRequest(opts ...ExecuteRequestOption) *pb.ExecuteRequest {
	req := &pb.ExecuteRequest{
		Metadata: f.makeMetadata(),
		Sql:      "INSERT INTO users (name, email) VALUES ($1, $2)",
		Params:   []*structpb.Value{},
		Schema:   "public",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithExecuteSQL sets the SQL statement
func WithExecuteSQL(sql string) ExecuteRequestOption {
	return func(req *pb.ExecuteRequest) {
		req.Sql = sql
	}
}

// WithExecuteParams sets the query parameters
func WithExecuteParams(params ...*structpb.Value) ExecuteRequestOption {
	return func(req *pb.ExecuteRequest) {
		req.Params = params
	}
}

// ============================================
// Transaction Request Factories
// ============================================

// BeginTransactionRequestOption modifies a BeginTransactionRequest
type BeginTransactionRequestOption func(*pb.BeginTransactionRequest)

// MakeBeginTransactionRequest creates a BeginTransactionRequest with defaults
func (f *TestDataFactory) MakeBeginTransactionRequest(opts ...BeginTransactionRequestOption) *pb.BeginTransactionRequest {
	req := &pb.BeginTransactionRequest{
		Metadata:       f.makeMetadata(),
		IsolationLevel: "READ COMMITTED",
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithIsolationLevel sets the isolation level
func WithIsolationLevel(level string) BeginTransactionRequestOption {
	return func(req *pb.BeginTransactionRequest) {
		req.IsolationLevel = level
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

// SimpleSelect returns a basic SELECT query
func (s *Scenarios) SimpleSelect() *pb.QueryRequest {
	return s.factory.MakeQueryRequest(
		WithSQL("SELECT id, name FROM users WHERE id = $1"),
	)
}

// InsertUser returns an INSERT statement
func (s *Scenarios) InsertUser() *pb.ExecuteRequest {
	return s.factory.MakeExecuteRequest(
		WithExecuteSQL("INSERT INTO users (name, email) VALUES ($1, $2)"),
	)
}

// UpdateUser returns an UPDATE statement
func (s *Scenarios) UpdateUser() *pb.ExecuteRequest {
	return s.factory.MakeExecuteRequest(
		WithExecuteSQL("UPDATE users SET name = $1 WHERE id = $2"),
	)
}

// DeleteUser returns a DELETE statement
func (s *Scenarios) DeleteUser() *pb.ExecuteRequest {
	return s.factory.MakeExecuteRequest(
		WithExecuteSQL("DELETE FROM users WHERE id = $1"),
	)
}

// EmptyQuery returns a request with empty query (EC-001)
func (s *Scenarios) EmptyQuery() *pb.QueryRequest {
	return s.factory.MakeQueryRequest(WithSQL(""))
}

// SyntaxErrorQuery returns a malformed SQL query (EC-002)
func (s *Scenarios) SyntaxErrorQuery() *pb.QueryRequest {
	return s.factory.MakeQueryRequest(WithSQL("SELCT * FORM users"))
}

// NonExistentTable returns a query on non-existent table (EC-005)
func (s *Scenarios) NonExistentTable() *pb.QueryRequest {
	return s.factory.MakeQueryRequest(
		WithSQL("SELECT * FROM non_existent_table_xyz"),
	)
}

// LongRunningQuery returns a query that will timeout
func (s *Scenarios) LongRunningQuery() *pb.QueryRequest {
	return s.factory.MakeQueryRequest(
		WithSQL("SELECT pg_sleep(60)"),
	)
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.QueryRequest) {
	tenant1Req = s.factory.MakeQueryRequest(
		WithQueryUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakeQueryRequest(
		WithQueryUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedIsolatedSchema returns the expected isolated schema format
func ExpectedIsolatedSchema(orgID, userID string) string {
	return fmt.Sprintf("%s_%s", orgID, userID)
}

// ExpectedResultFormat returns expected JSON result structure
type ExpectedResultFormat struct {
	Rows     []map[string]interface{} `json:"rows"`
	RowCount int                      `json:"row_count"`
	Columns  []string                 `json:"columns"`
}
