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

	goredis "github.com/redis/go-redis/v9"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/redis"
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

// GetMultiple 批量获取键值
func (s *RedisServer) GetMultiple(ctx context.Context, req *pb.GetMultipleRequest) (*pb.GetMultipleResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var isolatedKeys []string
	for _, key := range req.Keys {
		isolatedKeys = append(isolatedKeys, s.isolateKey(req.UserId, req.OrganizationId, key))
	}

	values, err := s.redisClient.GetMultiple(ctx, isolatedKeys)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	var keyValues []*pb.KeyValue
	for i, val := range values {
		if val != nil {
			if strVal, ok := val.(string); ok && strVal != "" {
				keyValues = append(keyValues, &pb.KeyValue{
					Key:   req.Keys[i],
					Value: strVal,
				})
			}
		}
	}

	return &pb.GetMultipleResponse{
		Values: keyValues,
	}, nil
}

// Decrement 递减
func (s *RedisServer) Decrement(ctx context.Context, req *pb.DecrementRequest) (*pb.DecrementResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)
	delta := req.Delta
	if delta == 0 {
		delta = 1
	}

	value, err := s.redisClient.Decrement(ctx, isolatedKey, delta)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.DecrementResponse{
		Value: value,
	}, nil
}

// Append 追加值到键
func (s *RedisServer) Append(ctx context.Context, req *pb.AppendRequest) (*pb.AppendResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	length, err := s.redisClient.Append(ctx, isolatedKey, req.Value)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.AppendResponse{
		Length: length,
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

// HGetAll 获取哈希所有字段
func (s *RedisServer) HGetAll(ctx context.Context, req *pb.HGetAllRequest) (*pb.HGetAllResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	allFields, err := s.redisClient.HGetAll(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	var fields []*pb.HashField
	for field, value := range allFields {
		fields = append(fields, &pb.HashField{
			Field: field,
			Value: value,
		})
	}

	return &pb.HGetAllResponse{
		Fields: fields,
	}, nil
}

// HDelete 删除哈希字段
func (s *RedisServer) HDelete(ctx context.Context, req *pb.HDeleteRequest) (*pb.HDeleteResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	err := s.redisClient.HDelete(ctx, isolatedKey, req.Fields...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HDeleteResponse{
		Success:      true,
		DeletedCount: int32(len(req.Fields)),
	}, nil
}

// HExists 检查哈希字段是否存在
func (s *RedisServer) HExists(ctx context.Context, req *pb.HExistsRequest) (*pb.HExistsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	exists, err := s.redisClient.HExists(ctx, isolatedKey, req.Field)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HExistsResponse{
		Exists: exists,
	}, nil
}

// HKeys 获取哈希所有字段名
func (s *RedisServer) HKeys(ctx context.Context, req *pb.HKeysRequest) (*pb.HKeysResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	fields, err := s.redisClient.HKeys(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HKeysResponse{
		Fields: fields,
	}, nil
}

// HValues 获取哈希所有值
func (s *RedisServer) HValues(ctx context.Context, req *pb.HValuesRequest) (*pb.HValuesResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	values, err := s.redisClient.HValues(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HValuesResponse{
		Values: values,
	}, nil
}

// HIncrement 递增哈希字段
func (s *RedisServer) HIncrement(ctx context.Context, req *pb.HIncrementRequest) (*pb.HIncrementResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	value, err := s.redisClient.HIncrement(ctx, isolatedKey, req.Field, req.Delta)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.HIncrementResponse{
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
		LockId:    lock.Value,
		ExpiresAt: timestamppb.New(time.Now().Add(ttl)),
	}, nil
}

// ReleaseLock 释放锁
func (s *RedisServer) ReleaseLock(ctx context.Context, req *pb.ReleaseLockRequest) (*pb.ReleaseLockResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.LockKey)

	// 使用 Lua 脚本确保只释放自己的锁
	script := `
		if redis.call("get", KEYS[1]) == ARGV[1] then
			return redis.call("del", KEYS[1])
		else
			return 0
		end
	`

	err := s.redisClient.EvalLua(ctx, script, []string{isolatedKey}, req.LockId)
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

// DeleteMultiple 批量删除键
func (s *RedisServer) DeleteMultiple(ctx context.Context, req *pb.DeleteMultipleRequest) (*pb.DeleteResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var isolatedKeys []string
	for _, key := range req.Keys {
		isolatedKeys = append(isolatedKeys, s.isolateKey(req.UserId, req.OrganizationId, key))
	}

	err := s.redisClient.Delete(ctx, isolatedKeys...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.DeleteResponse{
		Success:      true,
		DeletedCount: int32(len(req.Keys)),
	}, nil
}

// Rename 重命名键
func (s *RedisServer) Rename(ctx context.Context, req *pb.RenameRequest) (*pb.RenameResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	oldKey := s.isolateKey(req.UserId, req.OrganizationId, req.OldKey)
	newKey := s.isolateKey(req.UserId, req.OrganizationId, req.NewKey)

	err := s.redisClient.Rename(ctx, oldKey, newKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.RenameResponse{
		Success: true,
	}, nil
}

// ListKeys 列出匹配模式的键
func (s *RedisServer) ListKeys(ctx context.Context, req *pb.ListKeysRequest) (*pb.ListKeysResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 添加命名空间前缀到模式
	pattern := s.isolateKey(req.UserId, req.OrganizationId, req.Pattern)

	keys, err := s.redisClient.Keys(ctx, pattern)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	// 移除命名空间前缀
	var cleanKeys []string
	prefix := s.isolateKey(req.UserId, req.OrganizationId, "")
	for _, key := range keys {
		cleanKeys = append(cleanKeys, strings.TrimPrefix(key, prefix))
	}

	// 应用限制
	if req.Limit > 0 && int32(len(cleanKeys)) > req.Limit {
		cleanKeys = cleanKeys[:req.Limit]
	}

	return &pb.ListKeysResponse{
		Keys:       cleanKeys,
		TotalCount: int32(len(cleanKeys)),
	}, nil
}

// ============================================
// 列表操作实现
// ============================================

// LPush 从左侧推入列表
func (s *RedisServer) LPush(ctx context.Context, req *pb.LPushRequest) (*pb.LPushResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	var values []interface{}
	for _, v := range req.Values {
		values = append(values, v)
	}

	err := s.redisClient.LPush(ctx, isolatedKey, values...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	length, _ := s.redisClient.LLen(ctx, isolatedKey)
	return &pb.LPushResponse{Length: int32(length)}, nil
}

// RPush 从右侧推入列表
func (s *RedisServer) RPush(ctx context.Context, req *pb.RPushRequest) (*pb.RPushResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	var values []interface{}
	for _, v := range req.Values {
		values = append(values, v)
	}

	err := s.redisClient.RPush(ctx, isolatedKey, values...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	length, _ := s.redisClient.LLen(ctx, isolatedKey)
	return &pb.RPushResponse{Length: int32(length)}, nil
}

// LPop 从左侧弹出
func (s *RedisServer) LPop(ctx context.Context, req *pb.LPopRequest) (*pb.LPopResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	value, err := s.redisClient.LPop(ctx, isolatedKey)
	if err != nil {
		if err.Error() == "redis: nil" {
			return &pb.LPopResponse{Found: false}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.LPopResponse{Found: true, Value: value}, nil
}

// RPop 从右侧弹出
func (s *RedisServer) RPop(ctx context.Context, req *pb.RPopRequest) (*pb.RPopResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	value, err := s.redisClient.RPop(ctx, isolatedKey)
	if err != nil {
		if err.Error() == "redis: nil" {
			return &pb.RPopResponse{Found: false}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.RPopResponse{Found: true, Value: value}, nil
}

// LRange 获取列表范围
func (s *RedisServer) LRange(ctx context.Context, req *pb.LRangeRequest) (*pb.LRangeResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	values, err := s.redisClient.LRange(ctx, isolatedKey, int64(req.Start), int64(req.Stop))
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.LRangeResponse{Values: values}, nil
}

// LLen 获取列表长度
func (s *RedisServer) LLen(ctx context.Context, req *pb.LLenRequest) (*pb.LLenResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	length, err := s.redisClient.LLen(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.LLenResponse{Length: int32(length)}, nil
}

// LIndex 获取列表指定位置的元素
func (s *RedisServer) LIndex(ctx context.Context, req *pb.LIndexRequest) (*pb.LIndexResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	value, err := s.redisClient.LIndex(ctx, isolatedKey, int64(req.Index))
	if err != nil {
		if err.Error() == "redis: nil" {
			return &pb.LIndexResponse{Found: false}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.LIndexResponse{Found: true, Value: value}, nil
}

// LTrim 修剪列表
func (s *RedisServer) LTrim(ctx context.Context, req *pb.LTrimRequest) (*pb.LTrimResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	err := s.redisClient.LTrim(ctx, isolatedKey, int64(req.Start), int64(req.Stop))
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.LTrimResponse{Success: true}, nil
}

// ============================================
// 集合操作实现
// ============================================

// SAdd 添加成员到集合
func (s *RedisServer) SAdd(ctx context.Context, req *pb.SAddRequest) (*pb.SAddResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	var members []interface{}
	for _, m := range req.Members {
		members = append(members, m)
	}

	err := s.redisClient.SAdd(ctx, isolatedKey, members...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SAddResponse{AddedCount: int32(len(req.Members))}, nil
}

// SRemove 从集合删除成员
func (s *RedisServer) SRemove(ctx context.Context, req *pb.SRemoveRequest) (*pb.SRemoveResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	var members []interface{}
	for _, m := range req.Members {
		members = append(members, m)
	}

	err := s.redisClient.SRemove(ctx, isolatedKey, members...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SRemoveResponse{RemovedCount: int32(len(req.Members))}, nil
}

// SMembers 获取集合所有成员
func (s *RedisServer) SMembers(ctx context.Context, req *pb.SMembersRequest) (*pb.SMembersResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	members, err := s.redisClient.SMembers(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SMembersResponse{Members: members}, nil
}

// SIsMember 检查是否是集合成员
func (s *RedisServer) SIsMember(ctx context.Context, req *pb.SIsMemberRequest) (*pb.SIsMemberResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	isMember, err := s.redisClient.SIsMember(ctx, isolatedKey, req.Member)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SIsMemberResponse{IsMember: isMember}, nil
}

// SCard 获取集合元素数量
func (s *RedisServer) SCard(ctx context.Context, req *pb.SCardRequest) (*pb.SCardResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	count, err := s.redisClient.SCard(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SCardResponse{Count: int32(count)}, nil
}

// SUnion 集合并集
func (s *RedisServer) SUnion(ctx context.Context, req *pb.SUnionRequest) (*pb.SUnionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var isolatedKeys []string
	for _, key := range req.Keys {
		isolatedKeys = append(isolatedKeys, s.isolateKey(req.UserId, req.OrganizationId, key))
	}

	members, err := s.redisClient.SUnion(ctx, isolatedKeys...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SUnionResponse{Members: members}, nil
}

// SInter 集合交集
func (s *RedisServer) SInter(ctx context.Context, req *pb.SInterRequest) (*pb.SInterResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var isolatedKeys []string
	for _, key := range req.Keys {
		isolatedKeys = append(isolatedKeys, s.isolateKey(req.UserId, req.OrganizationId, key))
	}

	members, err := s.redisClient.SInter(ctx, isolatedKeys...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SInterResponse{Members: members}, nil
}

// SDiff 集合差集
func (s *RedisServer) SDiff(ctx context.Context, req *pb.SDiffRequest) (*pb.SDiffResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var isolatedKeys []string
	for _, key := range req.Keys {
		isolatedKeys = append(isolatedKeys, s.isolateKey(req.UserId, req.OrganizationId, key))
	}

	members, err := s.redisClient.SDiff(ctx, isolatedKeys...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.SDiffResponse{Members: members}, nil
}

// ============================================
// 有序集合操作实现
// ============================================

// ZAdd 添加成员到有序集合
func (s *RedisServer) ZAdd(ctx context.Context, req *pb.ZAddRequest) (*pb.ZAddResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	// 使用 go-redis 的 Z 类型
	var members []*goredis.Z
	for _, m := range req.Members {
		members = append(members, &goredis.Z{
			Score:  m.Score,
			Member: m.Member,
		})
	}

	err := s.redisClient.ZAdd(ctx, isolatedKey, members...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ZAddResponse{AddedCount: int32(len(req.Members))}, nil
}

// ZRemove 从有序集合删除成员
func (s *RedisServer) ZRemove(ctx context.Context, req *pb.ZRemoveRequest) (*pb.ZRemoveResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	var members []interface{}
	for _, m := range req.Members {
		members = append(members, m)
	}

	err := s.redisClient.ZRemove(ctx, isolatedKey, members...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ZRemoveResponse{RemovedCount: int32(len(req.Members))}, nil
}

// ZRange 获取有序集合范围
func (s *RedisServer) ZRange(ctx context.Context, req *pb.ZRangeRequest) (*pb.ZRangeResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	var members []*pb.ZSetMember
	if req.WithScores {
		zMembers, err := s.redisClient.ZRangeWithScores(ctx, isolatedKey, int64(req.Start), int64(req.Stop))
		if err != nil {
			return nil, status.Error(codes.Internal, err.Error())
		}
		for _, zm := range zMembers {
			members = append(members, &pb.ZSetMember{
				Member: zm.Member.(string),
				Score:  zm.Score,
			})
		}
	} else {
		values, err := s.redisClient.ZRange(ctx, isolatedKey, int64(req.Start), int64(req.Stop))
		if err != nil {
			return nil, status.Error(codes.Internal, err.Error())
		}
		for _, v := range values {
			members = append(members, &pb.ZSetMember{Member: v, Score: 0})
		}
	}

	return &pb.ZRangeResponse{Members: members}, nil
}

// ZRangeByScore 按分数范围获取成员
func (s *RedisServer) ZRangeByScore(ctx context.Context, req *pb.ZRangeByScoreRequest) (*pb.ZRangeByScoreResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	values, err := s.redisClient.ZRangeByScore(ctx, isolatedKey, req.MinScore, req.MaxScore)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	var members []*pb.ZSetMember
	for _, v := range values {
		members = append(members, &pb.ZSetMember{Member: v, Score: 0})
	}

	return &pb.ZRangeByScoreResponse{Members: members}, nil
}

// ZRank 获取成员排名
func (s *RedisServer) ZRank(ctx context.Context, req *pb.ZRankRequest) (*pb.ZRankResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	rank, err := s.redisClient.ZRank(ctx, isolatedKey, req.Member)
	if err != nil {
		if err.Error() == "redis: nil" {
			return &pb.ZRankResponse{Found: false}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ZRankResponse{Found: true, Rank: int32(rank)}, nil
}

// ZScore 获取成员分数
func (s *RedisServer) ZScore(ctx context.Context, req *pb.ZScoreRequest) (*pb.ZScoreResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	score, err := s.redisClient.ZScore(ctx, isolatedKey, req.Member)
	if err != nil {
		if err.Error() == "redis: nil" {
			return &pb.ZScoreResponse{Found: false}, nil
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ZScoreResponse{Found: true, Score: score}, nil
}

// ZCard 获取有序集合元素数量
func (s *RedisServer) ZCard(ctx context.Context, req *pb.ZCardRequest) (*pb.ZCardResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	count, err := s.redisClient.ZCard(ctx, isolatedKey)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ZCardResponse{Count: int32(count)}, nil
}

// ZIncrement 递增成员分数
func (s *RedisServer) ZIncrement(ctx context.Context, req *pb.ZIncrementRequest) (*pb.ZIncrementResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	score, err := s.redisClient.ZIncrement(ctx, isolatedKey, req.Member, req.Delta)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.ZIncrementResponse{Score: score}, nil
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

// RenewLock 续期锁
func (s *RedisServer) RenewLock(ctx context.Context, req *pb.RenewLockRequest) (*pb.RenewLockResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.LockKey)
	ttl := req.Ttl.AsDuration()

	err := s.redisClient.Expire(ctx, isolatedKey, ttl)
	if err != nil {
		return &pb.RenewLockResponse{Renewed: false}, nil
	}

	return &pb.RenewLockResponse{
		Renewed:   true,
		ExpiresAt: timestamppb.New(time.Now().Add(ttl)),
	}, nil
}

// Unsubscribe 取消订阅
func (s *RedisServer) Unsubscribe(ctx context.Context, req *pb.UnsubscribeRequest) (*pb.UnsubscribeResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Note: Unsubscribe is typically handled client-side by closing the stream
	// This is a placeholder implementation
	return &pb.UnsubscribeResponse{Success: true}, nil
}

// ============================================
// 批量操作
// ============================================

// ExecuteBatch 执行批量操作
func (s *RedisServer) ExecuteBatch(ctx context.Context, req *pb.RedisBatchRequest) (*pb.RedisBatchResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var errors []string
	executedCount := 0

	for _, cmd := range req.Commands {
		isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, cmd.Key)

		var err error
		switch strings.ToUpper(cmd.Operation) {
		case "SET":
			if cmd.Expiration != nil {
				err = s.redisClient.Set(ctx, isolatedKey, cmd.Value, cmd.Expiration.AsDuration())
			} else {
				err = s.redisClient.Set(ctx, isolatedKey, cmd.Value, 0)
			}
		case "GET":
			_, err = s.redisClient.Get(ctx, isolatedKey)
		case "DELETE", "DEL":
			err = s.redisClient.Delete(ctx, isolatedKey)
		default:
			errors = append(errors, fmt.Sprintf("unknown operation: %s", cmd.Operation))
			continue
		}

		if err != nil {
			errors = append(errors, fmt.Sprintf("%s failed for %s: %v", cmd.Operation, cmd.Key, err))
		} else {
			executedCount++
		}
	}

	return &pb.RedisBatchResponse{
		Success:        len(errors) == 0,
		ExecutedCount:  int32(executedCount),
		Errors:         errors,
	}, nil
}

// ============================================
// 会话管理
// ============================================

// CreateSession 创建会话
func (s *RedisServer) CreateSession(ctx context.Context, req *pb.CreateSessionRequest) (*pb.CreateSessionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 生成会话 ID
	sessionID := fmt.Sprintf("session:%s:%d", req.UserId, time.Now().UnixNano())
	sessionKey := s.isolateKey(req.UserId, req.OrganizationId, sessionID)

	// 存储会话数据为哈希
	var fields []interface{}
	for k, v := range req.Data {
		fields = append(fields, k, v)
	}
	fields = append(fields, "created_at", time.Now().Format(time.RFC3339))

	err := s.redisClient.HSet(ctx, sessionKey, fields...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	// 设置过期时间
	ttl := req.Ttl.AsDuration()
	if ttl == 0 {
		ttl = 24 * time.Hour // 默认 24 小时
	}
	s.redisClient.Expire(ctx, sessionKey, ttl)

	return &pb.CreateSessionResponse{
		SessionId: sessionID,
		ExpiresAt: timestamppb.New(time.Now().Add(ttl)),
	}, nil
}

// GetSession 获取会话
func (s *RedisServer) GetSession(ctx context.Context, req *pb.GetSessionRequest) (*pb.GetSessionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	sessionKey := s.isolateKey(req.UserId, "", req.SessionId)

	data, err := s.redisClient.HGetAll(ctx, sessionKey)
	if err != nil || len(data) == 0 {
		return &pb.GetSessionResponse{Found: false}, nil
	}

	// 构建 SessionInfo
	session := &pb.SessionInfo{
		SessionId: req.SessionId,
		UserId:    req.UserId,
		Data:      data,
	}

	if createdAt, ok := data["created_at"]; ok {
		if t, err := time.Parse(time.RFC3339, createdAt); err == nil {
			session.CreatedAt = timestamppb.New(t)
		}
	}

	return &pb.GetSessionResponse{
		Found:   true,
		Session: session,
	}, nil
}

// UpdateSession 更新会话
func (s *RedisServer) UpdateSession(ctx context.Context, req *pb.UpdateSessionRequest) (*pb.UpdateSessionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	sessionKey := s.isolateKey(req.UserId, "", req.SessionId)

	// 更新会话数据
	var fields []interface{}
	for k, v := range req.Data {
		fields = append(fields, k, v)
	}

	err := s.redisClient.HSet(ctx, sessionKey, fields...)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	// 延长过期时间
	if req.ExtendTtl {
		s.redisClient.Expire(ctx, sessionKey, 24*time.Hour)
	}

	return &pb.UpdateSessionResponse{Success: true}, nil
}

// DeleteSession 删除会话
func (s *RedisServer) DeleteSession(ctx context.Context, req *pb.DeleteSessionRequest) (*pb.DeleteSessionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	sessionKey := s.isolateKey(req.UserId, "", req.SessionId)

	err := s.redisClient.Delete(ctx, sessionKey)
	return &pb.DeleteSessionResponse{Success: err == nil}, nil
}

// ListSessions 列出会话
func (s *RedisServer) ListSessions(ctx context.Context, req *pb.ListSessionsRequest) (*pb.ListSessionsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 查找所有会话键
	pattern := s.isolateKey(req.UserId, req.OrganizationId, "session:*")
	keys, err := s.redisClient.Keys(ctx, pattern)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	var sessions []*pb.SessionInfo
	for _, key := range keys {
		data, _ := s.redisClient.HGetAll(ctx, key)
		if len(data) > 0 {
			session := &pb.SessionInfo{
				SessionId: strings.TrimPrefix(key, s.isolateKey(req.UserId, req.OrganizationId, "")),
				UserId:    req.UserId,
				Data:      data,
			}
			sessions = append(sessions, session)
		}
	}

	return &pb.ListSessionsResponse{Sessions: sessions}, nil
}

// ============================================
// 统计和监控
// ============================================

// GetStatistics 获取统计信息
func (s *RedisServer) GetStatistics(ctx context.Context, req *pb.GetStatisticsRequest) (*pb.GetStatisticsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 获取用户命名空间下的所有键
	pattern := s.isolateKey(req.UserId, req.OrganizationId, "*")
	keys, err := s.redisClient.Keys(ctx, pattern)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.GetStatisticsResponse{
		TotalKeys:             int64(len(keys)),
		MemoryUsedBytes:       0, // 需要从 INFO 命令解析
		CommandsProcessed:     0,
		ConnectionsReceived:   0,
		HitRate:               0,
		KeyTypeDistribution:   make(map[string]int64),
	}, nil
}

// GetKeyInfo 获取键信息
func (s *RedisServer) GetKeyInfo(ctx context.Context, req *pb.GetKeyInfoRequest) (*pb.GetKeyInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedKey := s.isolateKey(req.UserId, req.OrganizationId, req.Key)

	exists, err := s.redisClient.Exists(ctx, isolatedKey)
	if err != nil || !exists {
		return &pb.GetKeyInfoResponse{Exists: false}, nil
	}

	ttl, _ := s.redisClient.GetTTL(ctx, isolatedKey)

	return &pb.GetKeyInfoResponse{
		Exists:     true,
		Type:       pb.ValueType_VALUE_TYPE_STRING, // 简化实现
		TtlSeconds: int64(ttl.Seconds()),
		SizeBytes:  0,
		CreatedAt:  timestamppb.Now(),
	}, nil
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
