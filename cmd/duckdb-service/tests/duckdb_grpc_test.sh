#!/bin/bash

# DuckDB gRPC Service Testing Script
# Tests all gRPC functions using Go client
# File: cmd/duckdb-service/tests/duckdb_grpc_test.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# DuckDB gRPC Service endpoint
GRPC_ENDPOINT="${GRPC_ENDPOINT:-localhost:50052}"

echo "======================================================================"
echo "DuckDB gRPC Service Tests (Go Client)"
echo "======================================================================"
echo ""
echo "🔗 Service Endpoint: $GRPC_ENDPOINT"
echo "📁 Project Root: $PROJECT_ROOT"
echo ""

# Function to print test result
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ PASSED${NC}: $2"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ FAILED${NC}: $2"
        ((TESTS_FAILED++))
    fi
}

# Function to print section header
print_section() {
    echo ""
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""
}

# Create test directory
TEST_DIR="$PROJECT_ROOT/cmd/duckdb-service/tests/go_test"
mkdir -p "$TEST_DIR"

# Generate test code
print_section "Generating Go Test Code"

cat > "$TEST_DIR/main_test.go" << 'GOTEST'
package main

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
)

var (
	client        pb.DuckDBServiceClient
	conn          *grpc.ClientConn
	testUserID    = fmt.Sprintf("test-user-%d", time.Now().Unix())
	testDatabase  = fmt.Sprintf("test-db-%d", time.Now().Unix())
	testTable     = "test_users"
	testDatabaseID string
)

// Setup test connection
func TestMain(m *testing.M) {
	// Get endpoint from environment or use default
	endpoint := os.Getenv("GRPC_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:50052"
	}

	fmt.Printf("🔗 Connecting to DuckDB gRPC Service: %s\n", endpoint)

	// Create gRPC connection
	var err error
	conn, err = grpc.Dial(
		endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(100*1024*1024),
			grpc.MaxCallSendMsgSize(100*1024*1024),
		),
	)
	if err != nil {
		fmt.Printf("❌ Failed to connect: %v\n", err)
		os.Exit(1)
	}

	client = pb.NewDuckDBServiceClient(conn)
	fmt.Printf("✅ Connected successfully!\n\n")
	fmt.Printf("📋 Test Parameters:\n")
	fmt.Printf("   User ID: %s\n", testUserID)
	fmt.Printf("   Database: %s\n", testDatabase)
	fmt.Printf("   Table: %s\n\n", testTable)

	// Run tests
	code := m.Run()

	// Cleanup
	conn.Close()
	os.Exit(code)
}

// Test 1: Health Check
func TestHealthCheck(t *testing.T) {
	fmt.Println("======================================")
	fmt.Println("Test 1: Health Check")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	req := &pb.HealthCheckRequest{
		Detailed: true,
	}

	resp, err := client.HealthCheck(ctx, req)
	if err != nil {
		t.Fatalf("❌ HealthCheck failed: %v", err)
	}

	fmt.Printf("✅ Service Status: %s\n", resp.Status)
	fmt.Printf("   Healthy: %v\n", resp.Healthy)
	fmt.Printf("   Success: %v\n", resp.Success)

	if !resp.Healthy {
		t.Errorf("Service is not healthy")
	}
}

// Test 2: Create Database
func TestCreateDatabase(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 2: Create Database")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	req := &pb.CreateDatabaseRequest{
		DatabaseName:   testDatabase,
		UserId:         testUserID,
		OrganizationId: "test-org",
	}

	resp, err := client.CreateDatabase(ctx, req)
	if err != nil {
		t.Fatalf("❌ CreateDatabase failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ CreateDatabase returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Database created successfully!\n")
	if resp.DatabaseInfo != nil {
		fmt.Printf("   Database ID: %s\n", resp.DatabaseInfo.DatabaseId)
		fmt.Printf("   Database Name: %s\n", resp.DatabaseInfo.DatabaseName)
		fmt.Printf("   MinIO Bucket: %s\n", resp.DatabaseInfo.MinioBucket)
		testDatabaseID = resp.DatabaseInfo.DatabaseId
	}
}

