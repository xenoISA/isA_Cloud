// Package duckdb_contract provides test data factories and fixtures
// for DuckDB service contract testing.
package duckdb_contract

import (
	"fmt"
	"time"

	pb "github.com/isa-cloud/isa_cloud/api/proto/duckdb"
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
// ExecuteQueryRequest Factory
// ============================================

// ExecuteQueryRequestOption modifies an ExecuteQueryRequest
type ExecuteQueryRequestOption func(*pb.ExecuteQueryRequest)

// MakeExecuteQueryRequest creates an ExecuteQueryRequest with sensible defaults
func (f *TestDataFactory) MakeExecuteQueryRequest(opts ...ExecuteQueryRequestOption) *pb.ExecuteQueryRequest {
	req := &pb.ExecuteQueryRequest{
		DatabaseId:     "test-db-001",
		UserId:         "test-user-001",
		Query:          "SELECT 1 as value",
		Parameters:     map[string]*pb.Value{},
		MaxRows:        10000,
		TimeoutSeconds: 30,
		Explain:        false,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithQuery sets the SQL query
func WithQuery(query string) ExecuteQueryRequestOption {
	return func(req *pb.ExecuteQueryRequest) {
		req.Query = query
	}
}

// WithDatabaseID sets the database ID
func WithDatabaseID(dbID string) ExecuteQueryRequestOption {
	return func(req *pb.ExecuteQueryRequest) {
		req.DatabaseId = dbID
	}
}

// WithQueryUser sets the user ID
func WithQueryUser(userID string) ExecuteQueryRequestOption {
	return func(req *pb.ExecuteQueryRequest) {
		req.UserId = userID
	}
}

// WithMaxRows sets the max rows
func WithMaxRows(maxRows int32) ExecuteQueryRequestOption {
	return func(req *pb.ExecuteQueryRequest) {
		req.MaxRows = maxRows
	}
}

// WithTimeout sets the timeout
func WithTimeout(seconds int32) ExecuteQueryRequestOption {
	return func(req *pb.ExecuteQueryRequest) {
		req.TimeoutSeconds = seconds
	}
}

// WithExplain enables query plan explanation
func WithExplain(explain bool) ExecuteQueryRequestOption {
	return func(req *pb.ExecuteQueryRequest) {
		req.Explain = explain
	}
}

// ============================================
// ExecuteStatementRequest Factory
// ============================================

// ExecuteStatementRequestOption modifies an ExecuteStatementRequest
type ExecuteStatementRequestOption func(*pb.ExecuteStatementRequest)

// MakeExecuteStatementRequest creates an ExecuteStatementRequest with sensible defaults
func (f *TestDataFactory) MakeExecuteStatementRequest(opts ...ExecuteStatementRequestOption) *pb.ExecuteStatementRequest {
	req := &pb.ExecuteStatementRequest{
		DatabaseId: "test-db-001",
		UserId:     "test-user-001",
		Statement:  "CREATE TABLE test (id INTEGER, name VARCHAR)",
		Parameters: map[string]*pb.Value{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithStatement sets the SQL statement
func WithStatement(stmt string) ExecuteStatementRequestOption {
	return func(req *pb.ExecuteStatementRequest) {
		req.Statement = stmt
	}
}

// ============================================
// ImportFromMinIORequest Factory
// ============================================

// ImportFromMinIORequestOption modifies an ImportFromMinIORequest
type ImportFromMinIORequestOption func(*pb.ImportFromMinIORequest)

// MakeImportFromMinIORequest creates an ImportFromMinIORequest with sensible defaults
func (f *TestDataFactory) MakeImportFromMinIORequest(opts ...ImportFromMinIORequestOption) *pb.ImportFromMinIORequest {
	req := &pb.ImportFromMinIORequest{
		DatabaseId:  "test-db-001",
		UserId:      "test-user-001",
		TableName:   "imported_data",
		BucketName:  "test-bucket",
		ObjectKey:   "data/test.parquet",
		Format:      "parquet",
		CreateTable: true,
		Truncate:    false,
		Options:     map[string]string{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithImportTable sets the table name
func WithImportTable(table string) ImportFromMinIORequestOption {
	return func(req *pb.ImportFromMinIORequest) {
		req.TableName = table
	}
}

// WithImportBucket sets the bucket name
func WithImportBucket(bucket string) ImportFromMinIORequestOption {
	return func(req *pb.ImportFromMinIORequest) {
		req.BucketName = bucket
	}
}

// WithImportObjectKey sets the object key
func WithImportObjectKey(key string) ImportFromMinIORequestOption {
	return func(req *pb.ImportFromMinIORequest) {
		req.ObjectKey = key
	}
}

// WithImportFormat sets the format
func WithImportFormat(format string) ImportFromMinIORequestOption {
	return func(req *pb.ImportFromMinIORequest) {
		req.Format = format
	}
}

// ============================================
// ExportToMinIORequest Factory
// ============================================

// ExportToMinIORequestOption modifies an ExportToMinIORequest
type ExportToMinIORequestOption func(*pb.ExportToMinIORequest)

// MakeExportToMinIORequest creates an ExportToMinIORequest with sensible defaults
func (f *TestDataFactory) MakeExportToMinIORequest(opts ...ExportToMinIORequestOption) *pb.ExportToMinIORequest {
	req := &pb.ExportToMinIORequest{
		DatabaseId: "test-db-001",
		UserId:     "test-user-001",
		Query:      "SELECT * FROM test_table",
		BucketName: "test-bucket",
		ObjectKey:  "exports/test_export.parquet",
		Format:     "parquet",
		Options:    map[string]string{},
		Overwrite:  true,
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithExportQuery sets the export query
func WithExportQuery(query string) ExportToMinIORequestOption {
	return func(req *pb.ExportToMinIORequest) {
		req.Query = query
	}
}

// WithExportFormat sets the export format
func WithExportFormat(format string) ExportToMinIORequestOption {
	return func(req *pb.ExportToMinIORequest) {
		req.Format = format
	}
}

// ============================================
// CreateDatabaseRequest Factory
// ============================================

// CreateDatabaseRequestOption modifies a CreateDatabaseRequest
type CreateDatabaseRequestOption func(*pb.CreateDatabaseRequest)

// MakeCreateDatabaseRequest creates a CreateDatabaseRequest with sensible defaults
func (f *TestDataFactory) MakeCreateDatabaseRequest(opts ...CreateDatabaseRequestOption) *pb.CreateDatabaseRequest {
	req := &pb.CreateDatabaseRequest{
		DatabaseName:   "test-database",
		UserId:         "test-user-001",
		OrganizationId: "test-org-001",
		MinioBucket:    "test-bucket",
		Metadata:       map[string]string{},
		Config:         map[string]string{},
	}
	for _, opt := range opts {
		opt(req)
	}
	return req
}

// WithDatabaseName sets the database name
func WithDatabaseName(name string) CreateDatabaseRequestOption {
	return func(req *pb.CreateDatabaseRequest) {
		req.DatabaseName = name
	}
}

// WithDatabaseUser sets the user and org
func WithDatabaseUser(userID, orgID string) CreateDatabaseRequestOption {
	return func(req *pb.CreateDatabaseRequest) {
		req.UserId = userID
		req.OrganizationId = orgID
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
func (s *Scenarios) SimpleSelect() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery("SELECT * FROM sales LIMIT 100"),
	)
}

// AggregationQuery returns a GROUP BY query
func (s *Scenarios) AggregationQuery() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery(`
			SELECT
				product_id,
				SUM(quantity) as total_qty,
				AVG(price) as avg_price,
				COUNT(*) as num_orders
			FROM sales
			GROUP BY product_id
			ORDER BY total_qty DESC
		`),
	)
}

// WindowFunctionQuery returns a window function query
func (s *Scenarios) WindowFunctionQuery() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery(`
			SELECT
				*,
				ROW_NUMBER() OVER (PARTITION BY category ORDER BY revenue DESC) as rank,
				SUM(revenue) OVER (PARTITION BY category) as category_total
			FROM products
		`),
	)
}

// TimeSeriesQuery returns a time-based aggregation
func (s *Scenarios) TimeSeriesQuery(dateColumn string) *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery(fmt.Sprintf(`
			SELECT
				DATE_TRUNC('month', %s) as month,
				COUNT(*) as count,
				SUM(amount) as total
			FROM orders
			GROUP BY 1
			ORDER BY 1
		`, dateColumn)),
	)
}

// PaginatedQuery returns a paginated query
func (s *Scenarios) PaginatedQuery(page, pageSize int32) *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery(fmt.Sprintf("SELECT * FROM large_table ORDER BY id LIMIT %d OFFSET %d",
			pageSize, (page-1)*pageSize)),
		WithMaxRows(pageSize),
	)
}

// ParquetImport returns a Parquet import request
func (s *Scenarios) ParquetImport(tableName, objectKey string) *pb.ImportFromMinIORequest {
	return s.factory.MakeImportFromMinIORequest(
		WithImportTable(tableName),
		WithImportFormat("parquet"),
		WithImportObjectKey(objectKey),
	)
}

// CSVImport returns a CSV import request
func (s *Scenarios) CSVImport(tableName, objectKey string) *pb.ImportFromMinIORequest {
	return s.factory.MakeImportFromMinIORequest(
		WithImportTable(tableName),
		WithImportFormat("csv"),
		WithImportObjectKey(objectKey),
	)
}

// ParquetExport returns a Parquet export request
func (s *Scenarios) ParquetExport(query string) *pb.ExportToMinIORequest {
	return s.factory.MakeExportToMinIORequest(
		WithExportQuery(query),
		WithExportFormat("parquet"),
	)
}

// CSVExport returns a CSV export request
func (s *Scenarios) CSVExport(query string) *pb.ExportToMinIORequest {
	return s.factory.MakeExportToMinIORequest(
		WithExportQuery(query),
		WithExportFormat("csv"),
	)
}

// EmptyQuery returns query with empty string (EC-001)
func (s *Scenarios) EmptyQuery() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(WithQuery(""))
}

// SyntaxErrorQuery returns malformed SQL (EC-002)
func (s *Scenarios) SyntaxErrorQuery() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(WithQuery("SELCT * FORM data"))
}

// NonExistentTable returns query on missing table (EC-003)
func (s *Scenarios) NonExistentTable() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery("SELECT * FROM non_existent_table_xyz"),
	)
}

