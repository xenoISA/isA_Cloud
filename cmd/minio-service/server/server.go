// Package server implements the MinIO gRPC service
// 文件名: cmd/minio-service/server/server.go
package server

import (
	"context"
	"fmt"
	"io"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
	"github.com/isa-cloud/isa_cloud/pkg/storage/minio"
)

// MinIOServer MinIO gRPC 服务实现
type MinIOServer struct {
	pb.UnimplementedMinIOServiceServer

	minioClient *minio.Client
	authService *AuthService
	config      *storage.StorageConfig
}

// NewMinIOServer 创建 MinIO gRPC 服务实例
func NewMinIOServer(minioClient *minio.Client, cfg *storage.StorageConfig) (*MinIOServer, error) {
	return &MinIOServer{
		minioClient: minioClient,
		authService: NewAuthService(cfg),
		config:      cfg,
	}, nil
}

// CreateBucket 创建桶
func (s *MinIOServer) CreateBucket(ctx context.Context, req *pb.CreateBucketRequest) (*pb.CreateBucketResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 桶名隔离
	bucketName := fmt.Sprintf("user-%s-%s", req.UserId, req.BucketName)

	err := s.minioClient.MakeBucket(ctx, bucketName, minio.MakeBucketOptions{Region: req.Region})
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.CreateBucketResponse{
		Success: true,
		Bucket: &pb.BucketInfo{
			Name:    bucketName,
			OwnerId: req.UserId,
		},
	}, nil
}

// PutObject 上传对象（流式）
func (s *MinIOServer) PutObject(stream pb.MinIOService_PutObjectServer) error {
	// 第一个消息包含元数据
	firstReq, err := stream.Recv()
	if err != nil {
		return err
	}

	metadata := firstReq.GetMetadata()
	if err := s.authService.ValidateUser(metadata.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 桶名隔离
	bucketName := fmt.Sprintf("user-%s-%s", metadata.UserId, metadata.BucketName)

	// 接收数据流
	pr, pw := io.Pipe()
	errCh := make(chan error, 1)

	go func() {
		defer pw.Close()
		for {
			req, err := stream.Recv()
			if err == io.EOF {
				return
			}
			if err != nil {
				pw.CloseWithError(err)
				return
			}

			chunk := req.GetChunkData()
			if _, err := pw.Write(chunk); err != nil {
				pw.CloseWithError(err)
				return
			}
		}
	}()

	// 上传到 MinIO
	go func() {
		_, err := s.minioClient.PutObject(stream.Context(), bucketName, metadata.ObjectKey,
			pr, metadata.ContentLength, minio.PutOptions{
				ContentType: metadata.ContentType,
			})
		errCh <- err
	}()

	if err := <-errCh; err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	return stream.SendAndClose(&pb.PutObjectResponse{
		Success: true,
		Object: &pb.ObjectInfo{
			Key:     metadata.ObjectKey,
			Size:    metadata.ContentLength,
			OwnerId: metadata.UserId,
		},
	})
}

// GetObject 下载对象（流式）
func (s *MinIOServer) GetObject(req *pb.GetObjectRequest, stream pb.MinIOService_GetObjectServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := fmt.Sprintf("user-%s-%s", req.UserId, req.BucketName)

	object, err := s.minioClient.GetObject(stream.Context(), bucketName, req.ObjectKey, minio.GetObjectOptions{})
	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}
	defer object.Close()

	buf := make([]byte, 1024*1024) // 1MB chunks
	for {
		n, err := object.Read(buf)
		if n > 0 {
			if err := stream.Send(&pb.GetObjectResponse{
				ChunkData: buf[:n],
			}); err != nil {
				return err
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return status.Error(codes.Internal, err.Error())
		}
	}

	return nil
}

// HealthCheck 健康检查
func (s *MinIOServer) HealthCheck(ctx context.Context, req *pb.HealthCheckRequest) (*pb.HealthCheckResponse, error) {
	err := s.minioClient.HealthCheck(ctx)
	return &pb.HealthCheckResponse{
		Healthy: err == nil,
		Service: "minio",
	}, nil
}


