# Redis SDK 客户端

为 isA Cloud 平台提供统一的 Redis 缓存客户端封装。

## 功能特性

### 核心操作
- ✅ **String 操作**: Set, Get, Increment, Decrement, Append
- ✅ **Hash 操作**: HSet, HGet, HGetAll, HIncrement
- ✅ **List 操作**: LPush, RPush, LPop, RPop, LRange
- ✅ **Set 操作**: SAdd, SRemove, SMembers, SUnion, SInter, SDiff
- ✅ **Sorted Set 操作**: ZAdd, ZRange, ZRank, ZScore, ZIncrement

### 高级功能
- ✅ **分布式锁**: AcquireLock, ReleaseLock, RenewLock
- ✅ **Pub/Sub**: Publish, Subscribe
- ✅ **键管理**: Expire, GetTTL, Rename, Keys
- ✅ **批量操作**: GetMultiple, Delete (多个键)
- ✅ **健康检查**: Ping
- ✅ **统计信息**: GetStats

### 部署特性
- ✅ **Consul 服务发现**: 自动发现 Redis 服务
- ✅ **连接池管理**: 可配置的连接池
- ✅ **TLS 支持**: 安全连接
- ✅ **集群模式**: Redis Cluster 支持
- ✅ **Sentinel 模式**: 高可用支持

## 快速开始

### 安装

```bash
go get github.com/go-redis/redis/v8
```

### 基础用法

```go
package main

import (
    "context"
    "log"
    "time"

    "github.com/isa-cloud/isa_cloud/pkg/infrastructure/cache/redis"
)

func main() {
    // 创建客户端配置
    cfg := &redis.Config{
        Host:     "localhost",
        Port:     6379,
        Database: 0,
    }

    // 创建客户端
    client, err := redis.NewClient(cfg)
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    ctx := context.Background()

    // 设置键值
    err = client.Set(ctx, "user:123", "John Doe", 1*time.Hour)
    if err != nil {
        log.Fatal(err)
    }

    // 获取键值
    value, err := client.Get(ctx, "user:123")
    if err != nil {
        log.Fatal(err)
    }
    log.Printf("Value: %s", value)
}
```

### 使用配置文件

```go
import "github.com/isa-cloud/isa_cloud/pkg/infrastructure/cache"

// 从配置文件加载
factory, err := cache.NewCacheClientFactory()
if err != nil {
    log.Fatal(err)
}

// 创建 Redis 客户端（自动 Consul 发现）
client, err := factory.NewRedisClient(context.Background())
if err != nil {
    log.Fatal(err)
}
defer client.Close()
```

## 详细示例

### 1. 字符串操作

```go
ctx := context.Background()

// 设置键值（带过期时间）
client.Set(ctx, "session:abc", "user123", 30*time.Minute)

// 获取键值
value, err := client.Get(ctx, "session:abc")

// 递增计数器
count, err := client.Increment(ctx, "page:views", 1)

// 批量获取
values, err := client.GetMultiple(ctx, []string{"key1", "key2", "key3"})
```

### 2. 哈希操作

```go
// 设置用户信息
client.HSet(ctx, "user:123", 
    "name", "John Doe",
    "age", "30",
    "email", "john@example.com")

// 获取单个字段
name, err := client.HGet(ctx, "user:123", "name")

// 获取所有字段
user, err := client.HGetAll(ctx, "user:123")

// 递增字段值
newAge, err := client.HIncrement(ctx, "user:123", "age", 1)
```

### 3. 列表操作

```go
// 任务队列
client.RPush(ctx, "tasks", "task1", "task2", "task3")

// 从队列获取任务
task, err := client.LPop(ctx, "tasks")

// 获取队列长度
length, err := client.LLen(ctx, "tasks")

// 获取范围
tasks, err := client.LRange(ctx, "tasks", 0, 10)
```

### 4. 集合操作

```go
// 用户标签
client.SAdd(ctx, "user:123:tags", "golang", "redis", "cloud")

// 检查成员
exists, err := client.SIsMember(ctx, "user:123:tags", "golang")

// 获取所有成员
tags, err := client.SMembers(ctx, "user:123:tags")

// 集合交集（共同兴趣）
common, err := client.SInter(ctx, "user:123:tags", "user:456:tags")
```

### 5. 有序集合操作

```go
// 排行榜
client.ZAdd(ctx, "leaderboard", 
    &redis.Z{Score: 100, Member: "player1"},
    &redis.Z{Score: 95, Member: "player2"})

// 递增分数
newScore, err := client.ZIncrement(ctx, "leaderboard", "player1", 10)

// 获取前 10 名
top10, err := client.ZRange(ctx, "leaderboard", 0, 9)

// 获取排名
rank, err := client.ZRank(ctx, "leaderboard", "player1")
```

### 6. 分布式锁

```go
// 获取锁
lock, err := client.AcquireLock(ctx, "resource:123", 10*time.Second)
if err != nil {
    log.Fatal("Failed to acquire lock")
}
defer lock.Release(ctx)

// 执行临界区操作
performCriticalOperation()

// 如果需要更多时间，续期锁
lock.Renew(ctx)
```

### 7. Pub/Sub

