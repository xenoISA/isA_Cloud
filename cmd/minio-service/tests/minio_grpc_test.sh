#!/bin/bash

# MinIO gRPC Service Testing Script
# Tests all gRPC functions using Go client
# File: cmd/minio-service/tests/minio_grpc_test.sh

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

# MinIO gRPC Service endpoint
GRPC_ENDPOINT="${GRPC_ENDPOINT:-localhost:50051}"

echo "======================================================================"
echo "MinIO gRPC Service Tests (Go Client)"
echo "======================================================================"
echo ""
echo "=� Service Endpoint: $GRPC_ENDPOINT"
echo "=� Project Root: $PROJECT_ROOT"
echo ""

# Function to print test result
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN} PASSED${NC}: $2"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}L FAILED${NC}: $2"
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
TEST_DIR="$PROJECT_ROOT/cmd/minio-service/tests/go_test"
mkdir -p "$TEST_DIR"

# Generate test code
print_section "Generating Go Test Code"

cat > "$TEST_DIR/main_test.go" << 'GOTEST'
package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
)

var (
	client     pb.MinIOServiceClient
	conn       *grpc.ClientConn
	testUserID = fmt.Sprintf("test-user-%d", time.Now().Unix())
	testBucket = fmt.Sprintf("test-bucket-%d", time.Now().Unix())
	testObject = "test-file.txt"
)

// Setup test connection
func TestMain(m *testing.M) {
	// Get endpoint from environment or use default
	endpoint := os.Getenv("GRPC_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:50051"
	}

	fmt.Printf("= Connecting to MinIO gRPC Service: %s\n", endpoint)

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
		fmt.Printf("L Failed to connect: %v\n", err)
		os.Exit(1)
	}

	client = pb.NewMinIOServiceClient(conn)
	fmt.Printf(" Connected successfully!\n\n")
	fmt.Printf("=� Test Parameters:\n")
	fmt.Printf("   User ID: %s\n", testUserID)
	fmt.Printf("   Bucket: %s\n", testBucket)
	fmt.Printf("   Object: %s\n\n", testObject)

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
		t.Fatalf("L HealthCheck failed: %v", err)
	}

	fmt.Printf(" Service Status: %s\n", resp.Status)
	fmt.Printf("   Healthy: %v\n", resp.Healthy)
	fmt.Printf("   Success: %v\n", resp.Success)

	if !resp.Healthy {
		t.Errorf("Service is not healthy")
	}
}

// Test 2: Create Bucket
func TestCreateBucket(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 2: Create Bucket")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.CreateBucketRequest{
		BucketName:     testBucket,
		UserId:         testUserID,
		OrganizationId: "test-org",
		Region:         "us-east-1",
	}

	resp, err := client.CreateBucket(ctx, req)
	if err != nil {
		t.Fatalf("L CreateBucket failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L CreateBucket returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Bucket created successfully!\n")
	if resp.BucketInfo != nil {
		fmt.Printf("   Name: %s\n", resp.BucketInfo.Name)
		fmt.Printf("   Owner: %s\n", resp.BucketInfo.OwnerId)
		fmt.Printf("   Organization: %s\n", resp.BucketInfo.OrganizationId)
	}
}

// Test 3: List Buckets
func TestListBuckets(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 3: List Buckets")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ListBucketsRequest{
		UserId:         testUserID,
		OrganizationId: "test-org",
	}

	resp, err := client.ListBuckets(ctx, req)
	if err != nil {
		t.Fatalf("L ListBuckets failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L ListBuckets returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Found %d bucket(s):\n", len(resp.Buckets))
	for i, bucket := range resp.Buckets {
		fmt.Printf("   %d. %s (Owner: %s)\n", i+1, bucket.Name, bucket.OwnerId)
	}

	if len(resp.Buckets) == 0 {
		t.Errorf("Expected at least 1 bucket, got 0")
	}
}

