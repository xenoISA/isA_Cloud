// Package clients provides gRPC client implementations for inter-service communication
// Client Factory - provides convenient client instantiation and management
//
// 文件名: pkg/grpc/clients/factory.go
package clients

import (
	"fmt"
	"sync"
)

// ClientFactory 客户端工厂
// 提供统一的客户端创建和管理接口
type ClientFactory struct {
	config        *FactoryConfig
	minioClient   *MinIOGRPCClient
	redisClient   *RedisGRPCClient
	mu            sync.RWMutex
	isInitialized bool
}

// FactoryConfig 工厂配置
type FactoryConfig struct {
	// MinIO gRPC Service
	MinIOHost string
	MinIOPort int

	// Redis gRPC Service
	RedisHost string
	RedisPort int

	// DuckDB gRPC Service
	DuckDBHost string
	DuckDBPort int

	// NATS gRPC Service
	NATSHost string
	NATSPort int

	// Loki gRPC Service
	LokiHost string
	LokiPort int

	// User/Organization context
	UserID         string
	OrganizationID string
}

// NewClientFactory 创建客户端工厂
func NewClientFactory(config *FactoryConfig) (*ClientFactory, error) {
	if config == nil {
		return nil, fmt.Errorf("factory config cannot be nil")
	}

	return &ClientFactory{
		config:        config,
		isInitialized: false,
	}, nil
}

// Initialize 初始化所有客户端连接
// 可以选择性地初始化部分客户端，传入需要初始化的服务名称
func (f *ClientFactory) Initialize(services ...string) error {
	f.mu.Lock()
	defer f.mu.Unlock()

	// 如果没有指定服务，初始化所有服务
	if len(services) == 0 {
		services = []string{"minio", "redis"}
	}

	for _, service := range services {
		switch service {
		case "minio":
			if err := f.initMinIOClient(); err != nil {
				return fmt.Errorf("failed to initialize MinIO client: %w", err)
			}
		case "redis":
			if err := f.initRedisClient(); err != nil {
				return fmt.Errorf("failed to initialize Redis client: %w", err)
			}
		default:
			return fmt.Errorf("unknown service: %s", service)
		}
	}

	f.isInitialized = true
	return nil
}

// initMinIOClient 初始化 MinIO 客户端
func (f *ClientFactory) initMinIOClient() error {
	if f.minioClient != nil {
		return nil // Already initialized
	}

	if f.config.MinIOHost == "" || f.config.MinIOPort == 0 {
		return fmt.Errorf("MinIO host and port must be specified")
	}

	client, err := NewMinIOGRPCClient(&MinIOGRPCConfig{
		Host:   f.config.MinIOHost,
		Port:   f.config.MinIOPort,
		UserID: f.config.UserID,
	})
	if err != nil {
		return err
	}

	f.minioClient = client
	return nil
}

// initRedisClient 初始化 Redis 客户端
func (f *ClientFactory) initRedisClient() error {
	if f.redisClient != nil {
		return nil // Already initialized
	}

	if f.config.RedisHost == "" || f.config.RedisPort == 0 {
		return fmt.Errorf("Redis host and port must be specified")
	}

	client, err := NewRedisGRPCClient(&RedisGRPCConfig{
		Host:           f.config.RedisHost,
		Port:           f.config.RedisPort,
		UserID:         f.config.UserID,
		OrganizationID: f.config.OrganizationID,
	})
	if err != nil {
		return err
	}

	f.redisClient = client
	return nil
}

// GetMinIOClient 获取 MinIO 客户端
func (f *ClientFactory) GetMinIOClient() (*MinIOGRPCClient, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()

	if f.minioClient == nil {
		return nil, fmt.Errorf("MinIO client not initialized, call Initialize() first")
	}

	return f.minioClient, nil
}

// GetRedisClient 获取 Redis 客户端
func (f *ClientFactory) GetRedisClient() (*RedisGRPCClient, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()

	if f.redisClient == nil {
		return nil, fmt.Errorf("Redis client not initialized, call Initialize() first")
	}

	return f.redisClient, nil
}

// MustGetMinIOClient 获取 MinIO 客户端，如果未初始化则 panic
func (f *ClientFactory) MustGetMinIOClient() *MinIOGRPCClient {
	client, err := f.GetMinIOClient()
	if err != nil {
		panic(err)
	}
	return client
}

