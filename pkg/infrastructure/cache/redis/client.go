// Package redis provides a unified Redis client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 Redis 缓存客户端封装
//
// Redis 是一个高性能的内存数据结构存储，用作数据库、缓存和消息代理
// 特点：
// - 支持多种数据结构（String、Hash、List、Set、Sorted Set）
// - 高性能（单线程模型，非阻塞 I/O）
// - 持久化（RDB、AOF）
// - 分布式锁支持
// - Pub/Sub 消息
//
// 示例用法:
//
//	cfg := &redis.Config{
//	    Host:     "localhost",
//	    Port:     6379,
//	    Database: 0,
//	}
//	client, err := redis.NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 设置键值
//	client.Set(ctx, "key", "value", 0)
//
//	// 获取键值
//	value, _ := client.Get(ctx, "key")
package redis

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// Client Redis 客户端封装
type Client struct {
	client *redis.Client
	config *Config
}

// Config Redis 客户端配置
type Config struct {
	// 基础配置
	Host     string // Redis 主机地址
	Port     int    // Redis 端口
	Password string // 密码（可选）
	Database int    // 数据库编号（0-15）

	// 连接池配置
	MaxIdle        int           // 最大空闲连接数
	MaxActive      int           // 最大活跃连接数
	IdleTimeout    time.Duration // 空闲连接超时
	ConnectTimeout time.Duration // 连接超时
	ReadTimeout    time.Duration // 读取超时
	WriteTimeout   time.Duration // 写入超时

	// 集群模式
	ClusterEnabled bool     // 是否启用集群模式
	ClusterNodes   []string // 集群节点列表

	// Sentinel 模式
	SentinelEnabled    bool     // 是否启用 Sentinel 模式
	SentinelMasterName string   // Sentinel 主节点名称
	SentinelNodes      []string // Sentinel 节点列表

	// TLS 配置
	TLSEnabled bool   // 是否启用 TLS
	TLSCert    string // 证书文件路径
	TLSKey     string // 密钥文件路径
	TLSCA      string // CA 证书路径
}

// NewClient 创建新的 Redis 客户端
//
// 参数:
//
//	cfg: Redis 配置
//
// 返回:
//
//	*Client: Redis 客户端实例
//	error: 错误信息
//
// 示例:
//
//	cfg := &Config{
//	    Host:     "localhost",
//	    Port:     6379,
//	    Database: 0,
//	}
//	client, err := NewClient(cfg)
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if cfg.Port == 0 {
		cfg.Port = 6379
	}
	if cfg.MaxIdle == 0 {
		cfg.MaxIdle = 10
	}
	if cfg.MaxActive == 0 {
		cfg.MaxActive = 100
	}
	if cfg.IdleTimeout == 0 {
		cfg.IdleTimeout = 5 * time.Minute
	}
	if cfg.ConnectTimeout == 0 {
		cfg.ConnectTimeout = 5 * time.Second
	}
	if cfg.ReadTimeout == 0 {
		cfg.ReadTimeout = 3 * time.Second
	}
	if cfg.WriteTimeout == 0 {
		cfg.WriteTimeout = 3 * time.Second
	}

	// 创建 Redis 客户端选项
	opts := &redis.Options{
		Addr:         fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		Password:     cfg.Password,
		DB:           cfg.Database,
		PoolSize:     cfg.MaxActive,
		MinIdleConns: cfg.MaxIdle,
		DialTimeout:  cfg.ConnectTimeout,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		ConnMaxIdleTime: cfg.IdleTimeout,
	}

	// 创建客户端
	redisClient := redis.NewClient(opts)

	client := &Client{
		client: redisClient,
		config: cfg,
	}

	return client, nil
}

// Close 关闭客户端连接
func (c *Client) Close() error {
	return c.client.Close()
}

// Ping 健康检查
//
// 返回:
//
//	error: 错误信息
//
// 示例:
//
//	err := client.Ping(ctx)
func (c *Client) Ping(ctx context.Context) error {
	return c.client.Ping(ctx).Err()
}

// ============================================
// 字符串操作 (String Operations)
// ============================================

// Set 设置键值
//
// 参数:
//
//	ctx: 上下文
//	key: 键
//	value: 值
//	expiration: 过期时间（0 表示永不过期）
//
// 示例:
//
//	client.Set(ctx, "user:123", "John Doe", 1*time.Hour)
func (c *Client) Set(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return c.client.Set(ctx, key, value, expiration).Err()
}

// Get 获取键值
//
// 返回:
//
//	string: 值
//	error: 错误信息（redis.Nil 表示键不存在）
//
// 示例:
//
//	value, err := client.Get(ctx, "user:123")
//	if err == redis.Nil {
//	    fmt.Println("key does not exist")
//	} else if err != nil {
//	    log.Fatal(err)
//	}
func (c *Client) Get(ctx context.Context, key string) (string, error) {
	return c.client.Get(ctx, key).Result()
}