// Test 3: List Databases
func TestListDatabases(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 3: List Databases")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ListDatabasesRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
	}

	resp, err := client.ListDatabases(ctx, req)
	if err != nil {
		t.Fatalf("❌ ListDatabases failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ ListDatabases returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Found %d database(s):\n", len(resp.Databases))
	for i, db := range resp.Databases {
		fmt.Printf("   %d. %s (ID: %s)\n", i+1, db.DatabaseName, db.DatabaseId)
	}

	if len(resp.Databases) == 0 {
		t.Errorf("Expected at least 1 database, got 0")
	}
}

// Test 4: Create Table
func TestCreateTable(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 4: Create Table")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	columns := []*pb.ColumnInfo{
		{Name: "id", DataType: "INTEGER", Nullable: false},
		{Name: "name", DataType: "VARCHAR", Nullable: false},
		{Name: "email", DataType: "VARCHAR", Nullable: false},
		{Name: "age", DataType: "INTEGER", Nullable: true},
		{Name: "created_at", DataType: "TIMESTAMP", Nullable: true},
	}

	req := &pb.CreateTableRequest{
		DatabaseId: testDatabaseID,
		TableName:  testTable,
		Columns:    columns,
		UserId:     testUserID,
	}

	resp, err := client.CreateTable(ctx, req)
	if err != nil {
		t.Fatalf("❌ CreateTable failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ CreateTable returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Table created successfully!\n")
	if resp.TableInfo != nil {
		fmt.Printf("   Table Name: %s\n", resp.TableInfo.TableName)
		fmt.Printf("   Columns: %d\n", len(resp.TableInfo.Columns))
	}
}

// Test 5: Insert Data (Execute Statement)
func TestInsertData(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 5: Insert Data")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	statements := []string{
		fmt.Sprintf("INSERT INTO %s (id, name, email, age, created_at) VALUES (1, 'Alice', 'alice@example.com', 30, CURRENT_TIMESTAMP)", testTable),
		fmt.Sprintf("INSERT INTO %s (id, name, email, age, created_at) VALUES (2, 'Bob', 'bob@example.com', 25, CURRENT_TIMESTAMP)", testTable),
		fmt.Sprintf("INSERT INTO %s (id, name, email, age, created_at) VALUES (3, 'Charlie', 'charlie@example.com', 35, CURRENT_TIMESTAMP)", testTable),
	}

	for i, stmt := range statements {
		req := &pb.ExecuteStatementRequest{
			DatabaseId: testDatabaseID,
			Statement:  stmt,
			UserId:     testUserID,
		}

		resp, err := client.ExecuteStatement(ctx, req)
		if err != nil {
			t.Fatalf("❌ ExecuteStatement %d failed: %v", i+1, err)
		}

		if !resp.Success {
			t.Fatalf("❌ ExecuteStatement %d returned success=false: %s", i+1, resp.Error)
		}

		fmt.Printf("✅ Inserted row %d: %d row(s) affected\n", i+1, resp.AffectedRows)
	}
}

// Test 6: Query Data
func TestQueryData(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 6: Query Data")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ExecuteQueryRequest{
		DatabaseId: testDatabaseID,
		Query:      fmt.Sprintf("SELECT * FROM %s", testTable),
		UserId:     testUserID,
	}

	resp, err := client.ExecuteQuery(ctx, req)
	if err != nil {
		t.Fatalf("❌ ExecuteQuery failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ ExecuteQuery returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Query executed successfully!\n")
	fmt.Printf("   Rows returned: %d\n", resp.RowCount)
	fmt.Printf("   Columns: %v\n", resp.Columns)
	fmt.Printf("   Execution time: %.2f ms\n", resp.ExecutionTimeMs)

	if resp.RowCount != 3 {
		t.Errorf("Expected 3 rows, got %d", resp.RowCount)
	}
}

