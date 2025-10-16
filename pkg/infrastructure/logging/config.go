// Package logging provides unified logging infrastructure client configuration
// 为 isA Cloud 平台提供统一的日志基础设施客户端配置
package logging

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/hashicorp/consul/api"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
	"github.com/spf13/viper"
)

// LoggingConfig 日志基础设施配置
type LoggingConfig struct {
	// Loki 配置
	Loki   LokiServiceConfig `yaml:"loki" json:"loki" mapstructure:"loki"`
	Consul ConsulConfig      `yaml:"consul" json:"consul" mapstructure:"consul"`
}

// LokiServiceConfig Loki 服务配置（用于 gRPC 服务）
type LokiServiceConfig struct {
	// 基础配置
	URL         string `yaml:"url" json:"url" mapstructure:"url"`
	UseConsul   bool   `yaml:"use_consul" json:"use_consul" mapstructure:"use_consul"`
	ServiceName string `yaml:"service_name" json:"service_name" mapstructure:"service_name"`
	GRPCPort    int    `yaml:"grpc_port" json:"grpc_port" mapstructure:"grpc_port"`

	// 认证配置
	TenantID string `yaml:"tenant_id" json:"tenant_id" mapstructure:"tenant_id"`
	Username string `yaml:"username" json:"username" mapstructure:"username"`
	Password string `yaml:"password" json:"password" mapstructure:"password"`

	// 推送配置
	BatchSize int    `yaml:"batch_size" json:"batch_size" mapstructure:"batch_size"`
	BatchWait string `yaml:"batch_wait" json:"batch_wait" mapstructure:"batch_wait"`
	Timeout   string `yaml:"timeout" json:"timeout" mapstructure:"timeout"`

	// 重试配置
	MaxRetries int    `yaml:"max_retries" json:"max_retries" mapstructure:"max_retries"`
	RetryWait  string `yaml:"retry_wait" json:"retry_wait" mapstructure:"retry_wait"`

	// 标签配置
	StaticLabels map[string]string `yaml:"static_labels" json:"static_labels" mapstructure:"static_labels"`
}

// ConsulConfig Consul 配置
type ConsulConfig struct {
	Enabled bool   `yaml:"enabled" json:"enabled" mapstructure:"enabled"`
	Host    string `yaml:"host" json:"host" mapstructure:"host"`
	Port    int    `yaml:"port" json:"port" mapstructure:"port"`
}

// LokiConfig Loki 日志聚合配置
type LokiConfig struct {
	// 基础配置
	URL         string `yaml:"url" json:"url"`                   // Loki 服务地址
	UseConsul   bool   `yaml:"use_consul" json:"use_consul"`     // 是否使用 Consul 服务发现
	ServiceName string `yaml:"service_name" json:"service_name"` // Consul 服务名

	// 认证配置
	TenantID string `yaml:"tenant_id" json:"tenant_id"` // 租户 ID（多租户模式）
	Username string `yaml:"username" json:"username"`   // 基础认证用户名
	Password string `yaml:"password" json:"password"`   // 基础认证密码

	// 推送配置
	BatchSize int           `yaml:"batch_size" json:"batch_size"` // 批量发送大小
	BatchWait time.Duration `yaml:"batch_wait" json:"batch_wait"` // 批量等待时间
	Timeout   time.Duration `yaml:"timeout" json:"timeout"`       // 请求超时时间

	// 重试配置
	MaxRetries int           `yaml:"max_retries" json:"max_retries"` // 最大重试次数
	RetryWait  time.Duration `yaml:"retry_wait" json:"retry_wait"`   // 重试等待时间

	// 标签配置
	StaticLabels map[string]string `yaml:"static_labels" json:"static_labels"` // 静态标签
}

// Validate 验证配置
func (c *LokiConfig) Validate() error {
	if c.URL == "" && !c.UseConsul {
		return fmt.Errorf("Loki URL is required when not using Consul")
	}

	if c.UseConsul && c.ServiceName == "" {
		return fmt.Errorf("service name is required when using Consul")
	}

	if c.BatchSize < 0 {
		return fmt.Errorf("batch size cannot be negative")
	}

	if c.BatchWait < 0 {
		return fmt.Errorf("batch wait cannot be negative")
	}

	return nil
}

// GetServiceName 获取服务名
func (c *LokiConfig) GetServiceName() string {
	return c.ServiceName
}

// UseConsulDiscovery 是否使用 Consul 服务发现
func (c *LokiConfig) UseConsulDiscovery() bool {
	return c.UseConsul
}