// GetMultiple 批量获取键值
//
// 示例:
//
//	values, err := client.GetMultiple(ctx, []string{"key1", "key2", "key3"})
func (c *Client) GetMultiple(ctx context.Context, keys []string) ([]interface{}, error) {
	return c.client.MGet(ctx, keys...).Result()
}

// Increment 递增
//
// 示例:
//
//	newValue, err := client.Increment(ctx, "counter", 1)
func (c *Client) Increment(ctx context.Context, key string, delta int64) (int64, error) {
	return c.client.IncrBy(ctx, key, delta).Result()
}

// Decrement 递减
func (c *Client) Decrement(ctx context.Context, key string, delta int64) (int64, error) {
	return c.client.DecrBy(ctx, key, delta).Result()
}

// Append 追加字符串
func (c *Client) Append(ctx context.Context, key, value string) (int64, error) {
	return c.client.Append(ctx, key, value).Result()
}

// ============================================
// 键操作 (Key Operations)
// ============================================

// Delete 删除键
//
// 示例:
//
//	err := client.Delete(ctx, "user:123")
func (c *Client) Delete(ctx context.Context, keys ...string) error {
	return c.client.Del(ctx, keys...).Err()
}

// Exists 检查键是否存在
//
// 示例:
//
//	exists, err := client.Exists(ctx, "user:123")
func (c *Client) Exists(ctx context.Context, key string) (bool, error) {
	result, err := c.client.Exists(ctx, key).Result()
	return result > 0, err
}

// Expire 设置过期时间
//
// 示例:
//
//	err := client.Expire(ctx, "session:abc", 30*time.Minute)
func (c *Client) Expire(ctx context.Context, key string, expiration time.Duration) error {
	return c.client.Expire(ctx, key, expiration).Err()
}

// GetTTL 获取剩余生存时间
//
// 返回:
//
//	time.Duration: 剩余时间（-1 表示永不过期，-2 表示键不存在）
//
// 示例:
//
//	ttl, err := client.GetTTL(ctx, "session:abc")
func (c *Client) GetTTL(ctx context.Context, key string) (time.Duration, error) {
	return c.client.TTL(ctx, key).Result()
}

// Rename 重命名键
func (c *Client) Rename(ctx context.Context, oldKey, newKey string) error {
	return c.client.Rename(ctx, oldKey, newKey).Err()
}

// Keys 查找匹配模式的键
//
// 参数:
//
//	pattern: 匹配模式（如 "user:*"）
//
// 注意: 生产环境慎用，可能阻塞 Redis
//
// 示例:
//
//	keys, err := client.Keys(ctx, "user:*")
func (c *Client) Keys(ctx context.Context, pattern string) ([]string, error) {
	return c.client.Keys(ctx, pattern).Result()
}

// ============================================
// 哈希操作 (Hash Operations)
// ============================================

// HSet 设置哈希字段
//
// 示例:
//
//	client.HSet(ctx, "user:123", "name", "John", "age", "30")
func (c *Client) HSet(ctx context.Context, key string, values ...interface{}) error {
	return c.client.HSet(ctx, key, values...).Err()
}

// HGet 获取哈希字段值
//
// 示例:
//
//	name, err := client.HGet(ctx, "user:123", "name")
func (c *Client) HGet(ctx context.Context, key, field string) (string, error) {
	return c.client.HGet(ctx, key, field).Result()
}

// HGetAll 获取哈希所有字段
//
// 示例:
//
//	user, err := client.HGetAll(ctx, "user:123")
func (c *Client) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return c.client.HGetAll(ctx, key).Result()
}

// HDelete 删除哈希字段
func (c *Client) HDelete(ctx context.Context, key string, fields ...string) error {
	return c.client.HDel(ctx, key, fields...).Err()
}

// HExists 检查哈希字段是否存在
func (c *Client) HExists(ctx context.Context, key, field string) (bool, error) {
	return c.client.HExists(ctx, key, field).Result()
}

// HKeys 获取哈希所有字段名
func (c *Client) HKeys(ctx context.Context, key string) ([]string, error) {
	return c.client.HKeys(ctx, key).Result()
}

// HValues 获取哈希所有值
func (c *Client) HValues(ctx context.Context, key string) ([]string, error) {
	return c.client.HVals(ctx, key).Result()
}

// HIncrement 递增哈希字段
func (c *Client) HIncrement(ctx context.Context, key, field string, delta int64) (int64, error) {
	return c.client.HIncrBy(ctx, key, field, delta).Result()
}

