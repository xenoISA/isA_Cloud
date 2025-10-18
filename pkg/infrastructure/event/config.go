// Package event provides configuration and client initialization for event services
// 为事件服务提供配置管理和客户端初始化
package event

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/hashicorp/consul/api"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event/nats"
	"github.com/spf13/viper"
)

// EventConfig 事件服务配置
type EventConfig struct {
	NATS   NATSServiceConfig `mapstructure:"nats"`
	Consul ConsulConfig      `mapstructure:"consul"`
}

// NATSServiceConfig NATS 服务配置
type NATSServiceConfig struct {
	// 基础配置
	URLs      []string `mapstructure:"urls"`
	ClusterID string   `mapstructure:"cluster_id"`
	ClientID  string   `mapstructure:"client_id"`
	Username  string   `mapstructure:"username"`
	Password  string   `mapstructure:"password"`
	Token     string   `mapstructure:"token"`
	NKeySeed  string   `mapstructure:"nkey_seed"`

	// 服务发现配置
	UseConsul   bool   `mapstructure:"use_consul"`
	ServiceName string `mapstructure:"service_name"`
	GRPCPort    int    `mapstructure:"grpc_port"`

	// 连接配置
	MaxReconnect  int    `mapstructure:"max_reconnect"`
	ReconnectWait string `mapstructure:"reconnect_wait"`
	Timeout       string `mapstructure:"timeout"`
	PingInterval  string `mapstructure:"ping_interval"`
	MaxPingsOut   int    `mapstructure:"max_pings_out"`

	// JetStream 配置
	JetStreamEnabled bool   `mapstructure:"jetstream_enabled"`
	JetStreamDomain  string `mapstructure:"jetstream_domain"`

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

// LoadEventConfig 加载事件服务配置
func LoadEventConfig() (*EventConfig, error) {
	v := viper.New()

	// 设置默认值
	setEventDefaults(v)

	// 配置文件设置
	v.SetConfigName("nats")
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
	var cfg EventConfig
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	return &cfg, nil
}

// setEventDefaults 设置默认配置值
func setEventDefaults(v *viper.Viper) {
	// NATS 默认配置
	v.SetDefault("nats.urls", []string{"nats://localhost:4222"})
	v.SetDefault("nats.cluster_id", "isa-cloud-cluster")
	v.SetDefault("nats.use_consul", false)
	v.SetDefault("nats.service_name", "nats-service")
	v.SetDefault("nats.grpc_port", 50056)
	v.SetDefault("nats.max_reconnect", 10)
	v.SetDefault("nats.reconnect_wait", "2s")
	v.SetDefault("nats.timeout", "10s")
	v.SetDefault("nats.ping_interval", "2m")
	v.SetDefault("nats.max_pings_out", 2)
	v.SetDefault("nats.jetstream_enabled", true)
	v.SetDefault("nats.tls_enabled", false)

	// Consul 默认配置
	v.SetDefault("consul.enabled", false)
	v.SetDefault("consul.host", "localhost")
	v.SetDefault("consul.port", 8500)
}

// EventClientFactory 事件客户端工厂
type EventClientFactory struct {
	config       *EventConfig
	consulClient *api.Client
}

// NewEventClientFactory 创建事件客户端工厂
func NewEventClientFactory() (*EventClientFactory, error) {
	cfg, err := LoadEventConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load event config: %w", err)
	}

	factory := &EventClientFactory{
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

// NewNATSClient 创建 NATS 客户端
//
// 如果启用了 Consul，会先尝试从 Consul 获取服务地址
func (f *EventClientFactory) NewNATSClient(ctx context.Context) (*nats.Client, error) {
	cfg := f.config.NATS

	// 如果使用 Consul 服务发现
	if cfg.UseConsul && f.consulClient != nil {
		urls, err := f.discoverNATSService(ctx)
		if err != nil {
			fmt.Printf("Warning: Failed to discover NATS from Consul, using direct connection: %v\n", err)
		} else {
			cfg.URLs = urls
		}
	}

	// 解析时间配置
	reconnectWait, _ := time.ParseDuration(cfg.ReconnectWait)
	timeout, _ := time.ParseDuration(cfg.Timeout)
	pingInterval, _ := time.ParseDuration(cfg.PingInterval)

	// 创建 NATS 客户端配置
	natsConfig := &nats.Config{
		URLs:             cfg.URLs,
		ClusterID:        cfg.ClusterID,
		ClientID:         cfg.ClientID,
		Username:         cfg.Username,
		Password:         cfg.Password,
		Token:            cfg.Token,
		NKeySeed:         cfg.NKeySeed,
		MaxReconnect:     cfg.MaxReconnect,
		ReconnectWait:    reconnectWait,
		Timeout:          timeout,
		PingInterval:     pingInterval,
		MaxPingsOut:      cfg.MaxPingsOut,
		JetStreamEnabled: cfg.JetStreamEnabled,
		JetStreamDomain:  cfg.JetStreamDomain,
		TLSEnabled:       cfg.TLSEnabled,
		TLSCert:          cfg.TLSCert,
		TLSKey:           cfg.TLSKey,
		TLSCA:            cfg.TLSCA,
	}

	// 创建客户端
	client, err := nats.NewClient(natsConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create NATS client: %w", err)
	}

	// 验证连接 (add timeout for health check)
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := client.Ping(pingCtx); err != nil {
		client.Close()
		return nil, fmt.Errorf("NATS health check failed: %w", err)
	}

	return client, nil
}

// discoverNATSService 从 Consul 发现 NATS 服务
func (f *EventClientFactory) discoverNATSService(ctx context.Context) ([]string, error) {
	serviceName := f.config.NATS.ServiceName

	// 查询健康的服务实例
	services, _, err := f.consulClient.Health().Service(serviceName, "", true, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to query service: %w", err)
	}

	if len(services) == 0 {
		return nil, fmt.Errorf("no healthy instances found for service: %s", serviceName)
	}

	// 收集所有健康实例的地址
	var urls []string
	for _, service := range services {
		url := fmt.Sprintf("nats://%s:%d", service.Service.Address, service.Service.Port)
		urls = append(urls, url)
	}

	return urls, nil
}

// GetConfig 获取配置
func (f *EventClientFactory) GetConfig() *EventConfig {
	return f.config
}

// LoadFromEnv 从环境变量快速创建配置
func LoadFromEnv() *EventConfig {
	urlsStr := getEnv("NATS_URLS", "nats://localhost:4222")
	urls := strings.Split(urlsStr, ",")

	cfg := &EventConfig{
		NATS: NATSServiceConfig{
			URLs:             urls,
			ClusterID:        getEnv("NATS_CLUSTER_ID", "isa-cloud-cluster"),
			ClientID:         getEnv("NATS_CLIENT_ID", ""),
			Username:         getEnv("NATS_USERNAME", ""),
			Password:         getEnv("NATS_PASSWORD", ""),
			Token:            getEnv("NATS_TOKEN", ""),
			UseConsul:        getEnvBool("NATS_USE_CONSUL", false),
			ServiceName:      getEnv("NATS_SERVICE_NAME", "nats-service"),
			GRPCPort:         getEnvInt("NATS_GRPC_PORT", 50056),
			MaxReconnect:     10,
			ReconnectWait:    "2s",
			Timeout:          "10s",
			PingInterval:     "2m",
			MaxPingsOut:      2,
			JetStreamEnabled: true,
			TLSEnabled:       getEnvBool("NATS_TLS_ENABLED", false),
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