// SetDefaults 设置默认值
func (c *LokiConfig) SetDefaults() {
	if c.BatchSize == 0 {
		c.BatchSize = 100
	}
	if c.BatchWait == 0 {
		c.BatchWait = 1 * time.Second
	}
	if c.Timeout == 0 {
		c.Timeout = 10 * time.Second
	}
	if c.MaxRetries == 0 {
		c.MaxRetries = 3
	}
	if c.RetryWait == 0 {
		c.RetryWait = 1 * time.Second
	}
	if c.StaticLabels == nil {
		c.StaticLabels = make(map[string]string)
	}
}

// LoadLoggingConfig 加载日志服务配置
func LoadLoggingConfig() (*LoggingConfig, error) {
	v := viper.New()

	// 设置默认值
	setLoggingDefaults(v)

	// 配置文件设置
	v.SetConfigName("loki")
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
	var cfg LoggingConfig
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	return &cfg, nil
}

// setLoggingDefaults 设置默认配置值
func setLoggingDefaults(v *viper.Viper) {
	// Loki 默认配置
	v.SetDefault("loki.url", "http://localhost:3100")
	v.SetDefault("loki.use_consul", false)
	v.SetDefault("loki.service_name", "loki-service")
	v.SetDefault("loki.grpc_port", 50054)
	v.SetDefault("loki.batch_size", 100)
	v.SetDefault("loki.batch_wait", "1s")
	v.SetDefault("loki.timeout", "10s")
	v.SetDefault("loki.max_retries", 3)
	v.SetDefault("loki.retry_wait", "1s")

	// Consul 默认配置
	v.SetDefault("consul.enabled", false)
	v.SetDefault("consul.host", "localhost")
	v.SetDefault("consul.port", 8500)
}

// LoggingClientFactory 日志客户端工厂
type LoggingClientFactory struct {
	config       *LoggingConfig
	consulClient *api.Client
}

// NewLoggingClientFactory 创建日志客户端工厂
func NewLoggingClientFactory() (*LoggingClientFactory, error) {
	cfg, err := LoadLoggingConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load logging config: %w", err)
	}

	factory := &LoggingClientFactory{
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

// NewLokiClient 创建 Loki 客户端
func (f *LoggingClientFactory) NewLokiClient(ctx context.Context) (*loki.Client, error) {
	cfg := f.config.Loki

	// 如果使用 Consul 服务发现
	url := cfg.URL
	if cfg.UseConsul && f.consulClient != nil {
		discoveredURL, err := f.discoverLokiService(ctx)
		if err != nil {
			fmt.Printf("Warning: Failed to discover Loki from Consul, using direct connection: %v\n", err)
		} else {
			url = discoveredURL
		}
	}

	// 解析时间配置
	batchWait, _ := time.ParseDuration(cfg.BatchWait)
	if batchWait == 0 {
		batchWait = 1 * time.Second
	}
	timeout, _ := time.ParseDuration(cfg.Timeout)
	if timeout == 0 {
		timeout = 10 * time.Second
	}
	retryWait, _ := time.ParseDuration(cfg.RetryWait)
	if retryWait == 0 {
		retryWait = 1 * time.Second
	}

	// 创建 Loki 客户端配置
	lokiConfig := &loki.Config{
		URL:          url,
		TenantID:     cfg.TenantID,
		Username:     cfg.Username,
		Password:     cfg.Password,
		BatchSize:    cfg.BatchSize,
		BatchWait:    batchWait,
		Timeout:      timeout,
		MaxRetries:   cfg.MaxRetries,
		RetryWait:    retryWait,
		StaticLabels: cfg.StaticLabels,
	}

	// 创建客户端
	client, err := loki.NewClient(lokiConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create Loki client: %w", err)
	}

	return client, nil
}

// discoverLokiService 从 Consul 发现 Loki 服务
func (f *LoggingClientFactory) discoverLokiService(ctx context.Context) (string, error) {
	serviceName := f.config.Loki.ServiceName

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

	return fmt.Sprintf("http://%s:%d", service.Address, service.Port), nil
}

// GetConfig 获取配置
func (f *LoggingClientFactory) GetConfig() *LoggingConfig {
	return f.config
}

// LoadFromEnv 从环境变量快速创建配置
func LoadFromEnv() *LoggingConfig {
	cfg := &LoggingConfig{
		Loki: LokiServiceConfig{
			URL:          getEnv("LOKI_URL", "http://localhost:3100"),
			UseConsul:    getEnvBool("LOKI_USE_CONSUL", false),
			ServiceName:  getEnv("LOKI_SERVICE_NAME", "loki-service"),
			GRPCPort:     getEnvInt("LOKI_GRPC_PORT", 50054),
			BatchSize:    100,
			BatchWait:    "1s",
			Timeout:      "10s",
			MaxRetries:   3,
			RetryWait:    "1s",
			StaticLabels: make(map[string]string),
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


