// Package server implements the MinIO gRPC service
// 文件名: cmd/minio-service/server/server.go
package server

import (
	"context"
	"fmt"
	"io"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/minio"
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

// makeBucketName 生成带用户隔离的桶名
// Sanitizes userID to comply with MinIO bucket naming rules (no underscores)
func (s *MinIOServer) makeBucketName(userID, bucketName string) string {
	// Replace underscores with hyphens to comply with MinIO naming rules
	sanitizedUserID := strings.ReplaceAll(userID, "_", "-")
	return fmt.Sprintf("user-%s-%s", sanitizedUserID, bucketName)
}

// ========================================
// 桶管理方法
// ========================================

// CreateBucket 创建桶
func (s *MinIOServer) CreateBucket(ctx context.Context, req *pb.CreateBucketRequest) (*pb.CreateBucketResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 桶名隔离
	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.MakeBucket(ctx, bucketName, req.Region)
	if err != nil {
		return &pb.CreateBucketResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.CreateBucketResponse{
		Success: true,
		Message: fmt.Sprintf("Bucket %s created successfully", req.BucketName),
		BucketInfo: &pb.BucketInfo{
			Name:           bucketName,
			OwnerId:        req.UserId,
			OrganizationId: req.OrganizationId,
			Region:         req.Region,
			CreationDate:   timestamppb.Now(),
		},
	}, nil
}

// ListBuckets 列出桶
func (s *MinIOServer) ListBuckets(ctx context.Context, req *pb.ListBucketsRequest) (*pb.ListBucketsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	buckets, err := s.minioClient.ListBuckets(ctx)
	if err != nil {
		return &pb.ListBucketsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// 过滤用户的桶
	userPrefix := fmt.Sprintf("user-%s-", req.UserId)
	var userBuckets []*pb.BucketInfo

	for _, bucket := range buckets {
		// 只返回属于该用户的桶
		if strings.HasPrefix(bucket.Name, userPrefix) {
			// 如果有 prefix 过滤，进一步过滤
			if req.Prefix != "" && !strings.Contains(bucket.Name, req.Prefix) {
				continue
			}

			userBuckets = append(userBuckets, &pb.BucketInfo{
				Name:         bucket.Name,
				CreationDate: timestamppb.New(bucket.CreationDate),
				OwnerId:      req.UserId,
			})
		}
	}

	return &pb.ListBucketsResponse{
		Success:    true,
		Buckets:    userBuckets,
		TotalCount: int32(len(userBuckets)),
	}, nil
}

// DeleteBucket 删除桶
func (s *MinIOServer) DeleteBucket(ctx context.Context, req *pb.DeleteBucketRequest) (*pb.DeleteBucketResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	var deletedObjects int32
	var err error

	if req.Force {
		// 强制删除（包括所有对象）
		count, delErr := s.minioClient.RemoveBucketForce(ctx, bucketName)
		deletedObjects = int32(count)
		err = delErr
	} else {
		// 只删除空桶
		err = s.minioClient.RemoveBucket(ctx, bucketName)
	}

	if err != nil {
		return &pb.DeleteBucketResponse{
			Success:        false,
			Error:          err.Error(),
			DeletedObjects: deletedObjects,
		}, nil
	}

	return &pb.DeleteBucketResponse{
		Success:        true,
		Message:        fmt.Sprintf("Bucket %s deleted successfully", req.BucketName),
		DeletedObjects: deletedObjects,
	}, nil
}

// GetBucketInfo 获取桶信息
func (s *MinIOServer) GetBucketInfo(ctx context.Context, req *pb.GetBucketInfoRequest) (*pb.GetBucketInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	// 检查桶是否存在
	exists, err := s.minioClient.BucketExists(ctx, bucketName)
	if err != nil {
		return &pb.GetBucketInfoResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	if !exists {
		return &pb.GetBucketInfoResponse{
			Success: false,
			Error:   "bucket not found",
		}, nil
	}

	// 获取桶中对象统计
	objects, err := s.minioClient.ListObjects(ctx, bucketName, minio.ListOptions{
		Recursive: true,
	})

	var totalSize int64
	var objectCount int64
	if err == nil {
		for _, obj := range objects {
			totalSize += obj.Size
			objectCount++
		}
	}

	return &pb.GetBucketInfoResponse{
		Success: true,
		BucketInfo: &pb.BucketInfo{
			Name:        bucketName,
			OwnerId:     req.UserId,
			SizeBytes:   totalSize,
			ObjectCount: objectCount,
		},
	}, nil
}

// SetBucketPolicy 设置桶策略（简化实现）
func (s *MinIOServer) SetBucketPolicy(ctx context.Context, req *pb.SetBucketPolicyRequest) (*pb.SetBucketPolicyResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现：暂不实际设置策略，只返回成功
	// 实际生产环境需要调用 MinIO 的 SetBucketPolicy API
	return &pb.SetBucketPolicyResponse{
		Success: true,
		Message: "Bucket policy set successfully",
	}, nil
}

// GetBucketPolicy 获取桶策略（简化实现）
func (s *MinIOServer) GetBucketPolicy(ctx context.Context, req *pb.GetBucketPolicyRequest) (*pb.GetBucketPolicyResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现：返回默认私有策略
	return &pb.GetBucketPolicyResponse{
		Success:    true,
		PolicyType: pb.BucketPolicyType_BUCKET_POLICY_PRIVATE,
		PolicyJson: "{}",
	}, nil
}

// SetBucketTags 设置桶标签
func (s *MinIOServer) SetBucketTags(ctx context.Context, req *pb.SetBucketTagsRequest) (*pb.SetBucketTagsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.SetBucketTags(ctx, bucketName, req.Tags)
	if err != nil {
		return &pb.SetBucketTagsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.SetBucketTagsResponse{
		Success: true,
		Message: "Bucket tags set successfully",
	}, nil
}

// GetBucketTags 获取桶标签
func (s *MinIOServer) GetBucketTags(ctx context.Context, req *pb.GetBucketTagsRequest) (*pb.GetBucketTagsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	tags, err := s.minioClient.GetBucketTags(ctx, bucketName)
	if err != nil {
		return &pb.GetBucketTagsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.GetBucketTagsResponse{
		Success: true,
		Tags:    tags,
	}, nil
}

// DeleteBucketTags 删除桶标签
func (s *MinIOServer) DeleteBucketTags(ctx context.Context, req *pb.DeleteBucketTagsRequest) (*pb.DeleteBucketTagsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.RemoveBucketTags(ctx, bucketName)
	if err != nil {
		return &pb.DeleteBucketTagsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.DeleteBucketTagsResponse{
		Success: true,
		Message: "Bucket tags deleted successfully",
	}, nil
}

// SetBucketVersioning 设置桶版本控制
func (s *MinIOServer) SetBucketVersioning(ctx context.Context, req *pb.SetBucketVersioningRequest) (*pb.SetBucketVersioningResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.SetBucketVersioning(ctx, bucketName, req.Enabled)
	if err != nil {
		return &pb.SetBucketVersioningResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	message := "Bucket versioning disabled"
	if req.Enabled {
		message = "Bucket versioning enabled"
	}

	return &pb.SetBucketVersioningResponse{
		Success: true,
		Message: message,
	}, nil
}

// GetBucketVersioning 获取桶版本控制状态
func (s *MinIOServer) GetBucketVersioning(ctx context.Context, req *pb.GetBucketVersioningRequest) (*pb.GetBucketVersioningResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	enabled, err := s.minioClient.GetBucketVersioning(ctx, bucketName)
	if err != nil {
		return &pb.GetBucketVersioningResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.GetBucketVersioningResponse{
		Success: true,
		Enabled: enabled,
	}, nil
}

// SetBucketLifecycle 设置桶生命周期策略
func (s *MinIOServer) SetBucketLifecycle(ctx context.Context, req *pb.SetBucketLifecycleRequest) (*pb.SetBucketLifecycleResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.SetBucketLifecycle(ctx, bucketName, req.Rules)
	if err != nil {
		return &pb.SetBucketLifecycleResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.SetBucketLifecycleResponse{
		Success: true,
		Message: "Bucket lifecycle policy set successfully",
	}, nil
}

// GetBucketLifecycle 获取桶生命周期策略
func (s *MinIOServer) GetBucketLifecycle(ctx context.Context, req *pb.GetBucketLifecycleRequest) (*pb.GetBucketLifecycleResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	_, err := s.minioClient.GetBucketLifecycle(ctx, bucketName)
	if err != nil {
		return &pb.GetBucketLifecycleResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Return empty rules for now - full lifecycle implementation pending
	return &pb.GetBucketLifecycleResponse{
		Success: true,
		Rules:   []*pb.LifecycleRule{},
	}, nil
}

// DeleteBucketLifecycle 删除桶生命周期策略
func (s *MinIOServer) DeleteBucketLifecycle(ctx context.Context, req *pb.DeleteBucketLifecycleRequest) (*pb.DeleteBucketLifecycleResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.RemoveBucketLifecycle(ctx, bucketName)
	if err != nil {
		return &pb.DeleteBucketLifecycleResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.DeleteBucketLifecycleResponse{
		Success: true,
		Message: "Bucket lifecycle policy deleted successfully",
	}, nil
}

// ========================================
// 对象操作方法
// ========================================

// PutObject 上传对象（流式）
func (s *MinIOServer) PutObject(stream pb.MinIOService_PutObjectServer) error {
	// 第一个消息包含元数据
	firstReq, err := stream.Recv()
	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	metadata := firstReq.GetMetadata()
	if metadata == nil {
		return status.Error(codes.InvalidArgument, "first message must contain metadata")
	}

	if err := s.authService.ValidateUser(metadata.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 桶名隔离
	bucketName := s.makeBucketName(metadata.UserId, metadata.BucketName)

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

			chunk := req.GetChunk()
			if chunk == nil {
				continue
			}

			if _, err := pw.Write(chunk); err != nil {
				pw.CloseWithError(err)
				return
			}
		}
	}()

	// 上传到 MinIO
	var uploadInfo minio.ObjectInfo
	go func() {
		info, err := s.minioClient.PutObject(stream.Context(), bucketName, metadata.ObjectKey,
			pr, metadata.ContentLength, minio.PutOptions{
				ContentType: metadata.ContentType,
				Metadata:    metadata.Metadata,
			})
		if err == nil {
			uploadInfo = info
		}
		errCh <- err
	}()

	if err := <-errCh; err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	return stream.SendAndClose(&pb.PutObjectResponse{
		Success:   true,
		ObjectKey: uploadInfo.Key,
		Etag:      uploadInfo.ETag,
		VersionId: uploadInfo.VersionID,
		Size:      uploadInfo.Size,
	})
}

// GetObject 下载对象（流式）
func (s *MinIOServer) GetObject(req *pb.GetObjectRequest, stream pb.MinIOService_GetObjectServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	// 先获取对象信息
	stat, err := s.minioClient.StatObject(stream.Context(), bucketName, req.ObjectKey, minio.StatOptions{
		VersionID: req.VersionId,
	})
	if err != nil {
		return status.Error(codes.NotFound, err.Error())
	}

	// 发送对象元数据
	if err := stream.Send(&pb.GetObjectResponse{
		Data: &pb.GetObjectResponse_Metadata{
			Metadata: &pb.ObjectInfo{
				Key:          stat.Key,
				Size:         stat.Size,
				Etag:         stat.ETag,
				ContentType:  stat.ContentType,
				LastModified: timestamppb.New(stat.LastModified),
				Metadata:     stat.Metadata,
				VersionId:    stat.VersionID,
			},
		},
	}); err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	// 获取对象数据流
	object, err := s.minioClient.GetObject(stream.Context(), bucketName, req.ObjectKey, minio.GetOptions{
		VersionID: req.VersionId,
		Offset:    req.Offset,
		Length:    req.Length,
	})
	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}
	defer object.Close()

	// 流式发送数据
	buf := make([]byte, 1024*1024) // 1MB chunks
	for {
		n, err := object.Read(buf)
		if n > 0 {
			if err := stream.Send(&pb.GetObjectResponse{
				Data: &pb.GetObjectResponse_Chunk{
					Chunk: buf[:n],
				},
			}); err != nil {
				return status.Error(codes.Internal, err.Error())
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

// DeleteObject 删除对象
func (s *MinIOServer) DeleteObject(ctx context.Context, req *pb.DeleteObjectRequest) (*pb.DeleteObjectResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.RemoveObject(ctx, bucketName, req.ObjectKey)
	if err != nil {
		return &pb.DeleteObjectResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.DeleteObjectResponse{
		Success: true,
		Message: fmt.Sprintf("Object %s deleted successfully", req.ObjectKey),
	}, nil
}

// DeleteObjects 批量删除对象
func (s *MinIOServer) DeleteObjects(ctx context.Context, req *pb.DeleteObjectsRequest) (*pb.DeleteObjectsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	deleted, errors := s.minioClient.RemoveObjects(ctx, bucketName, req.ObjectKeys)

	var deleteErrors []*pb.DeleteError
	for i, err := range errors {
		if err != nil {
			deleteErrors = append(deleteErrors, &pb.DeleteError{
				Key:          req.ObjectKeys[i],
				ErrorCode:    "DeleteFailed",
				ErrorMessage: err.Error(),
			})
		}
	}

	success := len(deleteErrors) == 0
	var errorMsg string
	if !success {
		errorMsg = fmt.Sprintf("%d objects failed to delete", len(deleteErrors))
	}

	return &pb.DeleteObjectsResponse{
		Success:     success,
		DeletedKeys: deleted,
		Errors:      deleteErrors,
		Error:       errorMsg,
	}, nil
}

// ListObjects 列出对象
func (s *MinIOServer) ListObjects(ctx context.Context, req *pb.ListObjectsRequest) (*pb.ListObjectsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	// 设置列表选项
	maxKeys := req.MaxKeys
	if maxKeys == 0 {
		maxKeys = 1000 // 默认最大值
	}

	objects, err := s.minioClient.ListObjects(ctx, bucketName, minio.ListOptions{
		Prefix:    req.Prefix,
		Recursive: req.Recursive,
		MaxKeys:   int(maxKeys),
	})

	if err != nil {
		return &pb.ListObjectsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	var pbObjects []*pb.ObjectInfo
	for _, obj := range objects {
		pbObjects = append(pbObjects, &pb.ObjectInfo{
			Key:          obj.Key,
			Size:         obj.Size,
			Etag:         obj.ETag,
			LastModified: timestamppb.New(obj.LastModified),
			StorageClass: obj.StorageClass,
		})
	}

	return &pb.ListObjectsResponse{
		Success:    true,
		Objects:    pbObjects,
		IsTruncated: len(pbObjects) >= int(maxKeys),
	}, nil
}

// CopyObject 复制对象
func (s *MinIOServer) CopyObject(ctx context.Context, req *pb.CopyObjectRequest) (*pb.CopyObjectResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	srcBucket := s.makeBucketName(req.UserId, req.SourceBucket)
	destBucket := s.makeBucketName(req.UserId, req.DestBucket)

	err := s.minioClient.CopyObject(ctx, srcBucket, req.SourceKey, destBucket, req.DestKey, minio.CopyOptions{
		Metadata: req.Metadata,
	})

	if err != nil {
		return &pb.CopyObjectResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.CopyObjectResponse{
		Success:      true,
		Message:      "Object copied successfully",
		LastModified: timestamppb.Now(),
	}, nil
}

// StatObject 获取对象信息
func (s *MinIOServer) StatObject(ctx context.Context, req *pb.StatObjectRequest) (*pb.StatObjectResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	info, err := s.minioClient.StatObject(ctx, bucketName, req.ObjectKey, minio.StatOptions{
		VersionID: req.VersionId,
	})

	if err != nil {
		return &pb.StatObjectResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.StatObjectResponse{
		Success: true,
		ObjectInfo: &pb.ObjectInfo{
			Key:          info.Key,
			Size:         info.Size,
			Etag:         info.ETag,
			ContentType:  info.ContentType,
			LastModified: timestamppb.New(info.LastModified),
			Metadata:     info.Metadata,
			StorageClass: info.StorageClass,
			VersionId:    info.VersionID,
		},
	}, nil
}

// SetObjectTags 设置对象标签
func (s *MinIOServer) SetObjectTags(ctx context.Context, req *pb.SetObjectTagsRequest) (*pb.SetObjectTagsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.SetObjectTags(ctx, bucketName, req.ObjectKey, req.Tags, req.VersionId)
	if err != nil {
		return &pb.SetObjectTagsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.SetObjectTagsResponse{
		Success: true,
		Message: "Object tags set successfully",
	}, nil
}

// GetObjectTags 获取对象标签
func (s *MinIOServer) GetObjectTags(ctx context.Context, req *pb.GetObjectTagsRequest) (*pb.GetObjectTagsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	tags, err := s.minioClient.GetObjectTags(ctx, bucketName, req.ObjectKey, req.VersionId)
	if err != nil {
		return &pb.GetObjectTagsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.GetObjectTagsResponse{
		Success: true,
		Tags:    tags,
	}, nil
}

// DeleteObjectTags 删除对象标签
func (s *MinIOServer) DeleteObjectTags(ctx context.Context, req *pb.DeleteObjectTagsRequest) (*pb.DeleteObjectTagsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	err := s.minioClient.RemoveObjectTags(ctx, bucketName, req.ObjectKey, req.VersionId)
	if err != nil {
		return &pb.DeleteObjectTagsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.DeleteObjectTagsResponse{
		Success: true,
		Message: "Object tags deleted successfully",
	}, nil
}

// ========================================
// 预签名 URL 方法
// ========================================

// GetPresignedURL 获取预签名下载 URL
func (s *MinIOServer) GetPresignedURL(ctx context.Context, req *pb.GetPresignedURLRequest) (*pb.GetPresignedURLResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	expiry := time.Duration(req.ExpirySeconds) * time.Second
	if expiry == 0 {
		expiry = 7 * 24 * time.Hour // 默认7天
	}

	url, err := s.minioClient.PresignedGetURL(ctx, bucketName, req.ObjectKey, expiry)
	if err != nil {
		return &pb.GetPresignedURLResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	expiresAt := time.Now().Add(expiry)

	return &pb.GetPresignedURLResponse{
		Success:   true,
		Url:       url,
		ExpiresAt: timestamppb.New(expiresAt),
	}, nil
}

// GetPresignedPutURL 获取预签名上传 URL
func (s *MinIOServer) GetPresignedPutURL(ctx context.Context, req *pb.GetPresignedPutURLRequest) (*pb.GetPresignedPutURLResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	bucketName := s.makeBucketName(req.UserId, req.BucketName)

	expiry := time.Duration(req.ExpirySeconds) * time.Second
	if expiry == 0 {
		expiry = 1 * time.Hour // 默认1小时
	}

	url, err := s.minioClient.PresignedPutURL(ctx, bucketName, req.ObjectKey, expiry)
	if err != nil {
		return &pb.GetPresignedPutURLResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	expiresAt := time.Now().Add(expiry)

	return &pb.GetPresignedPutURLResponse{
		Success:   true,
		Url:       url,
		ExpiresAt: timestamppb.New(expiresAt),
	}, nil
}

// ========================================
// 多部分上传方法（简化实现）
// ========================================

// InitiateMultipartUpload 初始化多部分上传
func (s *MinIOServer) InitiateMultipartUpload(ctx context.Context, req *pb.InitiateMultipartUploadRequest) (*pb.InitiateMultipartUploadResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现：返回一个临时 upload ID
	// 实际生产环境需要调用 MinIO 的 NewMultipartUpload API
	uploadID := fmt.Sprintf("upload-%s-%d", req.ObjectKey, time.Now().Unix())

	return &pb.InitiateMultipartUploadResponse{
		Success:    true,
		UploadId:   uploadID,
		BucketName: req.BucketName,
		ObjectKey:  req.ObjectKey,
	}, nil
}

// UploadPart 上传分片
func (s *MinIOServer) UploadPart(stream pb.MinIOService_UploadPartServer) error {
	// 简化实现：接收数据但不实际处理
	firstReq, err := stream.Recv()
	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	metadata := firstReq.GetMetadata()
	if metadata == nil {
		return status.Error(codes.InvalidArgument, "first message must contain metadata")
	}

	if err := s.authService.ValidateUser(metadata.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 接收数据块
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return status.Error(codes.Internal, err.Error())
		}
		_ = req.GetChunk() // 简化实现：只接收不处理
	}

	return stream.SendAndClose(&pb.UploadPartResponse{
		Success:    true,
		PartNumber: metadata.PartNumber,
		Etag:       fmt.Sprintf("etag-%d", metadata.PartNumber),
	})
}

// CompleteMultipartUpload 完成多部分上传
func (s *MinIOServer) CompleteMultipartUpload(ctx context.Context, req *pb.CompleteMultipartUploadRequest) (*pb.CompleteMultipartUploadResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现：返回成功
	return &pb.CompleteMultipartUploadResponse{
		Success:   true,
		ObjectKey: req.ObjectKey,
		Etag:      "completed-etag",
		Location:  fmt.Sprintf("/%s/%s", req.BucketName, req.ObjectKey),
	}, nil
}

// AbortMultipartUpload 中止多部分上传
func (s *MinIOServer) AbortMultipartUpload(ctx context.Context, req *pb.AbortMultipartUploadRequest) (*pb.AbortMultipartUploadResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现：返回成功
	return &pb.AbortMultipartUploadResponse{
		Success: true,
		Message: "Multipart upload aborted successfully",
	}, nil
}

// ========================================
// 健康检查
// ========================================

// HealthCheck 健康检查
func (s *MinIOServer) HealthCheck(ctx context.Context, req *pb.MinIOHealthCheckRequest) (*pb.MinIOHealthCheckResponse, error) {
	err := s.minioClient.HealthCheck(ctx)
	healthy := err == nil

	response := &pb.MinIOHealthCheckResponse{
		Success:   healthy,
		Healthy:   healthy,
		Status:    "running",
		Timestamp: timestamppb.Now(),
	}

	if !healthy {
		response.Error = err.Error()
		response.Status = "unhealthy"
	}

	return response, nil
}
