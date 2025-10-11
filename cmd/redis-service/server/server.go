// Package server implements the Redis gRPC service
// 实现 Redis gRPC 服务端
//
// 文件名: cmd/redis-service/server/server.go
//
// 核心功能：
// - 实现 proto 定义的所有 RPC 方法
// - 调用底层 Redis SDK 客户端
// - 用户认证和权限验证
// - 多租户数据隔离
// - 审计日志记录
//
// 注意: 需要先运行 protoc 生成 pb.go 文件
//
//	protoc --go_out=. --go-grpc_out=. api/proto/redis_service.proto
package server

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/cache"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/cache/redis"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

// RedisServer Redis gRPC 服务实现
type RedisServer struct {
	pb.UnimplementedRedisServiceServer

	redisClient *redis.Client
	lokiClient  *loki.Client
	authService *AuthService
	config      *cache.CacheConfig
}

// NewRedisServer 创建 Redis gRPC 服务实例
func NewRedisServer(redisClient *redis.Client, cfg *cache.CacheConfig) (*RedisServer, error) {
	// 创建 Loki 客户端（用于审计日志）
	lokiClient, err := createLokiClient(cfg)
	if err != nil {
		// Loki 不可用时仅记录警告，不影响服务启动
		fmt.Printf("Warning: Failed to create Loki client: %v\n", err)
	}

	return &RedisServer{
		redisClient: redisClient,
		lokiClient:  lokiClient,
		authService: NewAuthService(cfg),
		config:      cfg,
	}, nil
}

// ============================================
// 字符串操作实现
// ============================================

// Set 设置键值
func (s *RedisServer) Set(ctx context.Context, req *pb.SetRequest) (*pb.SetResponse, error) {
	// 1. 验证用户权限
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 2. 添加命名空间隔离
	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	// 3. 调用 Redis SDK
	err := s.redisClient.Set(ctx, isolatedKey, req.Value, 0)
	if err != nil {
		s.logError(req.UserId, "Set", err)
		return nil, status.Error(codes.Internal, err.Error())
	}

	// 4. 记录审计日志
	s.logAudit(req.UserId, "Set", map[string]string{
		"key":   req.Key,
		"value": req.Value,
	})

	return &pb.SetResponse{
		Success: true,
		Message: "Key set successfully",
	}, nil
}

// Get 获取键值
func (s *RedisServer) Get(ctx context.Context, req *pb.GetRequest) (*pb.GetResponse, error) {
	// 验证权限
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 添加命名空间隔离
	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	// 调用 Redis SDK
	value, err := s.redisClient.Get(ctx, isolatedKey)
	if err != nil {
		// Redis Nil 表示键不存在，不是错误
		if err.Error() == "redis: nil" {
			return &pb.GetResponse{
				Found: false,
				Value: "",
			}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.GetResponse{
		Found: true,
		Value: value,
	}, nil
}

// SetWithExpiration 设置带过期时间的键值
func (s *RedisServer) SetWithExpiration(ctx context.Context, req *pb.SetWithExpirationRequest) (*pb.SetResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)
	expiration := req.Expiration.AsDuration()

	err := s.redisClient.Set(ctx, isolatedKey, req.Value, expiration)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	s.logAudit(req.UserId, "SetWithExpiration", map[string]string{
		"key": req.Key,
		"ttl": expiration.String(),
	})

	return &pb.SetResponse{
		Success: true,
		Message: "Key set with expiration",
	}, nil
}

// Increment 递增
func (s *RedisServer) Increment(ctx context.Context, req *pb.IncrementRequest) (*pb.IncrementResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)
	delta := req.Delta
	if delta == 0 {
		delta = 1
	}

	value, err := s.redisClient.Increment(ctx, isolatedKey, delta)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.IncrementResponse{
		Value: value,
	}, nil
}

// ============================================
// 哈希操作实现
// ============================================

