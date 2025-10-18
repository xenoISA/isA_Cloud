#!/bin/bash

# NATS gRPC Service Testing Script
# Tests all gRPC functions using Go client
# File: cmd/nats-service/tests/nats_grpc_test.sh

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

# NATS gRPC Service endpoint
GRPC_ENDPOINT="${GRPC_ENDPOINT:-localhost:50056}"

echo "======================================================================"
echo "NATS gRPC Service Tests (Go Client)"
echo "======================================================================"
echo ""
echo "🔌 Service Endpoint: $GRPC_ENDPOINT"
echo "📂 Project Root: $PROJECT_ROOT"
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
TEST_DIR="$PROJECT_ROOT/cmd/nats-service/tests/go_test"
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
	"google.golang.org/protobuf/types/known/durationpb"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
)

var (
	client       pb.NATSServiceClient
	conn         *grpc.ClientConn
	testUserID   = fmt.Sprintf("test-user-%d", time.Now().Unix())
	testSubject  = "events.test"
	testStream   = fmt.Sprintf("test-stream-%d", time.Now().Unix())
	testKVBucket = "test-config"
	testObjBucket = "test-objects"
)

// Setup test connection
func TestMain(m *testing.M) {
	// Get endpoint from environment or use default
	endpoint := os.Getenv("GRPC_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:50056"
	}

	fmt.Printf("🔌 Connecting to NATS gRPC Service: %s\n", endpoint)

	// Create gRPC connection
	var err error
	conn, err = grpc.Dial(
		endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(10*1024*1024),
			grpc.MaxCallSendMsgSize(10*1024*1024),
		),
	)
	if err != nil {
		fmt.Printf("❌ Failed to connect: %v\n", err)
		os.Exit(1)
	}

	client = pb.NewNATSServiceClient(conn)
	fmt.Printf("✅ Connected successfully!\n\n")
	fmt.Printf("📋 Test Parameters:\n")
	fmt.Printf("   User ID: %s\n", testUserID)
	fmt.Printf("   Subject: %s\n", testSubject)
	fmt.Printf("   Stream: %s\n\n", testStream)

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

	req := &pb.NATSHealthCheckRequest{
		DeepCheck: true,
	}

	resp, err := client.HealthCheck(ctx, req)
	if err != nil {
		t.Fatalf("❌ HealthCheck failed: %v", err)
	}

	fmt.Printf("✅ Service Status: %s\n", resp.NatsStatus)
	fmt.Printf("   Healthy: %v\n", resp.Healthy)
	fmt.Printf("   JetStream Enabled: %v\n", resp.JetstreamEnabled)
	fmt.Printf("   Connections: %d\n", resp.Connections)

	if !resp.Healthy {
		t.Errorf("Service is not healthy")
	}
}

// Test 2: Publish Message
func TestPublish(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 2: Publish Message")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	testData := []byte(fmt.Sprintf("Hello from NATS gRPC!\nTimestamp: %s\nUser: %s\n",
		time.Now().Format(time.RFC3339), testUserID))

	req := &pb.PublishRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Subject:        testSubject,
		Data:           testData,
	}

	resp, err := client.Publish(ctx, req)
	if err != nil {
		t.Fatalf("❌ Publish failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ Publish returned success=false: %s", resp.Message)
	}

	fmt.Printf("✅ Message published successfully!\n")
	fmt.Printf("   Subject: %s\n", testSubject)
	fmt.Printf("   Data size: %d bytes\n", len(testData))
}

// Test 3: Publish Batch
func TestPublishBatch(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 3: Publish Batch Messages")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	messages := []*pb.NATSMessage{
		{Subject: "events.user.created", Data: []byte(`{"user_id": "123"}`)},
		{Subject: "events.user.updated", Data: []byte(`{"user_id": "123", "field": "email"}`)},
		{Subject: "events.user.deleted", Data: []byte(`{"user_id": "123"}`)},
	}

	req := &pb.PublishBatchRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Messages:       messages,
	}

	resp, err := client.PublishBatch(ctx, req)
	if err != nil {
		t.Fatalf("❌ PublishBatch failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ PublishBatch returned success=false")
	}

	fmt.Printf("✅ Batch published successfully!\n")
	fmt.Printf("   Published: %d messages\n", resp.PublishedCount)
	fmt.Printf("   Errors: %d\n", len(resp.Errors))
}

// Test 4: Create Stream
func TestCreateStream(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 4: Create JetStream Stream")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	streamConfig := &pb.StreamConfig{
		Name:       testStream,
		Subjects:   []string{"events.>"},
		Storage:    pb.StorageType_STORAGE_MEMORY,
		MaxMsgs:    1000,
		MaxBytes:   1024 * 1024 * 10, // 10MB
		Replicas:   1,
	}

	req := &pb.CreateStreamRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Config:         streamConfig,
	}

	resp, err := client.CreateStream(ctx, req)
	if err != nil {
		t.Fatalf("❌ CreateStream failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ CreateStream returned success=false: %s", resp.Message)
	}

	fmt.Printf("✅ Stream created successfully!\n")
	if resp.Stream != nil {
		fmt.Printf("   Name: %s\n", resp.Stream.Name)
		fmt.Printf("   Subjects: %v\n", resp.Stream.Config.Subjects)
	}
}

// Test 5: Get Stream Info
func TestGetStreamInfo(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 5: Get Stream Info")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.GetStreamInfoRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		StreamName:     testStream,
	}

	resp, err := client.GetStreamInfo(ctx, req)
	if err != nil {
		t.Fatalf("❌ GetStreamInfo failed: %v", err)
	}

	stream := resp.Stream
	fmt.Printf("✅ Stream info retrieved!\n")
	fmt.Printf("   Name: %s\n", stream.Name)
	fmt.Printf("   Messages: %d\n", stream.State.Messages)
	fmt.Printf("   Bytes: %d\n", stream.State.Bytes)
	fmt.Printf("   Consumers: %d\n", stream.State.ConsumerCount)
}

