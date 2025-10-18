// Package clients provides gRPC client implementations for inter-service communication
// Redis gRPC Client - for services to communicate with Redis service
//
// 文件名: pkg/grpc/clients/redis_grpc_client.go
package clients

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/durationpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/redis"
)

// RedisGRPCClient Redis gRPC 客户端
// 用于服务间通信，连接到 Redis gRPC 服务
type RedisGRPCClient struct {
	conn           *grpc.ClientConn
	client         pb.RedisServiceClient
	userID         string
	organizationID string
}

// RedisGRPCConfig Redis gRPC 客户端配置
type RedisGRPCConfig struct {
	Host           string
	Port           int
	UserID         string
	OrganizationID string
}

// NewRedisGRPCClient 创建 Redis gRPC 客户端
func NewRedisGRPCClient(cfg *RedisGRPCConfig) (*RedisGRPCClient, error) {
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
		return nil, fmt.Errorf("failed to connect to Redis gRPC service at %s: %w", addr, err)
	}

	return &RedisGRPCClient{
		conn:           conn,
		client:         pb.NewRedisServiceClient(conn),
		userID:         cfg.UserID,
		organizationID: cfg.OrganizationID,
	}, nil
}

// Close 关闭连接
func (c *RedisGRPCClient) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// ============================================
// String Operations
// ============================================

// Set 设置字符串值
func (c *RedisGRPCClient) Set(ctx context.Context, key, value string) error {
	req := &pb.SetRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Value:          value,
	}

	resp, err := c.client.Set(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("set failed: %s", resp.Message)
	}

	return nil
}

// Get 获取字符串值
func (c *RedisGRPCClient) Get(ctx context.Context, key string) (string, bool, error) {
	req := &pb.GetRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.Get(ctx, req)
	if err != nil {
		return "", false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, resp.Found, nil
}

// GetMultiple 批量获取字符串值
func (c *RedisGRPCClient) GetMultiple(ctx context.Context, keys []string) (map[string]string, error) {
	req := &pb.GetMultipleRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Keys:           keys,
	}

	resp, err := c.client.GetMultiple(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	result := make(map[string]string)
	for _, kv := range resp.Values {
		result[kv.Key] = kv.Value
	}

	return result, nil
}

// SetWithExpiration 设置带过期时间的值
func (c *RedisGRPCClient) SetWithExpiration(ctx context.Context, key, value string, expiration time.Duration) error {
	req := &pb.SetWithExpirationRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Value:          value,
		Expiration:     durationpb.New(expiration),
	}

	resp, err := c.client.SetWithExpiration(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("set with expiration failed: %s", resp.Message)
	}

	return nil
}

// Increment 增加数值
func (c *RedisGRPCClient) Increment(ctx context.Context, key string, delta int64) (int64, error) {
	req := &pb.IncrementRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Delta:          delta,
	}

	resp, err := c.client.Increment(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, nil
}

// Decrement 减少数值
func (c *RedisGRPCClient) Decrement(ctx context.Context, key string, delta int64) (int64, error) {
	req := &pb.DecrementRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Delta:          delta,
	}

	resp, err := c.client.Decrement(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, nil
}

// Append 追加字符串
func (c *RedisGRPCClient) Append(ctx context.Context, key, value string) (int64, error) {
	req := &pb.AppendRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Value:          value,
	}

	resp, err := c.client.Append(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Length, nil
}

// ============================================
// Key Operations
// ============================================

// Delete 删除键
func (c *RedisGRPCClient) Delete(ctx context.Context, key string) error {
	req := &pb.DeleteRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.Delete(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("delete failed")
	}

	return nil
}

// DeleteMultiple 批量删除键
func (c *RedisGRPCClient) DeleteMultiple(ctx context.Context, keys []string) (int32, error) {
	req := &pb.DeleteMultipleRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Keys:           keys,
	}

	resp, err := c.client.DeleteMultiple(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.DeletedCount, nil
}