```go
// 发布者
err := client.Publish(ctx, "notifications", "Hello World")

// 订阅者
pubsub := client.Subscribe(ctx, "notifications")
defer pubsub.Close()

ch := pubsub.Channel()
for msg := range ch {
    log.Printf("Received: %s", msg.Payload)
}
```

## 配置选项

### 配置文件 (configs/sdk/redis.yaml)

```yaml
# 基础配置
host: "localhost"
port: 6379
password: ""
database: 0

# Consul 服务发现
use_consul: true
service_name: "redis-service"
grpc_port: 50055

# 连接池
max_idle: 10
max_active: 100
idle_timeout: "5m"
connect_timeout: "5s"
read_timeout: "3s"
write_timeout: "3s"

# 集群模式
cluster_enabled: false
cluster_nodes:
  - "redis-1:6379"
  - "redis-2:6379"

# TLS
tls_enabled: false
```

### 环境变量

```bash
export ISA_CLOUD_REDIS_HOST="redis.example.com"
export ISA_CLOUD_REDIS_PORT=6379
export ISA_CLOUD_REDIS_PASSWORD="secret"
export ISA_CLOUD_REDIS_DATABASE=0
export ISA_CLOUD_REDIS_USE_CONSUL=true
```

## 实际应用场景

### 会话管理

```go
// 创建会话
sessionID := generateSessionID()
sessionData := map[string]interface{}{
    "user_id": "123",
    "role": "admin",
}

// 存储会话（30分钟过期）
client.HSet(ctx, fmt.Sprintf("session:%s", sessionID), sessionData...)
client.Expire(ctx, fmt.Sprintf("session:%s", sessionID), 30*time.Minute)

// 获取会话
session, err := client.HGetAll(ctx, fmt.Sprintf("session:%s", sessionID))

// 延长会话
client.Expire(ctx, fmt.Sprintf("session:%s", sessionID), 30*time.Minute)
```

### 缓存查询结果

```go
func GetUserByID(ctx context.Context, userID string) (*User, error) {
    cacheKey := fmt.Sprintf("user:%s", userID)
    
    // 尝试从缓存获取
    data, err := client.Get(ctx, cacheKey)
    if err == nil {
        var user User
        json.Unmarshal([]byte(data), &user)
        return &user, nil
    }
    
    // 缓存未命中，从数据库查询
    user := queryUserFromDB(userID)
    
    // 写入缓存
    data, _ := json.Marshal(user)
    client.Set(ctx, cacheKey, data, 1*time.Hour)
    
    return user, nil
}
```

### 限流器

```go
func CheckRateLimit(ctx context.Context, userID string) (bool, error) {
    key := fmt.Sprintf("ratelimit:%s", userID)
    
    count, err := client.Increment(ctx, key, 1)
    if err != nil {
        return false, err
    }
    
    // 第一次请求，设置过期时间
    if count == 1 {
        client.Expire(ctx, key, 1*time.Minute)
    }
    
    // 每分钟最多 100 次请求
    return count <= 100, nil
}
```

### 实时计数器

```go
// 在线用户数
client.SAdd(ctx, "online:users", "user123")

// 获取在线用户数
count, _ := client.SCard(ctx, "online:users")

// 用户下线
client.SRemove(ctx, "online:users", "user123")
```

## Consul 服务发现

当启用 Consul 时，客户端会自动从 Consul 发现 Redis 服务：

```yaml
use_consul: true
service_name: "redis-service"
```

工作流程：
1. 客户端启动时查询 Consul
2. 获取健康的 Redis 服务实例
3. 自动连接到发现的实例
4. 如果 Consul 不可用，回退到直连配置

## 性能优化建议

1. **使用连接池**: 配置合适的 `max_idle` 和 `max_active`
2. **批量操作**: 使用 `GetMultiple`, `HSet` 批量设置
3. **使用管道**: 对于大量操作，考虑使用 Redis Pipeline
4. **合理设置过期时间**: 避免内存泄漏
5. **避免使用 Keys**: 生产环境使用 Scan 代替
6. **使用二进制序列化**: 如 MessagePack，比 JSON 更高效

## 故障排查

### 连接失败
```bash
# 检查 Redis 服务
redis-cli ping

# 检查网络连接
telnet localhost 6379

# 检查 Consul 服务发现
curl http://localhost:8500/v1/health/service/redis-service
```

### 性能问题
```go
// 获取统计信息
stats, err := client.GetStats(ctx)
fmt.Printf("Stats: %+v\n", stats)
```

## 相关文档

- [Redis 官方文档](https://redis.io/documentation)
- [go-redis 文档](https://github.com/go-redis/redis)
- [统一基础设施 SDK](../../../docs/UNIFIED_INFRASTRUCTURE_SDK.md)
- [Consul 集成](../../../docs/CONSUL_INTEGRATION_SUMMARY.md)

## 最佳实践

1. **始终使用 context**: 支持超时和取消
2. **处理 redis.Nil 错误**: 区分键不存在和其他错误
3. **使用分布式锁保护临界区**: 避免竞态条件
4. **设置合理的过期时间**: 防止内存泄漏
5. **监控缓存命中率**: 优化缓存策略
6. **使用连接池**: 避免频繁建立连接
7. **异步处理 Pub/Sub**: 避免阻塞主流程



