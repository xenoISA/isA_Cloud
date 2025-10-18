// Package clients provides gRPC client implementations for inter-service communication
// MinIO gRPC Client - for services to communicate with MinIO service
//
// 文件名: pkg/grpc/clients/minio_grpc_client.go
package clients

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/isa-cloud/isa_cloud/api/proto/minio"
)

// MinIOGRPCClient MinIO gRPC 客户端
// 用于服务间通信，连接到 MinIO gRPC 服务
type MinIOGRPCClient struct {
	conn   *grpc.ClientConn
	client pb.MinIOServiceClient
	userID string
}

// MinIOGRPCConfig MinIO gRPC 客户端配置
type MinIOGRPCConfig struct {
	Host   string
	Port   int
	UserID string
}

// NewMinIOGRPCClient 创建 MinIO gRPC 客户端
func NewMinIOGRPCClient(cfg *MinIOGRPCConfig) (*MinIOGRPCClient, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)

	// Create gRPC connection
	conn, err := grpc.Dial(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
		grpc.WithTimeout(10*time.Second),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to MinIO gRPC service at %s: %w", addr, err)
	}

	return &MinIOGRPCClient{
		conn:   conn,
		client: pb.NewMinIOServiceClient(conn),
		userID: cfg.UserID,
	}, nil
}

// Close 关闭连接
func (c *MinIOGRPCClient) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// ============================================
// Bucket Operations
// ============================================

// CreateBucket 创建桶
// Note: MinIO service will automatically add user prefix to bucket name
func (c *MinIOGRPCClient) CreateBucket(ctx context.Context, bucketName string) error {
	req := &pb.CreateBucketRequest{
		BucketName: bucketName,
		UserId:     c.userID,
	}

	resp, err := c.client.CreateBucket(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("create bucket failed: %s", resp.Error)
	}

	return nil
}

// BucketExists 检查桶是否存在
func (c *MinIOGRPCClient) BucketExists(ctx context.Context, bucketName string) (bool, error) {
	req := &pb.GetBucketInfoRequest{
		BucketName: bucketName,
		UserId:     c.userID,
	}

	resp, err := c.client.GetBucketInfo(ctx, req)
	if err != nil {
		return false, nil // Bucket doesn't exist
	}

	return resp.Success, nil
}

// ListBuckets 列出所有桶
func (c *MinIOGRPCClient) ListBuckets(ctx context.Context) ([]*pb.BucketInfo, error) {
	req := &pb.ListBucketsRequest{
		UserId: c.userID,
	}

	resp, err := c.client.ListBuckets(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return nil, fmt.Errorf("list buckets failed: %s", resp.Error)
	}

	return resp.Buckets, nil
}

// DeleteBucket 删除桶
func (c *MinIOGRPCClient) DeleteBucket(ctx context.Context, bucketName string, force bool) error {
	req := &pb.DeleteBucketRequest{
		BucketName: bucketName,
		UserId:     c.userID,
		Force:      force,
	}

	resp, err := c.client.DeleteBucket(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("delete bucket failed: %s", resp.Error)
	}

	return nil
}

// ============================================
// Object Operations
// ============================================

// PutObject 上传对象
func (c *MinIOGRPCClient) PutObject(ctx context.Context, bucketName, objectKey string, reader io.Reader, size int64) (*pb.PutObjectResponse, error) {
	stream, err := c.client.PutObject(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create upload stream: %w", err)
	}

	// Send metadata first
	metadata := &pb.PutObjectMetadata{
		BucketName:    bucketName,
		ObjectKey:     objectKey,
		UserId:        c.userID,
		ContentLength: size,
	}

	err = stream.Send(&pb.PutObjectRequest{
		Data: &pb.PutObjectRequest_Metadata{Metadata: metadata},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to send metadata: %w", err)
	}

	// Send data in chunks
	buf := make([]byte, 32*1024) // 32KB chunks
	for {
		n, err := reader.Read(buf)
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("failed to read data: %w", err)
		}

		chunk := buf[:n]
		err = stream.Send(&pb.PutObjectRequest{
			Data: &pb.PutObjectRequest_Chunk{Chunk: chunk},
		})
		if err != nil {
			return nil, fmt.Errorf("failed to send chunk: %w", err)
		}
	}

	// Close and receive response
	resp, err := stream.CloseAndRecv()
	if err != nil {
		return nil, fmt.Errorf("failed to close stream: %w", err)
	}

	if !resp.Success {
		return nil, fmt.Errorf("upload failed: %s", resp.Error)
	}

	return resp, nil
}