// Exists 检查键是否存在
func (c *RedisGRPCClient) Exists(ctx context.Context, key string) (bool, error) {
	req := &pb.ExistsRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.Exists(ctx, req)
	if err != nil {
		return false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Exists, nil
}

// Expire 设置过期时间
func (c *RedisGRPCClient) Expire(ctx context.Context, key string, expiration time.Duration) error {
	req := &pb.ExpireRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Expiration:     durationpb.New(expiration),
	}

	resp, err := c.client.Expire(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("expire failed")
	}

	return nil
}

// GetTTL 获取剩余时间
func (c *RedisGRPCClient) GetTTL(ctx context.Context, key string) (int64, error) {
	req := &pb.GetTTLRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.GetTTL(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.TtlSeconds, nil
}

// Rename 重命名键
func (c *RedisGRPCClient) Rename(ctx context.Context, oldKey, newKey string) error {
	req := &pb.RenameRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		OldKey:         oldKey,
		NewKey:         newKey,
	}

	resp, err := c.client.Rename(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("rename failed")
	}

	return nil
}

// ListKeys 列出键
func (c *RedisGRPCClient) ListKeys(ctx context.Context, pattern string, limit int32) ([]string, error) {
	req := &pb.ListKeysRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Pattern:        pattern,
		Limit:          limit,
	}

	resp, err := c.client.ListKeys(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Keys, nil
}

// ============================================
// Hash Operations
// ============================================

// HSet 设置哈希字段
func (c *RedisGRPCClient) HSet(ctx context.Context, key string, fields map[string]string) error {
	hashFields := make([]*pb.HashField, 0, len(fields))
	for field, value := range fields {
		hashFields = append(hashFields, &pb.HashField{
			Field: field,
			Value: value,
		})
	}

	req := &pb.HSetRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Fields:         hashFields,
	}

	resp, err := c.client.HSet(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("hset failed")
	}

	return nil
}

// HGet 获取哈希字段
func (c *RedisGRPCClient) HGet(ctx context.Context, key, field string) (string, bool, error) {
	req := &pb.HGetRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Field:          field,
	}

	resp, err := c.client.HGet(ctx, req)
	if err != nil {
		return "", false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, resp.Found, nil
}

// HGetAll 获取所有哈希字段
func (c *RedisGRPCClient) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	req := &pb.HGetAllRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.HGetAll(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	result := make(map[string]string)
	for _, field := range resp.Fields {
		result[field.Field] = field.Value
	}

	return result, nil
}

// HDelete 删除哈希字段
func (c *RedisGRPCClient) HDelete(ctx context.Context, key string, fields []string) (int32, error) {
	req := &pb.HDeleteRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Fields:         fields,
	}

	resp, err := c.client.HDelete(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.DeletedCount, nil
}

// HExists 检查哈希字段是否存在
func (c *RedisGRPCClient) HExists(ctx context.Context, key, field string) (bool, error) {
	req := &pb.HExistsRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Field:          field,
	}

	resp, err := c.client.HExists(ctx, req)
	if err != nil {
		return false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Exists, nil
}

