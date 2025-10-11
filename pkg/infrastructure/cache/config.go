// Package cache provides configuration and client initialization for cache services
// 为缓存服务提供配置管理和客户端初始化
package cache

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/hashicorp/consul/api"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/cache/redis"
	"github.com/spf13/viper"
)

// CacheConfig 缓存服务配置
type CacheConfig struct {
	Redis  RedisServiceConfig `mapstructure:"redis"`
	Consul ConsulConfig       `mapstructure:"consul"`
}

// RedisServiceConfig Redis 服务配置
type RedisServiceConfig struct {
	// 基础配置
	Host     string `mapstructure:"host"`
	Port     int    `mapstructure:"port"`
	Password string `mapstructure:"password"`
	Database int    `mapstructure:"database"`

	// 服务发现配置
	UseConsul   bool   `mapstructure:"use_consul"`
	ServiceName string `mapstructure:"service_name"`
	GRPCPort    int    `mapstructure:"grpc_port"`

	// 连接池配置
	MaxIdle        int    `mapstructure:"max_idle"`
	MaxActive      int    `mapstructure:"max_active"`
	IdleTimeout    string `mapstructure:"idle_timeout"`
	ConnectTimeout string `mapstructure:"connect_timeout"`
	ReadTimeout    string `mapstructure:"read_timeout"`
	WriteTimeout   string `mapstructure:"write_timeout"`

	// 集群配置
	ClusterEnabled bool     `mapstructure:"cluster_enabled"`
	ClusterNodes   []string `mapstructure:"cluster_nodes"`

	// Sentinel 配置
	SentinelEnabled    bool     `mapstructure:"sentinel_enabled"`
	SentinelMasterName string   `mapstructure:"sentinel_master_name"`
	SentinelNodes      []string `mapstructure:"sentinel_nodes"`

	// TLS 配置
	TLSEnabled bool   `mapstructure:"tls_enabled"`
	TLSCert    string `mapstructure:"tls_cert"`
	TLSKey     string `mapstructure:"tls_key"`
	TLSCA      string `mapstructure:"tls_ca"`
}

// ConsulConfig Consul 配置
type ConsulConfig struct {
	Enabled bool   `mapstructure:"enabled"`
	Host    string `mapstructure:"host"`
	Port    int    `mapstructure:"port"`
}

// LoadCacheConfig 加载缓存服务配置
func LoadCacheConfig() (*CacheConfig, error) {
	v := viper.New()

	// 设置默认值
	setCacheDefaults(v)

	// 配置文件设置
	v.SetConfigName("redis")
	v.SetConfigType("yaml")
	v.AddConfigPath("./configs/sdk")
	v.AddConfigPath("../configs/sdk")
	v.AddConfigPath("/etc/isa_cloud")
	v.AddConfigPath(".")

	// 读取环境变量
	v.AutomaticEnv()
	v.SetEnvPrefix("ISA_CLOUD")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))

	// 尝试读取配置文件
	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("failed to read config file: %w", err)
		}
	}

	// 解析配置
	var cfg CacheConfig
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	return &cfg, nil
}

// setCacheDefaults 设置默认配置值
func setCacheDefaults(v *viper.Viper) {
	// Redis 默认配置
	v.SetDefault("redis.host", "localhost")
	v.SetDefault("redis.port", 6379)
	v.SetDefault("redis.password", "")
	v.SetDefault("redis.database", 0)
	v.SetDefault("redis.use_consul", false)
	v.SetDefault("redis.service_name", "redis-service")
	v.SetDefault("redis.grpc_port", 50055)
	v.SetDefault("redis.max_idle", 10)
	v.SetDefault("redis.max_active", 100)
	v.SetDefault("redis.idle_timeout", "5m")
	v.SetDefault("redis.connect_timeout", "5s")
	v.SetDefault("redis.read_timeout", "3s")
	v.SetDefault("redis.write_timeout", "3s")
	v.SetDefault("redis.cluster_enabled", false)
	v.SetDefault("redis.sentinel_enabled", false)
	v.SetDefault("redis.tls_enabled", false)

	// Consul 默认配置
	v.SetDefault("consul.enabled", false)
	v.SetDefault("consul.host", "localhost")
	v.SetDefault("consul.port", 8500)
}

