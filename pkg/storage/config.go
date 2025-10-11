// Package storage provides configuration and client initialization for storage services
// 为存储服务提供配置管理和客户端初始化
//
// 文件名: pkg/storage/config.go
//
// 功能：
// - 从环境变量和配置文件加载配置
// - 支持 Consul 服务发现
// - 提供统一的客户端工厂方法
package storage

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/hashicorp/consul/api"
	"github.com/isa-cloud/isa_cloud/pkg/analytics/duckdb"
	"github.com/isa-cloud/isa_cloud/pkg/storage/minio"
	"github.com/spf13/viper"
)

// StorageConfig 存储服务配置
type StorageConfig struct {
	MinIO  MinIOServiceConfig  `mapstructure:"minio"`
	DuckDB DuckDBServiceConfig `mapstructure:"duckdb"`
	Consul ConsulConfig        `mapstructure:"consul"`
}

// MinIOServiceConfig MinIO 服务配置
type MinIOServiceConfig struct {
	// 直连配置
	Endpoint  string `mapstructure:"endpoint"`   // 如 "localhost:9000"
	AccessKey string `mapstructure:"access_key"` // 访问密钥
	SecretKey string `mapstructure:"secret_key"` // 私钥
	UseSSL    bool   `mapstructure:"use_ssl"`    // 是否使用 SSL
	Region    string `mapstructure:"region"`     // 区域

	// 服务发现配置
	UseConsul   bool   `mapstructure:"use_consul"`   // 是否使用 Consul 发现
	ServiceName string `mapstructure:"service_name"` // Consul 服务名
	GRPCPort    int    `mapstructure:"grpc_port"`    // gRPC 端口（用于服务注册）

	// 连接配置
	ConnectTimeout time.Duration `mapstructure:"connect_timeout"`
	RequestTimeout time.Duration `mapstructure:"request_timeout"`
	MaxRetries     int           `mapstructure:"max_retries"`
}

// DuckDBServiceConfig DuckDB 服务配置
type DuckDBServiceConfig struct {
	// 直连配置
	DatabasePath string `mapstructure:"database_path"` // 数据库文件路径，":memory:" 表示内存数据库
	MemoryLimit  string `mapstructure:"memory_limit"`  // 内存限制，如 "2GB"
	Threads      int    `mapstructure:"threads"`       // 线程数

	// 服务发现配置
	UseConsul   bool   `mapstructure:"use_consul"`   // 是否使用 Consul 发现
	ServiceName string `mapstructure:"service_name"` // Consul 服务名
	GRPCPort    int    `mapstructure:"grpc_port"`    // gRPC 端口

	// 连接配置
	MaxOpenConns int           `mapstructure:"max_open_conns"`
	MaxIdleConns int           `mapstructure:"max_idle_conns"`
	ConnMaxLife  time.Duration `mapstructure:"conn_max_life"`

	// 扩展
	Extensions []string `mapstructure:"extensions"` // 自动加载的扩展
}

// ConsulConfig Consul 配置
type ConsulConfig struct {
	Enabled bool   `mapstructure:"enabled"` // 是否启用 Consul
	Host    string `mapstructure:"host"`    // Consul 地址
	Port    int    `mapstructure:"port"`    // Consul 端口
}

// LoadStorageConfig 加载存储服务配置
//
// 优先级（从高到低）：
// 1. 环境变量（ISA_CLOUD_STORAGE_*）
// 2. 配置文件（storage.yaml）
// 3. 默认值
//
// 示例：
//
//	cfg, err := storage.LoadStorageConfig()
//	if err != nil {
//	    log.Fatal(err)
//	}
func LoadStorageConfig() (*StorageConfig, error) {
	v := viper.New()

	// 设置默认值
	setStorageDefaults(v)

	// 配置文件设置
	v.SetConfigName("storage")
	v.SetConfigType("yaml")
	v.AddConfigPath("./deployments/configs")
	v.AddConfigPath("../deployments/configs")
	v.AddConfigPath("/etc/isa_cloud")
	v.AddConfigPath(".")

	// 读取环境变量
	v.AutomaticEnv()
	v.SetEnvPrefix("ISA_CLOUD_STORAGE")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))

	// 尝试读取配置文件
	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("failed to read config file: %w", err)
		}
		// 配置文件不存在，使用默认值和环境变量
	}

	// 解析配置
	var cfg StorageConfig
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	return &cfg, nil
}