// MustGetRedisClient 获取 Redis 客户端，如果未初始化则 panic
func (f *ClientFactory) MustGetRedisClient() *RedisGRPCClient {
	client, err := f.GetRedisClient()
	if err != nil {
		panic(err)
	}
	return client
}

// LazyGetMinIOClient 延迟获取 MinIO 客户端，如果未初始化则自动初始化
func (f *ClientFactory) LazyGetMinIOClient() (*MinIOGRPCClient, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	if f.minioClient == nil {
		if err := f.initMinIOClient(); err != nil {
			return nil, err
		}
	}

	return f.minioClient, nil
}

// LazyGetRedisClient 延迟获取 Redis 客户端，如果未初始化则自动初始化
func (f *ClientFactory) LazyGetRedisClient() (*RedisGRPCClient, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	if f.redisClient == nil {
		if err := f.initRedisClient(); err != nil {
			return nil, err
		}
	}

	return f.redisClient, nil
}

// Close 关闭所有客户端连接
func (f *ClientFactory) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()

	var errors []error

	if f.minioClient != nil {
		if err := f.minioClient.Close(); err != nil {
			errors = append(errors, fmt.Errorf("failed to close MinIO client: %w", err))
		}
		f.minioClient = nil
	}

	if f.redisClient != nil {
		if err := f.redisClient.Close(); err != nil {
			errors = append(errors, fmt.Errorf("failed to close Redis client: %w", err))
		}
		f.redisClient = nil
	}

	if len(errors) > 0 {
		return fmt.Errorf("errors closing clients: %v", errors)
	}

	f.isInitialized = false
	return nil
}

// IsInitialized 检查是否已初始化
func (f *ClientFactory) IsInitialized() bool {
	f.mu.RLock()
	defer f.mu.RUnlock()
	return f.isInitialized
}

// ============================================
// Helper Functions
// ============================================

// NewDefaultFactoryConfig 创建默认配置
// 使用标准端口号
func NewDefaultFactoryConfig(userID, organizationID string) *FactoryConfig {
	return &FactoryConfig{
		MinIOHost:      "localhost",
		MinIOPort:      50051,
		RedisHost:      "localhost",
		RedisPort:      50055,
		DuckDBHost:     "localhost",
		DuckDBPort:     50052,
		NATSHost:       "localhost",
		NATSPort:       50054,
		LokiHost:       "localhost",
		LokiPort:       50056,
		UserID:         userID,
		OrganizationID: organizationID,
	}
}

// NewFactoryFromEnv 从环境变量创建工厂配置
// 支持的环境变量：
// - ISA_MINIO_GRPC_HOST, ISA_MINIO_GRPC_PORT
// - ISA_REDIS_GRPC_HOST, ISA_REDIS_GRPC_PORT
// - ISA_DUCKDB_GRPC_HOST, ISA_DUCKDB_GRPC_PORT
// - ISA_NATS_GRPC_HOST, ISA_NATS_GRPC_PORT
// - ISA_LOKI_GRPC_HOST, ISA_LOKI_GRPC_PORT
// - ISA_USER_ID, ISA_ORGANIZATION_ID
func NewFactoryFromEnv() (*FactoryConfig, error) {
	// TODO: 实现从环境变量读取配置
	// 这里返回默认配置作为占位符
	return NewDefaultFactoryConfig("default_user", "default_org"), nil
}

// ============================================
// Usage Examples (for documentation)
// ============================================
// Example 1: Initialize all clients at once
//
//   factory, err := NewClientFactory(&FactoryConfig{
//       MinIOHost: "minio-grpc.example.com",
//       MinIOPort: 50051,
//       RedisHost: "redis-grpc.example.com",
//       RedisPort: 50055,
//       UserID: "user123",
//       OrganizationID: "org456",
//   })
//   if err := factory.Initialize(); err != nil {
//       log.Fatal(err)
//   }
//   defer factory.Close()
//
//   minioClient, _ := factory.GetMinIOClient()
//   redisClient, _ := factory.GetRedisClient()
//
// Example 2: Lazy initialization
//
//   factory, _ := NewClientFactory(config)
//   // Clients are initialized on first use
//   minioClient, err := factory.LazyGetMinIOClient()
//   redisClient, err := factory.LazyGetRedisClient()
//
// Example 3: Selective initialization
//
//   factory, _ := NewClientFactory(config)
//   // Only initialize MinIO client
//   if err := factory.Initialize("minio"); err != nil {
//       log.Fatal(err)
//   }
//   minioClient, _ := factory.GetMinIOClient()