// Test 7: List Tables
func TestListTables(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 7: List Tables")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ListTablesRequest{
		DatabaseId: testDatabaseID,
		UserId:     testUserID,
		SchemaName: "main",
	}

	resp, err := client.ListTables(ctx, req)
	if err != nil {
		t.Fatalf("❌ ListTables failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ ListTables returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Found %d table(s):\n", len(resp.Tables))
	for i, table := range resp.Tables {
		fmt.Printf("   %d. %s (Rows: %d)\n", i+1, table.TableName, table.RowCount)
	}

	if len(resp.Tables) == 0 {
		t.Errorf("Expected at least 1 table, got 0")
	}
}

// Test 8: Get Table Schema
func TestGetTableSchema(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 8: Get Table Schema")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.GetTableSchemaRequest{
		DatabaseId: testDatabaseID,
		TableName:  testTable,
		UserId:     testUserID,
	}

	resp, err := client.GetTableSchema(ctx, req)
	if err != nil {
		t.Fatalf("❌ GetTableSchema failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ GetTableSchema returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Table schema retrieved!\n")
	if resp.TableInfo != nil {
		fmt.Printf("   Table: %s\n", resp.TableInfo.TableName)
		fmt.Printf("   Columns:\n")
		for _, col := range resp.TableInfo.Columns {
			nullable := "NULL"
			if !col.Nullable {
				nullable = "NOT NULL"
			}
			fmt.Printf("     - %s: %s %s\n", col.Name, col.DataType, nullable)
		}
	}
}

// Test 9: Query with Filter
func TestQueryWithFilter(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 9: Query with Filter")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ExecuteQueryRequest{
		DatabaseId: testDatabaseID,
		Query:      fmt.Sprintf("SELECT name, age FROM %s WHERE age > 28 ORDER BY age", testTable),
		UserId:     testUserID,
	}

	resp, err := client.ExecuteQuery(ctx, req)
	if err != nil {
		t.Fatalf("❌ ExecuteQuery (filtered) failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ ExecuteQuery (filtered) returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Filtered query executed!\n")
	fmt.Printf("   Rows returned: %d\n", resp.RowCount)
	fmt.Printf("   Execution time: %.2f ms\n", resp.ExecutionTimeMs)

	if resp.RowCount != 2 {
		t.Errorf("Expected 2 rows (age > 28), got %d", resp.RowCount)
	}
}

// Test 10: Delete Database (Cleanup)
func TestDeleteDatabase(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 10: Delete Database (Cleanup)")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	req := &pb.DeleteDatabaseRequest{
		DatabaseId: testDatabaseID,
		UserId:     testUserID,
	}

	resp, err := client.DeleteDatabase(ctx, req)
	if err != nil {
		t.Fatalf("❌ DeleteDatabase failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ DeleteDatabase returned success=false: %s", resp.Error)
	}

	fmt.Printf("✅ Database deleted successfully!\n")
	fmt.Printf("   Database: %s\n", testDatabase)
}
GOTEST

# Create go.mod for test
cat > "$TEST_DIR/go.mod" << GOMOD
module github.com/isa-cloud/isa_cloud/cmd/duckdb-service/tests/go_test

go 1.25

require (
	github.com/isa-cloud/isa_cloud v0.0.0
	google.golang.org/grpc v1.69.2
	google.golang.org/protobuf v1.36.0
)

replace github.com/isa-cloud/isa_cloud => ../../../..
GOMOD

echo "✅ Test code generated"

# Run tests
print_section "Running Go Tests"
cd "$TEST_DIR"

echo "📦 Downloading dependencies..."
go mod download || {
    echo -e "${RED}❌ Failed to download dependencies${NC}"
    exit 1
}

echo ""
echo "🚀 Running tests..."
echo ""

if GRPC_ENDPOINT="$GRPC_ENDPOINT" go test -v -timeout 3m; then
    print_result 0 "All Go tests passed"
else
    print_result 1 "Some Go tests failed"
fi

# Cleanup
cd "$PROJECT_ROOT"
# Uncomment to remove test directory after running
# rm -rf "$TEST_DIR"

# Summary
echo ""
echo "======================================================================"
echo -e "${BLUE}Test Summary${NC}"
echo "======================================================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
TOTAL=$((TESTS_PASSED + TESTS_FAILED))
echo "Total: $TOTAL"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Please review the output above.${NC}"
    exit 1
fi