// setStorageDefaults 设置默认配置值
func setStorageDefaults(v *viper.Viper) {
	// MinIO 默认配置
	v.SetDefault("minio.endpoint", "localhost:9000")
	v.SetDefault("minio.access_key", "minioadmin")
	v.SetDefault("minio.secret_key", "minioadmin")
	v.SetDefault("minio.use_ssl", false)
	v.SetDefault("minio.region", "us-east-1")
	v.SetDefault("minio.use_consul", false)
	v.SetDefault("minio.service_name", "minio-service")
	v.SetDefault("minio.grpc_port", 50051)
	v.SetDefault("minio.connect_timeout", "30s")
	v.SetDefault("minio.request_timeout", "5m")
	v.SetDefault("minio.max_retries", 3)

	// DuckDB 默认配置
	v.SetDefault("duckdb.database_path", ":memory:")
	v.SetDefault("duckdb.memory_limit", "2GB")
	v.SetDefault("duckdb.threads", 4)
	v.SetDefault("duckdb.use_consul", false)
	v.SetDefault("duckdb.service_name", "duckdb-service")
	v.SetDefault("duckdb.grpc_port", 50052)
	v.SetDefault("duckdb.max_open_conns", 10)
	v.SetDefault("duckdb.max_idle_conns", 5)
	v.SetDefault("duckdb.conn_max_life", "1h")
	v.SetDefault("duckdb.extensions", []string{"httpfs", "parquet"})

	// Consul 默认配置
	v.SetDefault("consul.enabled", true)
	v.SetDefault("consul.host", "localhost")
	v.SetDefault("consul.port", 8500)
}

// StorageClientFactory 存储客户端工厂
type StorageClientFactory struct {
	config       *StorageConfig
	consulClient *api.Client
}

// NewStorageClientFactory 创建存储客户端工厂
//
// 示例：
//
//	factory, err := storage.NewStorageClientFactory()
//	if err != nil {
//	    log.Fatal(err)
//	}
func NewStorageClientFactory() (*StorageClientFactory, error) {
	cfg, err := LoadStorageConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load storage config: %w", err)
	}

	factory := &StorageClientFactory{
		config: cfg,
	}

	// 如果启用了 Consul，创建 Consul 客户端
	if cfg.Consul.Enabled {
		consulConfig := api.DefaultConfig()
		consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

		consulClient, err := api.NewClient(consulConfig)
		if err != nil {
			return nil, fmt.Errorf("failed to create consul client: %w", err)
		}

		factory.consulClient = consulClient
	}

	return factory, nil
}

// NewMinIOClient 创建 MinIO 客户端
//
// 如果启用了 Consul，会先尝试从 Consul 获取服务地址
// 如果 Consul 不可用或未启用，使用配置的直连地址
//
// 示例：
//
//	factory, _ := storage.NewStorageClientFactory()
//	minioClient, err := factory.NewMinIOClient(context.Background())
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer minioClient.Close()
func (f *StorageClientFactory) NewMinIOClient(ctx context.Context) (*minio.Client, error) {
	cfg := f.config.MinIO

	// 如果使用 Consul 服务发现
	if cfg.UseConsul && f.consulClient != nil {
		endpoint, err := f.discoverMinIOService(ctx)
		if err != nil {
			fmt.Printf("Warning: Failed to discover MinIO from Consul, using direct connection: %v\n", err)
		} else {
			cfg.Endpoint = endpoint
		}
	}

	// 创建 MinIO 客户端配置
	minioConfig := &minio.Config{
		Endpoint:       cfg.Endpoint,
		AccessKey:      cfg.AccessKey,
		SecretKey:      cfg.SecretKey,
		UseSSL:         cfg.UseSSL,
		Region:         cfg.Region,
		ConnectTimeout: cfg.ConnectTimeout,
		RequestTimeout: cfg.RequestTimeout,
		MaxRetries:     cfg.MaxRetries,
	}

	// 创建客户端
	client, err := minio.NewClient(minioConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create MinIO client: %w", err)
	}

	// 验证连接
	if err := client.HealthCheck(ctx); err != nil {
		client.Close()
		return nil, fmt.Errorf("MinIO health check failed: %w", err)
	}

	return client, nil
}