// HSet 设置哈希字段
func (s *RedisServer) HSet(ctx context.Context, req *pb.HSetRequest) (*pb.HSetResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	// 转换 fields 为 interface{} 切片
	var values []interface{}
	for _, field := range req.Fields {
		values = append(values, field.Field, field.Value)
	}

	err := s.redisClient.HSet(ctx, isolatedKey, values...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HSetResponse{
		Success:   true,
		FieldsSet: int32(len(req.Fields)),
	}, nil
}

// HGet 获取哈希字段值
func (s *RedisServer) HGet(ctx context.Context, req *pb.HGetRequest) (*pb.HGetResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	value, err := s.redisClient.HGet(ctx, isolatedKey, req.Field)
	if err != nil {
		if err.Error() == "redis: nil" {
			return &pb.HGetResponse{Found: false}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HGetResponse{
		Found: true,
		Value: value,
	}, nil
}

// ============================================
// 分布式锁实现
// ============================================

// AcquireLock 获取分布式锁
func (s *RedisServer) AcquireLock(ctx context.Context, req *pb.AcquireLockRequest) (*pb.AcquireLockResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.LockKey)
	ttl := req.Ttl.AsDuration()

	lock, err := s.redisClient.AcquireLock(ctx, isolatedKey, ttl)
	if err != nil {
		return &pb.AcquireLockResponse{
			Acquired: false,
		}, nil
	}

	s.logAudit(req.UserId, "AcquireLock", map[string]string{
		"lock_key": req.LockKey,
		"ttl":      ttl.String(),
	})

	return &pb.AcquireLockResponse{
		Acquired:  true,
		LockId:    lock.value,
		ExpiresAt: timestamppb.New(time.Now().Add(ttl)),
	}, nil
}

// ReleaseLock 释放锁
func (s *RedisServer) ReleaseLock(ctx context.Context, req *pb.ReleaseLockRequest) (*pb.ReleaseLockResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.LockKey)

	// 创建锁对象来释放
	lock := &redis.Lock{
		Key:    isolatedKey,
		Value:  req.LockId,
		client: s.redisClient,
	}

	err := lock.Release(ctx)
	return &pb.ReleaseLockResponse{
		Released: err == nil,
	}, nil
}

// ============================================
// 键操作实现
// ============================================

// Delete 删除键
func (s *RedisServer) Delete(ctx context.Context, req *pb.DeleteRequest) (*pb.DeleteResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	err := s.redisClient.Delete(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.DeleteResponse{
		Success:      true,
		DeletedCount: 1,
	}, nil
}

// Exists 检查键是否存在
func (s *RedisServer) Exists(ctx context.Context, req *pb.ExistsRequest) (*pb.ExistsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	exists, err := s.redisClient.Exists(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ExistsResponse{
		Exists: exists,
	}, nil
}

// Expire 设置过期时间
func (s *RedisServer) Expire(ctx context.Context, req *pb.ExpireRequest) (*pb.ExpireResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)
	expiration := req.Expiration.AsDuration()

	err := s.redisClient.Expire(ctx, isolatedKey, expiration)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ExpireResponse{
		Success: true,
	}, nil
}

// GetTTL 获取剩余生存时间
func (s *RedisServer) GetTTL(ctx context.Context, req *pb.GetTTLRequest) (*pb.GetTTLResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	ttl, err := s.redisClient.GetTTL(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.GetTTLResponse{
		TtlSeconds: int64(ttl.Seconds()),
	}, nil
}

// ============================================
// Pub/Sub 实现
// ============================================

// Publish 发布消息
func (s *RedisServer) Publish(ctx context.Context, req *pb.PublishRequest) (*pb.PublishResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 添加频道隔离
	isolatedChannel := s.isolateChannel(req.UserId, req.OrganizationId, req.Channel)

	err := s.redisClient.Publish(ctx, isolatedChannel, req.Message)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.PublishResponse{
		SubscriberCount: 0, // Redis Publish 命令返回订阅者数
	}, nil
}

// Subscribe 订阅频道（流式返回）
func (s *RedisServer) Subscribe(req *pb.SubscribeRequest, stream pb.RedisService_SubscribeServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 添加频道隔离
	var isolatedChannels []string
	for _, channel := range req.Channels {
		isolatedChannels = append(isolatedChannels,
			s.isolateChannel(req.UserId, req.OrganizationId, channel))
	}

	// 订阅 Redis
	pubsub := s.redisClient.Subscribe(stream.Context(), isolatedChannels...)
	defer pubsub.Close()

	// 流式发送消息
	ch := pubsub.Channel()
	for {
		select {
		case msg := <-ch:
			// 移除隔离前缀，返回原始频道名
			originalChannel := s.deisolateChannel(req.UserId, req.OrganizationId, msg.Channel)

			response := &pb.MessageResponse{
				Channel:   originalChannel,
				Message:   msg.Payload,
				Timestamp: timestamppb.Now(),
			}

			if err := stream.Send(response); err != nil {
				return err
			}

		case <-stream.Context().Done():
			return nil
		}
	}
}

// ============================================
// 健康检查
// ============================================

// HealthCheck 健康检查
func (s *RedisServer) HealthCheck(ctx context.Context, req *pb.RedisHealthCheckRequest) (*pb.RedisHealthCheckResponse, error) {
	// Ping Redis
	err := s.redisClient.Ping(ctx)
	if err != nil {
		return &pb.RedisHealthCheckResponse{
			Healthy:     false,
			RedisStatus: "unhealthy",
			Message:     err.Error(),
			CheckedAt:   timestamppb.Now(),
		}, nil
	}

	// 深度检查
	if req.DeepCheck {
		// 尝试读写操作
		testKey := fmt.Sprintf("healthcheck:%d", time.Now().UnixNano())
		err := s.redisClient.Set(ctx, testKey, "test", 10*time.Second)
		if err != nil {
			return &pb.RedisHealthCheckResponse{
				Healthy:     false,
				RedisStatus: "unhealthy",
				Message:     "write test failed",
				CheckedAt:   timestamppb.Now(),
			}, nil
		}

		_, err = s.redisClient.Get(ctx, testKey)
		if err != nil {
			return &pb.RedisHealthCheckResponse{
				Healthy:     false,
				RedisStatus: "unhealthy",
				Message:     "read test failed",
				CheckedAt:   timestamppb.Now(),
			}, nil
		}

		s.redisClient.Delete(ctx, testKey)
	}

	return &pb.RedisHealthCheckResponse{
		Healthy:          true,
		RedisStatus:      "healthy",
		ConnectedClients: 0, // 可以从 INFO 命令获取
		CheckedAt:        timestamppb.Now(),
		Message:          "Redis is healthy",
	}, nil
}

// ============================================
// 辅助方法
// ============================================

// isolateKey 添加命名空间隔离
//
// 格式: org-{org_id}:user-{user_id}:{original_key}
//
// 例子:
//
//	原始: "session:abc"
//	隔离后: "org-456:user-123:session:abc"
func (s *RedisServer) isolateKey(userID, orgID, key string) string {
	if orgID != "" {
		return fmt.Sprintf("org-%s:user-%s:%s", orgID, userID, key)
	}
	return fmt.Sprintf("user-%s:%s", userID, key)
}

// isolateChannel 添加频道隔离
func (s *RedisServer) isolateChannel(userID, orgID, channel string) string {
	if orgID != "" {
		return fmt.Sprintf("org-%s:user-%s:%s", orgID, userID, channel)
	}
	return fmt.Sprintf("user-%s:%s", userID, channel)
}

// deisolateChannel 移除频道隔离前缀
func (s *RedisServer) deisolateChannel(userID, orgID, isolatedChannel string) string {
	var prefix string
	if orgID != "" {
		prefix = fmt.Sprintf("org-%s:user-%s:", orgID, userID)
	} else {
		prefix = fmt.Sprintf("user-%s:", userID)
	}

	return strings.TrimPrefix(isolatedChannel, prefix)
}

// logAudit 记录审计日志到 Loki
func (s *RedisServer) logAudit(userID, operation string, metadata map[string]string) {
	if s.lokiClient == nil {
		return
	}

	labels := map[string]string{
		"service":   "redis-grpc-service",
		"user_id":   userID,
		"operation": operation,
	}
	for k, v := range metadata {
		labels[k] = v
	}

	s.lokiClient.PushLog("redis", "info",
		fmt.Sprintf("User %s executed %s", userID, operation),
		labels)
}

// logError 记录错误日志
func (s *RedisServer) logError(userID, operation string, err error) {
	if s.lokiClient == nil {
		return
	}

	s.lokiClient.PushLog("redis", "error",
		fmt.Sprintf("User %s failed %s: %v", userID, operation, err),
		map[string]string{
			"service":   "redis-grpc-service",
			"user_id":   userID,
			"operation": operation,
		})
}

// createLokiClient 创建 Loki 客户端
func createLokiClient(cfg *cache.CacheConfig) (*loki.Client, error) {
	// 从环境变量或配置获取 Loki 地址
	lokiURL := os.Getenv("LOKI_URL")
	if lokiURL == "" {
		lokiURL = "http://localhost:3100"
	}

	lokiCfg := &loki.Config{
		URL:       lokiURL,
		BatchSize: 100,
		BatchWait: 1 * time.Second,
		StaticLabels: map[string]string{
			"service": "redis-grpc-service",
		},
	}

	return loki.NewClient(lokiCfg)
}