// CacheClientFactory 缓存客户端工厂
type CacheClientFactory struct {
	config       *CacheConfig
	consulClient *api.Client
}

// NewCacheClientFactory 创建缓存客户端工厂
func NewCacheClientFactory() (*CacheClientFactory, error) {
	cfg, err := LoadCacheConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load cache config: %w", err)
	}

	factory := &CacheClientFactory{
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

// NewRedisClient 创建 Redis 客户端
//
// 如果启用了 Consul，会先尝试从 Consul 获取服务地址
func (f *CacheClientFactory) NewRedisClient(ctx context.Context) (*redis.Client, error) {
	cfg := f.config.Redis

	// 如果使用 Consul 服务发现
	if cfg.UseConsul && f.consulClient != nil {
		host, port, err := f.discoverRedisService(ctx)
		if err != nil {
			fmt.Printf("Warning: Failed to discover Redis from Consul, using direct connection: %v\n", err)
		} else {
			cfg.Host = host
			cfg.Port = port
		}
	}

	// 解析时间配置
	idleTimeout, _ := time.ParseDuration(cfg.IdleTimeout)
	connectTimeout, _ := time.ParseDuration(cfg.ConnectTimeout)
	readTimeout, _ := time.ParseDuration(cfg.ReadTimeout)
	writeTimeout, _ := time.ParseDuration(cfg.WriteTimeout)

	// 创建 Redis 客户端配置
	redisConfig := &redis.Config{
		Host:           cfg.Host,
		Port:           cfg.Port,
		Password:       cfg.Password,
		Database:       cfg.Database,
		MaxIdle:        cfg.MaxIdle,
		MaxActive:      cfg.MaxActive,
		IdleTimeout:    idleTimeout,
		ConnectTimeout: connectTimeout,
		ReadTimeout:    readTimeout,
		WriteTimeout:   writeTimeout,
		ClusterEnabled: cfg.ClusterEnabled,
		ClusterNodes:   cfg.ClusterNodes,
		TLSEnabled:     cfg.TLSEnabled,
		TLSCert:        cfg.TLSCert,
		TLSKey:         cfg.TLSKey,
		TLSCA:          cfg.TLSCA,
	}

	// 创建客户端
	client, err := redis.NewClient(redisConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create Redis client: %w", err)
	}

	// 验证连接
	if err := client.Ping(ctx); err != nil {
		client.Close()
		return nil, fmt.Errorf("Redis health check failed: %w", err)
	}

	return client, nil
}

// discoverRedisService 从 Consul 发现 Redis 服务
func (f *CacheClientFactory) discoverRedisService(ctx context.Context) (string, int, error) {
	serviceName := f.config.Redis.ServiceName

	// 查询健康的服务实例
	services, _, err := f.consulClient.Health().Service(serviceName, "", true, nil)
	if err != nil {
		return "", 0, fmt.Errorf("failed to query service: %w", err)
	}

	if len(services) == 0 {
		return "", 0, fmt.Errorf("no healthy instances found for service: %s", serviceName)
	}

	// 使用第一个健康的实例
	service := services[0].Service

	return service.Address, service.Port, nil
}

// GetConfig 获取配置
func (f *CacheClientFactory) GetConfig() *CacheConfig {
	return f.config
}

// LoadFromEnv 从环境变量快速创建配置
func LoadFromEnv() *CacheConfig {
	cfg := &CacheConfig{
		Redis: RedisServiceConfig{
			Host:           getEnv("REDIS_HOST", "localhost"),
			Port:           getEnvInt("REDIS_PORT", 6379),
			Password:       getEnv("REDIS_PASSWORD", ""),
			Database:       getEnvInt("REDIS_DATABASE", 0),
			UseConsul:      getEnvBool("REDIS_USE_CONSUL", false),
			ServiceName:    getEnv("REDIS_SERVICE_NAME", "redis-service"),
			GRPCPort:       getEnvInt("REDIS_GRPC_PORT", 50055),
			MaxIdle:        10,
			MaxActive:      100,
			IdleTimeout:    "5m",
			ConnectTimeout: "5s",
			ReadTimeout:    "3s",
			WriteTimeout:   "3s",
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