// GetObject 下载对象
func (c *MinIOGRPCClient) GetObject(ctx context.Context, bucketName, objectKey string) ([]byte, error) {
	req := &pb.GetObjectRequest{
		BucketName: bucketName,
		ObjectKey:  objectKey,
		UserId:     c.userID,
	}

	stream, err := c.client.GetObject(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	var data bytes.Buffer
	for {
		resp, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("failed to receive chunk: %w", err)
		}

		// First message contains metadata, subsequent messages contain chunks
		if chunk := resp.GetChunk(); chunk != nil {
			data.Write(chunk)
		}
	}

	return data.Bytes(), nil
}

// StatObject 获取对象信息
func (c *MinIOGRPCClient) StatObject(ctx context.Context, bucketName, objectKey string) (*pb.ObjectInfo, error) {
	req := &pb.StatObjectRequest{
		BucketName: bucketName,
		ObjectKey:  objectKey,
		UserId:     c.userID,
	}

	resp, err := c.client.StatObject(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return nil, fmt.Errorf("stat object failed: %s", resp.Error)
	}

	return resp.ObjectInfo, nil
}

// DeleteObject 删除对象
func (c *MinIOGRPCClient) DeleteObject(ctx context.Context, bucketName, objectKey string) error {
	req := &pb.DeleteObjectRequest{
		BucketName: bucketName,
		ObjectKey:  objectKey,
		UserId:     c.userID,
	}

	resp, err := c.client.DeleteObject(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("delete object failed: %s", resp.Error)
	}

	return nil
}

// ListObjects 列出对象
func (c *MinIOGRPCClient) ListObjects(ctx context.Context, bucketName string, prefix string, recursive bool) ([]*pb.ObjectInfo, error) {
	req := &pb.ListObjectsRequest{
		BucketName: bucketName,
		UserId:     c.userID,
		Prefix:     prefix,
		Recursive:  recursive,
	}

	resp, err := c.client.ListObjects(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return nil, fmt.Errorf("list objects failed: %s", resp.Error)
	}

	return resp.Objects, nil
}

// CopyObject 复制对象
func (c *MinIOGRPCClient) CopyObject(ctx context.Context, srcBucket, srcKey, destBucket, destKey string) error {
	req := &pb.CopyObjectRequest{
		SourceBucket: srcBucket,
		SourceKey:    srcKey,
		DestBucket:   destBucket,
		DestKey:      destKey,
		UserId:       c.userID,
	}

	resp, err := c.client.CopyObject(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("copy object failed: %s", resp.Error)
	}

	return nil
}

// ============================================
// Presigned URLs
// ============================================

// GetPresignedURL 生成预签名下载 URL
func (c *MinIOGRPCClient) GetPresignedURL(ctx context.Context, bucketName, objectKey string, expirySeconds int32) (string, error) {
	req := &pb.GetPresignedURLRequest{
		BucketName:    bucketName,
		ObjectKey:     objectKey,
		UserId:        c.userID,
		ExpirySeconds: expirySeconds,
	}

	resp, err := c.client.GetPresignedURL(ctx, req)
	if err != nil {
		return "", fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return "", fmt.Errorf("generate presigned URL failed: %s", resp.Error)
	}

	return resp.Url, nil
}

// GetPresignedPutURL 生成预签名上传 URL
func (c *MinIOGRPCClient) GetPresignedPutURL(ctx context.Context, bucketName, objectKey string, expirySeconds int32) (string, error) {
	req := &pb.GetPresignedPutURLRequest{
		BucketName:    bucketName,
		ObjectKey:     objectKey,
		UserId:        c.userID,
		ExpirySeconds: expirySeconds,
	}

	resp, err := c.client.GetPresignedPutURL(ctx, req)
	if err != nil {
		return "", fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return "", fmt.Errorf("generate presigned PUT URL failed: %s", resp.Error)
	}

	return resp.Url, nil
}

// ============================================
// Health Check
// ============================================

// HealthCheck 健康检查
func (c *MinIOGRPCClient) HealthCheck(ctx context.Context) error {
	req := &pb.MinIOHealthCheckRequest{
		Detailed: false,
	}

	resp, err := c.client.HealthCheck(ctx, req)
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}

	if !resp.Healthy {
		return fmt.Errorf("MinIO service unhealthy: %s", resp.Status)
	}

	return nil
}