// ============================================
// 列表操作 (List Operations)
// ============================================

// LPush 从左侧推入列表
//
// 示例:
//
//	client.LPush(ctx, "queue", "task1", "task2")
func (c *Client) LPush(ctx context.Context, key string, values ...interface{}) error {
	return c.client.LPush(ctx, key, values...).Err()
}

// RPush 从右侧推入列表
func (c *Client) RPush(ctx context.Context, key string, values ...interface{}) error {
	return c.client.RPush(ctx, key, values...).Err()
}

// LPop 从左侧弹出
func (c *Client) LPop(ctx context.Context, key string) (string, error) {
	return c.client.LPop(ctx, key).Result()
}

// RPop 从右侧弹出
func (c *Client) RPop(ctx context.Context, key string) (string, error) {
	return c.client.RPop(ctx, key).Result()
}

// LRange 获取列表范围
//
// 示例:
//
//	items, err := client.LRange(ctx, "queue", 0, 10)
func (c *Client) LRange(ctx context.Context, key string, start, stop int64) ([]string, error) {
	return c.client.LRange(ctx, key, start, stop).Result()
}

// LLen 获取列表长度
func (c *Client) LLen(ctx context.Context, key string) (int64, error) {
	return c.client.LLen(ctx, key).Result()
}

// LIndex 获取列表指定位置的元素
func (c *Client) LIndex(ctx context.Context, key string, index int64) (string, error) {
	return c.client.LIndex(ctx, key, index).Result()
}

// LTrim 修剪列表
func (c *Client) LTrim(ctx context.Context, key string, start, stop int64) error {
	return c.client.LTrim(ctx, key, start, stop).Err()
}

// ============================================
// 集合操作 (Set Operations)
// ============================================

// SAdd 添加成员到集合
//
// 示例:
//
//	client.SAdd(ctx, "tags", "go", "redis", "cloud")
func (c *Client) SAdd(ctx context.Context, key string, members ...interface{}) error {
	return c.client.SAdd(ctx, key, members...).Err()
}

// SRemove 从集合删除成员
func (c *Client) SRemove(ctx context.Context, key string, members ...interface{}) error {
	return c.client.SRem(ctx, key, members...).Err()
}

// SMembers 获取集合所有成员
func (c *Client) SMembers(ctx context.Context, key string) ([]string, error) {
	return c.client.SMembers(ctx, key).Result()
}

// SIsMember 检查是否是集合成员
func (c *Client) SIsMember(ctx context.Context, key string, member interface{}) (bool, error) {
	return c.client.SIsMember(ctx, key, member).Result()
}

// SCard 获取集合元素数量
func (c *Client) SCard(ctx context.Context, key string) (int64, error) {
	return c.client.SCard(ctx, key).Result()
}

// SUnion 集合并集
func (c *Client) SUnion(ctx context.Context, keys ...string) ([]string, error) {
	return c.client.SUnion(ctx, keys...).Result()
}

// SInter 集合交集
func (c *Client) SInter(ctx context.Context, keys ...string) ([]string, error) {
	return c.client.SInter(ctx, keys...).Result()
}

// SDiff 集合差集
func (c *Client) SDiff(ctx context.Context, keys ...string) ([]string, error) {
	return c.client.SDiff(ctx, keys...).Result()
}

// ============================================
// 有序集合操作 (Sorted Set Operations)
// ============================================

// ZAdd 添加成员到有序集合
//
// 示例:
//
//	client.ZAdd(ctx, "leaderboard", redis.Z{Score: 100, Member: "player1"})
func (c *Client) ZAdd(ctx context.Context, key string, members ...*redis.Z) error {
	// 转换 []*redis.Z 为 []redis.Z
	zMembers := make([]redis.Z, len(members))
	for i, m := range members {
		zMembers[i] = *m
	}
	return c.client.ZAdd(ctx, key, zMembers...).Err()
}

// ZRemove 从有序集合删除成员
func (c *Client) ZRemove(ctx context.Context, key string, members ...interface{}) error {
	return c.client.ZRem(ctx, key, members...).Err()
}

// ZRange 获取有序集合范围（按分数排序）
//
// 示例:
//
//	// 获取前 10 名
//	top10, err := client.ZRange(ctx, "leaderboard", 0, 9)
func (c *Client) ZRange(ctx context.Context, key string, start, stop int64) ([]string, error) {
	return c.client.ZRange(ctx, key, start, stop).Result()
}

// ZRangeWithScores 获取有序集合范围（包含分数）
func (c *Client) ZRangeWithScores(ctx context.Context, key string, start, stop int64) ([]redis.Z, error) {
	return c.client.ZRangeWithScores(ctx, key, start, stop).Result()
}