// Test 4: Put Object (Streaming)
func TestPutObject(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 4: Put Object (Streaming)")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	stream, err := client.PutObject(ctx)
	if err != nil {
		t.Fatalf("L Failed to create PutObject stream: %v", err)
	}

	// Prepare test data
	testData := []byte(fmt.Sprintf("Hello from MinIO gRPC Service!\nTimestamp: %s\nUser: %s\n",
		time.Now().Format(time.RFC3339), testUserID))

	// Send metadata first
	metadata := &pb.PutObjectMetadata{
		BucketName:    testBucket,
		ObjectKey:     testObject,
		UserId:        testUserID,
		ContentType:   "text/plain",
		ContentLength: int64(len(testData)),
	}

	err = stream.Send(&pb.PutObjectRequest{
		Data: &pb.PutObjectRequest_Metadata{
			Metadata: metadata,
		},
	})
	if err != nil {
		t.Fatalf("L Failed to send metadata: %v", err)
	}

	// Send data in chunks
	chunkSize := 1024
	for i := 0; i < len(testData); i += chunkSize {
		end := i + chunkSize
		if end > len(testData) {
			end = len(testData)
		}

		err = stream.Send(&pb.PutObjectRequest{
			Data: &pb.PutObjectRequest_Chunk{
				Chunk: testData[i:end],
			},
		})
		if err != nil {
			t.Fatalf("L Failed to send chunk: %v", err)
		}
	}

	// Close and get response
	resp, err := stream.CloseAndRecv()
	if err != nil {
		t.Fatalf("L Failed to receive response: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L PutObject returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Object uploaded successfully!\n")
	fmt.Printf("   Object Key: %s\n", resp.ObjectKey)
	fmt.Printf("   Size: %d bytes\n", resp.Size)
	fmt.Printf("   ETag: %s\n", resp.Etag)
}

// Test 5: List Objects
func TestListObjects(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 5: List Objects")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.ListObjectsRequest{
		BucketName: testBucket,
		UserId:     testUserID,
		Recursive:  true,
		MaxKeys:    100,
	}

	resp, err := client.ListObjects(ctx, req)
	if err != nil {
		t.Fatalf("L ListObjects failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L ListObjects returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Found %d object(s):\n", len(resp.Objects))
	for i, obj := range resp.Objects {
		fmt.Printf("   %d. %s (Size: %d bytes, ETag: %s)\n",
			i+1, obj.Key, obj.Size, obj.Etag)
	}

	if len(resp.Objects) == 0 {
		t.Errorf("Expected at least 1 object, got 0")
	}
}

// Test 6: Get Object Info (Stat)
func TestStatObject(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 6: Stat Object")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.StatObjectRequest{
		BucketName: testBucket,
		ObjectKey:  testObject,
		UserId:     testUserID,
	}

	resp, err := client.StatObject(ctx, req)
	if err != nil {
		t.Fatalf("L StatObject failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L StatObject returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Object info retrieved!\n")
	if resp.ObjectInfo != nil {
		fmt.Printf("   Key: %s\n", resp.ObjectInfo.Key)
		fmt.Printf("   Size: %d bytes\n", resp.ObjectInfo.Size)
		fmt.Printf("   Content-Type: %s\n", resp.ObjectInfo.ContentType)
		fmt.Printf("   ETag: %s\n", resp.ObjectInfo.Etag)
	}
}

// Test 7: Get Object (Streaming Download)
func TestGetObject(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 7: Get Object (Streaming)")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	req := &pb.GetObjectRequest{
		BucketName: testBucket,
		ObjectKey:  testObject,
		UserId:     testUserID,
	}

	stream, err := client.GetObject(ctx, req)
	if err != nil {
		t.Fatalf("L Failed to create GetObject stream: %v", err)
	}

	var totalBytes int64
	var metadata *pb.ObjectInfo
	firstChunk := true

	for {
		resp, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatalf("L Failed to receive chunk: %v", err)
		}

		switch data := resp.Data.(type) {
		case *pb.GetObjectResponse_Metadata:
			metadata = data.Metadata
			if firstChunk {
				fmt.Printf("=� Receiving object metadata:\n")
				fmt.Printf("   Key: %s\n", metadata.Key)
				fmt.Printf("   Size: %d bytes\n", metadata.Size)
				firstChunk = false
			}
		case *pb.GetObjectResponse_Chunk:
			totalBytes += int64(len(data.Chunk))
		}
	}

	fmt.Printf(" Object downloaded successfully!\n")
	fmt.Printf("   Total bytes received: %d\n", totalBytes)

	if metadata != nil && totalBytes != metadata.Size {
		t.Errorf("Size mismatch: expected %d bytes, got %d bytes", metadata.Size, totalBytes)
	}
}