// Test 6: Publish to Stream
func TestPublishToStream(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 6: Publish to Stream")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	testData := []byte(fmt.Sprintf("Stream message at %s", time.Now().Format(time.RFC3339)))

	req := &pb.PublishToStreamRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		StreamName:     testStream,
		Subject:        testSubject,
		Data:           testData,
	}

	resp, err := client.PublishToStream(ctx, req)
	if err != nil {
		t.Fatalf("❌ PublishToStream failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ PublishToStream returned success=false: %s", resp.Message)
	}

	fmt.Printf("✅ Message published to stream!\n")
	fmt.Printf("   Sequence: %d\n", resp.Sequence)
}

// Test 7: KV Put
func TestKVPut(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 7: Key-Value Store - Put")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.KVPutRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Bucket:         testKVBucket,
		Key:            "setting1",
		Value:          []byte("value1"),
	}

	resp, err := client.KVPut(ctx, req)
	if err != nil {
		t.Fatalf("❌ KVPut failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ KVPut returned success=false")
	}

	fmt.Printf("✅ Key-value pair stored!\n")
	fmt.Printf("   Revision: %d\n", resp.Revision)
}

// Test 8: KV Get
func TestKVGet(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 8: Key-Value Store - Get")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.KVGetRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Bucket:         testKVBucket,
		Key:            "setting1",
	}

	resp, err := client.KVGet(ctx, req)
	if err != nil {
		t.Fatalf("❌ KVGet failed: %v", err)
	}

	if !resp.Found {
		t.Fatalf("❌ Key not found")
	}

	fmt.Printf("✅ Key-value retrieved!\n")
	fmt.Printf("   Value: %s\n", string(resp.Value))
	fmt.Printf("   Revision: %d\n", resp.Revision)
}

// Test 9: Object Put
func TestObjectPut(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 9: Object Store - Put")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	testData := []byte(fmt.Sprintf("Object data created at %s", time.Now().Format(time.RFC3339)))

	req := &pb.ObjectPutRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Bucket:         testObjBucket,
		ObjectName:     "test-file.txt",
		Data:           testData,
	}

	resp, err := client.ObjectPut(ctx, req)
	if err != nil {
		t.Fatalf("❌ ObjectPut failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ ObjectPut returned success=false")
	}

	fmt.Printf("✅ Object stored!\n")
	fmt.Printf("   Object ID: %s\n", resp.ObjectId)
}

// Test 10: Object Get
func TestObjectGet(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 10: Object Store - Get")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ObjectGetRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		Bucket:         testObjBucket,
		ObjectName:     "test-file.txt",
	}

	resp, err := client.ObjectGet(ctx, req)
	if err != nil {
		t.Fatalf("❌ ObjectGet failed: %v", err)
	}

	if !resp.Found {
		t.Fatalf("❌ Object not found")
	}

	fmt.Printf("✅ Object retrieved!\n")
	fmt.Printf("   Size: %d bytes\n", len(resp.Data))
	fmt.Printf("   Preview: %s\n", string(resp.Data[:min(50, len(resp.Data))]))
}

// Test 11: Get Statistics
func TestGetStatistics(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 11: Get NATS Statistics")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.GetStatisticsRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
	}

	resp, err := client.GetStatistics(ctx, req)
	if err != nil {
		t.Fatalf("❌ GetStatistics failed: %v", err)
	}

	fmt.Printf("✅ Statistics retrieved!\n")
	fmt.Printf("   Connections: %d\n", resp.Connections)
	fmt.Printf("   In Messages: %d\n", resp.InMsgs)
	fmt.Printf("   Out Messages: %d\n", resp.OutMsgs)
	fmt.Printf("   In Bytes: %d\n", resp.InBytes)
	fmt.Printf("   Out Bytes: %d\n", resp.OutBytes)
}

// Test 12: Get Stream Stats
func TestGetStreamStats(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 12: Get Stream Statistics")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.GetStreamStatsRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		StreamName:     testStream,
	}

	resp, err := client.GetStreamStats(ctx, req)
	if err != nil {
		t.Fatalf("❌ GetStreamStats failed: %v", err)
	}

	fmt.Printf("✅ Stream statistics retrieved!\n")
	fmt.Printf("   Stream: %s\n", resp.StreamName)
	fmt.Printf("   Messages: %d\n", resp.Messages)
	fmt.Printf("   Bytes: %d\n", resp.Bytes)
	fmt.Printf("   Consumers: %d\n", resp.ConsumerCount)
}

// Test 13: Delete Stream (Cleanup)
func TestDeleteStream(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 13: Delete Stream (Cleanup)")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.DeleteStreamRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
		StreamName:     testStream,
	}

	resp, err := client.DeleteStream(ctx, req)
	if err != nil {
		t.Fatalf("❌ DeleteStream failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("❌ DeleteStream returned success=false")
	}

	fmt.Printf("✅ Stream deleted successfully!\n")
	fmt.Printf("   Stream: %s\n", testStream)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
GOTEST

# Create go.mod for test
cat > "$TEST_DIR/go.mod" << GOMOD
module github.com/isa-cloud/isa_cloud/cmd/nats-service/tests/go_test

go 1.23

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

if GRPC_ENDPOINT="$GRPC_ENDPOINT" go test -v -timeout 2m; then
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