// ZRangeByScore 按分数范围获取成员
func (c *Client) ZRangeByScore(ctx context.Context, key string, min, max float64) ([]string, error) {
	return c.client.ZRangeByScore(ctx, key, &redis.ZRangeBy{
		Min: fmt.Sprintf("%f", min),
		Max: fmt.Sprintf("%f", max),
	}).Result()
}

// ZRank 获取成员排名
func (c *Client) ZRank(ctx context.Context, key, member string) (int64, error) {
	return c.client.ZRank(ctx, key, member).Result()
}

// ZScore 获取成员分数
func (c *Client) ZScore(ctx context.Context, key, member string) (float64, error) {
	return c.client.ZScore(ctx, key, member).Result()
}

// ZCard 获取有序集合元素数量
func (c *Client) ZCard(ctx context.Context, key string) (int64, error) {
	return c.client.ZCard(ctx, key).Result()
}

// ZIncrement 递增成员分数
func (c *Client) ZIncrement(ctx context.Context, key string, member string, increment float64) (float64, error) {
	return c.client.ZIncrBy(ctx, key, increment, member).Result()
}

// ============================================
// 分布式锁 (Distributed Lock)
// ============================================

// Lock 分布式锁
type Lock struct {
	Key        string        // 锁键（导出供外部访问）
	Value      string        // 锁值（导出供外部访问）
	Expiration time.Duration // 过期时间
	client     *Client       // Redis 客户端（内部使用）
}

// AcquireLock 获取分布式锁
//
// 参数:
//
//	key: 锁键
//	expiration: 锁超时时间
//
// 返回:
//
//	*Lock: 锁对象
//	error: 错误信息
//
// 示例:
//
//	lock, err := client.AcquireLock(ctx, "resource:123", 10*time.Second)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer lock.Release(ctx)
func (c *Client) AcquireLock(ctx context.Context, key string, expiration time.Duration) (*Lock, error) {
	value := fmt.Sprintf("%d", time.Now().UnixNano())

	// 使用 SET NX EX 实现锁
	success, err := c.client.SetNX(ctx, key, value, expiration).Result()
	if err != nil {
		return nil, err
	}

	if !success {
		return nil, fmt.Errorf("failed to acquire lock")
	}

	return &Lock{
		Key:        key,
		Value:      value,
		Expiration: expiration,
		client:     c,
	}, nil
}

// Release 释放锁
func (l *Lock) Release(ctx context.Context) error {
	// 使用 Lua 脚本确保只释放自己的锁
	script := `
		if redis.call("get", KEYS[1]) == ARGV[1] then
			return redis.call("del", KEYS[1])
		else
			return 0
		end
	`

	return l.client.client.Eval(ctx, script, []string{l.Key}, l.Value).Err()
}

// Renew 续期锁
func (l *Lock) Renew(ctx context.Context) error {
	return l.client.Expire(ctx, l.Key, l.Expiration)
}

// ============================================
// Pub/Sub
// ============================================

// Publish 发布消息
//
// 示例:
//
//	err := client.Publish(ctx, "notifications", "Hello World")
func (c *Client) Publish(ctx context.Context, channel string, message interface{}) error {
	return c.client.Publish(ctx, channel, message).Err()
}

// Subscribe 订阅频道
//
// 返回:
//
//	*redis.PubSub: 订阅对象
//
// 示例:
//
//	pubsub := client.Subscribe(ctx, "notifications")
//	defer pubsub.Close()
//
//	ch := pubsub.Channel()
//	for msg := range ch {
//	    fmt.Println(msg.Payload)
//	}
func (c *Client) Subscribe(ctx context.Context, channels ...string) *redis.PubSub {
	return c.client.Subscribe(ctx, channels...)
}

// ============================================
// 工具方法
// ============================================

// GetConfig 获取配置
func (c *Client) GetConfig() *Config {
	return c.config
}

// FlushDB 清空当前数据库（慎用！）
func (c *Client) FlushDB(ctx context.Context) error {
	return c.client.FlushDB(ctx).Err()
}

// GetStats 获取统计信息
//
// 返回:
//
//	map[string]interface{}: 统计信息
//
// 示例:
//
//	stats, err := client.GetStats(ctx)
//	fmt.Printf("Used memory: %s\n", stats["used_memory"])
func (c *Client) GetStats(ctx context.Context) (map[string]interface{}, error) {
	info, err := c.client.Info(ctx).Result()
	if err != nil {
		return nil, err
	}

	stats := make(map[string]interface{})
	stats["info"] = info

	return stats, nil
}

// EvalLua 执行 Lua 脚本
func (c *Client) EvalLua(ctx context.Context, script string, keys []string, args ...interface{}) error {
	return c.client.Eval(ctx, script, keys, args...).Err()
}