// Test 8: Get Presigned URL
func TestGetPresignedURL(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 8: Get Presigned URL")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.GetPresignedURLRequest{
		BucketName:    testBucket,
		ObjectKey:     testObject,
		UserId:        testUserID,
		ExpirySeconds: 3600,
	}

	resp, err := client.GetPresignedURL(ctx, req)
	if err != nil {
		t.Fatalf("L GetPresignedURL failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L GetPresignedURL returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Presigned URL generated!\n")
	fmt.Printf("   URL: %s\n", resp.Url[:80]+"...")
	fmt.Printf("   Expires at: %v\n", resp.ExpiresAt.AsTime())
}

// Test 9: Copy Object
func TestCopyObject(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 9: Copy Object")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	destKey := testObject + ".copy"

	req := &pb.CopyObjectRequest{
		SourceBucket: testBucket,
		SourceKey:    testObject,
		DestBucket:   testBucket,
		DestKey:      destKey,
		UserId:       testUserID,
	}

	resp, err := client.CopyObject(ctx, req)
	if err != nil {
		t.Fatalf("L CopyObject failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L CopyObject returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Object copied successfully!\n")
	fmt.Printf("   Source: %s/%s\n", testBucket, testObject)
	fmt.Printf("   Destination: %s/%s\n", testBucket, destKey)
}

// Test 10: Delete Object
func TestDeleteObject(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 10: Delete Object")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Delete the copied object
	req := &pb.DeleteObjectRequest{
		BucketName: testBucket,
		ObjectKey:  testObject + ".copy",
		UserId:     testUserID,
	}

	resp, err := client.DeleteObject(ctx, req)
	if err != nil {
		t.Fatalf("L DeleteObject failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L DeleteObject returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Object deleted successfully!\n")
	fmt.Printf("   Object: %s\n", testObject+".copy")
}

// Test 11: Delete Bucket (Cleanup)
func TestDeleteBucket(t *testing.T) {
	fmt.Println("\n======================================")
	fmt.Println("Test 11: Delete Bucket (Cleanup)")
	fmt.Println("======================================")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	req := &pb.DeleteBucketRequest{
		BucketName: testBucket,
		UserId:     testUserID,
		Force:      true, // Force delete with all objects
	}

	resp, err := client.DeleteBucket(ctx, req)
	if err != nil {
		t.Fatalf("L DeleteBucket failed: %v", err)
	}

	if !resp.Success {
		t.Fatalf("L DeleteBucket returned success=false: %s", resp.Error)
	}

	fmt.Printf(" Bucket deleted successfully!\n")
	fmt.Printf("   Bucket: %s\n", testBucket)
	fmt.Printf("   Deleted objects: %d\n", resp.DeletedObjects)
}
GOTEST

# Create go.mod for test
cat > "$TEST_DIR/go.mod" << GOMOD
module github.com/isa-cloud/isa_cloud/cmd/minio-service/tests/go_test

go 1.23

require (
	github.com/isa-cloud/isa_cloud v0.0.0
	google.golang.org/grpc v1.69.2
	google.golang.org/protobuf v1.36.0
)

replace github.com/isa-cloud/isa_cloud => ../../../..
GOMOD

echo " Test code generated"

# Run tests
print_section "Running Go Tests"
cd "$TEST_DIR"

echo "=� Downloading dependencies..."
go mod download || {
    echo -e "${RED}L Failed to download dependencies${NC}"
    exit 1
}

echo ""
echo ">� Running tests..."
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
    echo -e "${GREEN} All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}L Some tests failed. Please review the output above.${NC}"
    exit 1
fi