// HKeys 获取所有哈希字段名
func (c *RedisGRPCClient) HKeys(ctx context.Context, key string) ([]string, error) {
	req := &pb.HKeysRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.HKeys(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Fields, nil
}

// HValues 获取所有哈希字段值
func (c *RedisGRPCClient) HValues(ctx context.Context, key string) ([]string, error) {
	req := &pb.HValuesRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.HValues(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Values, nil
}

// HIncrement 增加哈希字段值
func (c *RedisGRPCClient) HIncrement(ctx context.Context, key, field string, delta int64) (int64, error) {
	req := &pb.HIncrementRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Field:          field,
		Delta:          delta,
	}

	resp, err := c.client.HIncrement(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, nil
}

// ============================================
// List Operations
// ============================================

// LPush 从左侧推入列表
func (c *RedisGRPCClient) LPush(ctx context.Context, key string, values []string) (int32, error) {
	req := &pb.LPushRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Values:         values,
	}

	resp, err := c.client.LPush(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Length, nil
}

// RPush 从右侧推入列表
func (c *RedisGRPCClient) RPush(ctx context.Context, key string, values []string) (int32, error) {
	req := &pb.RPushRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Values:         values,
	}

	resp, err := c.client.RPush(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Length, nil
}

// LPop 从左侧弹出
func (c *RedisGRPCClient) LPop(ctx context.Context, key string) (string, bool, error) {
	req := &pb.LPopRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.LPop(ctx, req)
	if err != nil {
		return "", false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, resp.Found, nil
}

// RPop 从右侧弹出
func (c *RedisGRPCClient) RPop(ctx context.Context, key string) (string, bool, error) {
	req := &pb.RPopRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.RPop(ctx, req)
	if err != nil {
		return "", false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, resp.Found, nil
}

// LRange 获取列表范围
func (c *RedisGRPCClient) LRange(ctx context.Context, key string, start, stop int32) ([]string, error) {
	req := &pb.LRangeRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Start:          start,
		Stop:           stop,
	}

	resp, err := c.client.LRange(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Values, nil
}

// LLen 获取列表长度
func (c *RedisGRPCClient) LLen(ctx context.Context, key string) (int32, error) {
	req := &pb.LLenRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.LLen(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Length, nil
}

// LIndex 获取列表元素
func (c *RedisGRPCClient) LIndex(ctx context.Context, key string, index int32) (string, bool, error) {
	req := &pb.LIndexRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Index:          index,
	}

	resp, err := c.client.LIndex(ctx, req)
	if err != nil {
		return "", false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Value, resp.Found, nil
}

// LTrim 修剪列表
func (c *RedisGRPCClient) LTrim(ctx context.Context, key string, start, stop int32) error {
	req := &pb.LTrimRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Start:          start,
		Stop:           stop,
	}

	resp, err := c.client.LTrim(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("ltrim failed")
	}

	return nil
}

// ============================================
// Set Operations
// ============================================

// SAdd 添加集合成员
func (c *RedisGRPCClient) SAdd(ctx context.Context, key string, members []string) (int32, error) {
	req := &pb.SAddRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Members:        members,
	}

	resp, err := c.client.SAdd(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.AddedCount, nil
}

// SRemove 移除集合成员
func (c *RedisGRPCClient) SRemove(ctx context.Context, key string, members []string) (int32, error) {
	req := &pb.SRemoveRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Members:        members,
	}

	resp, err := c.client.SRemove(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.RemovedCount, nil
}

// SMembers 获取所有集合成员
func (c *RedisGRPCClient) SMembers(ctx context.Context, key string) ([]string, error) {
	req := &pb.SMembersRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.SMembers(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Members, nil
}

// SIsMember 检查是否是集合成员
func (c *RedisGRPCClient) SIsMember(ctx context.Context, key, member string) (bool, error) {
	req := &pb.SIsMemberRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Member:         member,
	}

	resp, err := c.client.SIsMember(ctx, req)
	if err != nil {
		return false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.IsMember, nil
}

// SCard 获取集合大小
func (c *RedisGRPCClient) SCard(ctx context.Context, key string) (int32, error) {
	req := &pb.SCardRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.SCard(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Count, nil
}

// SUnion 获取集合并集
func (c *RedisGRPCClient) SUnion(ctx context.Context, keys []string) ([]string, error) {
	req := &pb.SUnionRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Keys:           keys,
	}

	resp, err := c.client.SUnion(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Members, nil
}

// SInter 获取集合交集
func (c *RedisGRPCClient) SInter(ctx context.Context, keys []string) ([]string, error) {
	req := &pb.SInterRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Keys:           keys,
	}

	resp, err := c.client.SInter(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Members, nil
}

// SDiff 获取集合差集
func (c *RedisGRPCClient) SDiff(ctx context.Context, keys []string) ([]string, error) {
	req := &pb.SDiffRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Keys:           keys,
	}

	resp, err := c.client.SDiff(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Members, nil
}

// ============================================
// Sorted Set Operations
// ============================================

// ZAdd 添加有序集合成员
func (c *RedisGRPCClient) ZAdd(ctx context.Context, key string, members map[string]float64) (int32, error) {
	zsetMembers := make([]*pb.ZSetMember, 0, len(members))
	for member, score := range members {
		zsetMembers = append(zsetMembers, &pb.ZSetMember{
			Member: member,
			Score:  score,
		})
	}

	req := &pb.ZAddRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Members:        zsetMembers,
	}

	resp, err := c.client.ZAdd(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.AddedCount, nil
}

// ZRemove 移除有序集合成员
func (c *RedisGRPCClient) ZRemove(ctx context.Context, key string, members []string) (int32, error) {
	req := &pb.ZRemoveRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Members:        members,
	}

	resp, err := c.client.ZRemove(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.RemovedCount, nil
}

// ZRange 获取有序集合范围
func (c *RedisGRPCClient) ZRange(ctx context.Context, key string, start, stop int32, withScores bool) ([]*pb.ZSetMember, error) {
	req := &pb.ZRangeRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Start:          start,
		Stop:           stop,
		WithScores:     withScores,
	}

	resp, err := c.client.ZRange(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Members, nil
}

// ZRangeByScore 按分数获取有序集合
func (c *RedisGRPCClient) ZRangeByScore(ctx context.Context, key string, minScore, maxScore float64, offset, count int32) ([]*pb.ZSetMember, error) {
	req := &pb.ZRangeByScoreRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		MinScore:       minScore,
		MaxScore:       maxScore,
		Offset:         offset,
		Count:          count,
	}

	resp, err := c.client.ZRangeByScore(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Members, nil
}

// ZRank 获取成员排名
func (c *RedisGRPCClient) ZRank(ctx context.Context, key, member string) (int32, bool, error) {
	req := &pb.ZRankRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Member:         member,
	}

	resp, err := c.client.ZRank(ctx, req)
	if err != nil {
		return 0, false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Rank, resp.Found, nil
}

// ZScore 获取成员分数
func (c *RedisGRPCClient) ZScore(ctx context.Context, key, member string) (float64, bool, error) {
	req := &pb.ZScoreRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Member:         member,
	}

	resp, err := c.client.ZScore(ctx, req)
	if err != nil {
		return 0, false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Score, resp.Found, nil
}

// ZCard 获取有序集合大小
func (c *RedisGRPCClient) ZCard(ctx context.Context, key string) (int32, error) {
	req := &pb.ZCardRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.ZCard(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Count, nil
}

// ZIncrement 增加成员分数
func (c *RedisGRPCClient) ZIncrement(ctx context.Context, key, member string, delta float64) (float64, error) {
	req := &pb.ZIncrementRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
		Member:         member,
		Delta:          delta,
	}

	resp, err := c.client.ZIncrement(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Score, nil
}

// ============================================
// Distributed Lock
// ============================================

// AcquireLock 获取分布式锁
func (c *RedisGRPCClient) AcquireLock(ctx context.Context, lockKey string, ttl, waitTimeout time.Duration) (string, bool, error) {
	req := &pb.AcquireLockRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		LockKey:        lockKey,
		Ttl:            durationpb.New(ttl),
		WaitTimeout:    durationpb.New(waitTimeout),
	}

	resp, err := c.client.AcquireLock(ctx, req)
	if err != nil {
		return "", false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.LockId, resp.Acquired, nil
}

// ReleaseLock 释放分布式锁
func (c *RedisGRPCClient) ReleaseLock(ctx context.Context, lockKey, lockID string) (bool, error) {
	req := &pb.ReleaseLockRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		LockKey:        lockKey,
		LockId:         lockID,
	}

	resp, err := c.client.ReleaseLock(ctx, req)
	if err != nil {
		return false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Released, nil
}

// RenewLock 续期分布式锁
func (c *RedisGRPCClient) RenewLock(ctx context.Context, lockKey, lockID string, ttl time.Duration) (bool, error) {
	req := &pb.RenewLockRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		LockKey:        lockKey,
		LockId:         lockID,
		Ttl:            durationpb.New(ttl),
	}

	resp, err := c.client.RenewLock(ctx, req)
	if err != nil {
		return false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Renewed, nil
}

// ============================================
// Pub/Sub
// ============================================

// Publish 发布消息
func (c *RedisGRPCClient) Publish(ctx context.Context, channel, message string) (int32, error) {
	req := &pb.PublishRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Channel:        channel,
		Message:        message,
	}

	resp, err := c.client.Publish(ctx, req)
	if err != nil {
		return 0, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.SubscriberCount, nil
}

// Subscribe 订阅频道 (流式接收消息)
func (c *RedisGRPCClient) Subscribe(ctx context.Context, channels []string) (pb.RedisService_SubscribeClient, error) {
	req := &pb.SubscribeRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Channels:       channels,
	}

	stream, err := c.client.Subscribe(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return stream, nil
}

// Unsubscribe 取消订阅
func (c *RedisGRPCClient) Unsubscribe(ctx context.Context, channels []string) error {
	req := &pb.UnsubscribeRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Channels:       channels,
	}

	resp, err := c.client.Unsubscribe(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("unsubscribe failed")
	}

	return nil
}

// ============================================
// Session Management
// ============================================

// CreateSession 创建会话
func (c *RedisGRPCClient) CreateSession(ctx context.Context, data map[string]string, ttl time.Duration) (string, *timestamppb.Timestamp, error) {
	req := &pb.CreateSessionRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Data:           data,
		Ttl:            durationpb.New(ttl),
	}

	resp, err := c.client.CreateSession(ctx, req)
	if err != nil {
		return "", nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.SessionId, resp.ExpiresAt, nil
}

// GetSession 获取会话
func (c *RedisGRPCClient) GetSession(ctx context.Context, sessionID string) (*pb.SessionInfo, bool, error) {
	req := &pb.GetSessionRequest{
		UserId:    c.userID,
		SessionId: sessionID,
	}

	resp, err := c.client.GetSession(ctx, req)
	if err != nil {
		return nil, false, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Session, resp.Found, nil
}

// UpdateSession 更新会话
func (c *RedisGRPCClient) UpdateSession(ctx context.Context, sessionID string, data map[string]string, extendTTL bool) error {
	req := &pb.UpdateSessionRequest{
		UserId:    c.userID,
		SessionId: sessionID,
		Data:      data,
		ExtendTtl: extendTTL,
	}

	resp, err := c.client.UpdateSession(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("update session failed")
	}

	return nil
}

// DeleteSession 删除会话
func (c *RedisGRPCClient) DeleteSession(ctx context.Context, sessionID string) error {
	req := &pb.DeleteSessionRequest{
		UserId:    c.userID,
		SessionId: sessionID,
	}

	resp, err := c.client.DeleteSession(ctx, req)
	if err != nil {
		return fmt.Errorf("gRPC call failed: %w", err)
	}

	if !resp.Success {
		return fmt.Errorf("delete session failed")
	}

	return nil
}

// ListSessions 列出所有会话
func (c *RedisGRPCClient) ListSessions(ctx context.Context) ([]*pb.SessionInfo, error) {
	req := &pb.ListSessionsRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
	}

	resp, err := c.client.ListSessions(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp.Sessions, nil
}

// ============================================
// Statistics and Monitoring
// ============================================

// GetStatistics 获取统计信息
func (c *RedisGRPCClient) GetStatistics(ctx context.Context) (*pb.GetStatisticsResponse, error) {
	req := &pb.GetStatisticsRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
	}

	resp, err := c.client.GetStatistics(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp, nil
}

// GetKeyInfo 获取键信息
func (c *RedisGRPCClient) GetKeyInfo(ctx context.Context, key string) (*pb.GetKeyInfoResponse, error) {
	req := &pb.GetKeyInfoRequest{
		UserId:         c.userID,
		OrganizationId: c.organizationID,
		Key:            key,
	}

	resp, err := c.client.GetKeyInfo(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC call failed: %w", err)
	}

	return resp, nil
}

// ============================================
// Health Check
// ============================================

// HealthCheck 健康检查
func (c *RedisGRPCClient) HealthCheck(ctx context.Context, deepCheck bool) error {
	req := &pb.RedisHealthCheckRequest{
		DeepCheck: deepCheck,
	}

	resp, err := c.client.HealthCheck(ctx, req)
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}

	if !resp.Healthy {
		return fmt.Errorf("Redis service unhealthy: %s", resp.Message)
	}

	return nil
}