// NewDuckDBClient 创建 DuckDB 客户端
//
// 示例：
//
//	factory, _ := storage.NewStorageClientFactory()
//	duckdbClient, err := factory.NewDuckDBClient(context.Background())
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer duckdbClient.Close()
func (f *StorageClientFactory) NewDuckDBClient(ctx context.Context) (*duckdb.Client, error) {
	cfg := f.config.DuckDB

	// 如果使用 Consul 服务发现
	// DuckDB 通常是本地或直连，但也可以通过 gRPC 服务提供
	// 这里先使用直连方式

	// 创建 DuckDB 客户端配置
	duckdbConfig := &duckdb.Config{
		DatabasePath: cfg.DatabasePath,
		MemoryLimit:  cfg.MemoryLimit,
		Threads:      cfg.Threads,
		MaxOpenConns: cfg.MaxOpenConns,
		MaxIdleConns: cfg.MaxIdleConns,
		ConnMaxLife:  cfg.ConnMaxLife,
		Extensions:   cfg.Extensions,
	}

	// 创建客户端
	client, err := duckdb.NewClient(duckdbConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create DuckDB client: %w", err)
	}

	// 验证连接
	if err := client.Ping(ctx); err != nil {
		client.Close()
		return nil, fmt.Errorf("DuckDB health check failed: %w", err)
	}

	return client, nil
}

// discoverMinIOService 从 Consul 发现 MinIO 服务
func (f *StorageClientFactory) discoverMinIOService(ctx context.Context) (string, error) {
	serviceName := f.config.MinIO.ServiceName

	// 查询健康的服务实例
	services, _, err := f.consulClient.Health().Service(serviceName, "", true, nil)
	if err != nil {
		return "", fmt.Errorf("failed to query service: %w", err)
	}

	if len(services) == 0 {
		return "", fmt.Errorf("no healthy instances found for service: %s", serviceName)
	}

	// 使用第一个健康的实例
	service := services[0].Service
	endpoint := fmt.Sprintf("%s:%d", service.Address, service.Port)

	return endpoint, nil
}

// GetConfig 获取配置
func (f *StorageClientFactory) GetConfig() *StorageConfig {
	return f.config
}

// LoadFromEnv 从环境变量快速创建配置（简化版）
//
// 环境变量：
//   - MINIO_ENDPOINT (默认: localhost:9000)
//   - MINIO_ACCESS_KEY (默认: minioadmin)
//   - MINIO_SECRET_KEY (默认: minioadmin)
//   - MINIO_USE_SSL (默认: false)
//   - DUCKDB_PATH (默认: :memory:)
//   - DUCKDB_MEMORY_LIMIT (默认: 2GB)
//   - CONSUL_ENABLED (默认: false)
//
// 示例：
//
//	// 在 Python 服务中设置环境变量
//	os.environ["MINIO_ENDPOINT"] = "minio:9000"
//	os.environ["CONSUL_ENABLED"] = "true"
func LoadFromEnv() *StorageConfig {
	cfg := &StorageConfig{
		MinIO: MinIOServiceConfig{
			Endpoint:       getEnv("MINIO_ENDPOINT", "localhost:9000"),
			AccessKey:      getEnv("MINIO_ACCESS_KEY", "minioadmin"),
			SecretKey:      getEnv("MINIO_SECRET_KEY", "minioadmin"),
			UseSSL:         getEnvBool("MINIO_USE_SSL", false),
			Region:         getEnv("MINIO_REGION", "us-east-1"),
			UseConsul:      getEnvBool("MINIO_USE_CONSUL", false),
			ServiceName:    getEnv("MINIO_SERVICE_NAME", "minio-service"),
			GRPCPort:       getEnvInt("MINIO_GRPC_PORT", 50051),
			ConnectTimeout: 30 * time.Second,
			RequestTimeout: 5 * time.Minute,
			MaxRetries:     3,
		},
		DuckDB: DuckDBServiceConfig{
			DatabasePath: getEnv("DUCKDB_PATH", ":memory:"),
			MemoryLimit:  getEnv("DUCKDB_MEMORY_LIMIT", "2GB"),
			Threads:      getEnvInt("DUCKDB_THREADS", 4),
			UseConsul:    getEnvBool("DUCKDB_USE_CONSUL", false),
			ServiceName:  getEnv("DUCKDB_SERVICE_NAME", "duckdb-service"),
			GRPCPort:     getEnvInt("DUCKDB_GRPC_PORT", 50052),
			MaxOpenConns: 10,
			MaxIdleConns: 5,
			ConnMaxLife:  1 * time.Hour,
			Extensions:   []string{"httpfs", "parquet"},
		},
		Consul: ConsulConfig{
			Enabled: getEnvBool("CONSUL_ENABLED", false),
			Host:    getEnv("CONSUL_HOST", "localhost"),
			Port:    getEnvInt("CONSUL_PORT", 8500),
		},
	}

	return cfg
}

// 辅助函数
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvBool(key string, defaultValue bool) bool {
	if value := os.Getenv(key); value != "" {
		return strings.ToLower(value) == "true" || value == "1"
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		var result int
		fmt.Sscanf(value, "%d", &result)
		return result
	}
	return defaultValue
}