// HeavyQuery returns a memory-intensive query (EC-005)
func (s *Scenarios) HeavyQuery() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery(`
			SELECT *
			FROM generate_series(1, 100000000) t1
			CROSS JOIN generate_series(1, 1000) t2
		`),
	)
}

// DivisionByZero returns query with division by zero (EC-009)
func (s *Scenarios) DivisionByZero() *pb.ExecuteQueryRequest {
	return s.factory.MakeExecuteQueryRequest(
		WithQuery("SELECT 1/0 as result"),
	)
}

// MultiTenantScenario returns requests for two different tenants
func (s *Scenarios) MultiTenantScenario() (tenant1Req, tenant2Req *pb.CreateDatabaseRequest) {
	tenant1Req = s.factory.MakeCreateDatabaseRequest(
		WithDatabaseUser("user-001", "org-001"),
	)
	tenant2Req = s.factory.MakeCreateDatabaseRequest(
		WithDatabaseUser("user-002", "org-002"),
	)
	return
}

// ============================================
// Assertion Helpers
// ============================================

// ExpectedSchemaName returns the expected org schema name
func ExpectedSchemaName(orgID string) string {
	return fmt.Sprintf("org_%s", orgID)
}

// DefaultSchemaName returns schema name for default test org
func DefaultSchemaName() string {
	return ExpectedSchemaName("test-org-001")
}

// QualifiedTableName returns fully qualified table name
func QualifiedTableName(orgID, tableName string) string {
	return fmt.Sprintf("%s.%s", ExpectedSchemaName(orgID), tableName)
}

// SampleCSVData returns sample CSV data for testing
func SampleCSVData() string {
	return `id,name,value,date
1,Item A,100.50,2025-01-01
2,Item B,200.75,2025-01-02
3,Item C,150.25,2025-01-03`
}
