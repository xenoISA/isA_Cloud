// Package messaging provides unified messaging infrastructure client configuration
// 为 isA Cloud 平台提供统一的消息基础设施客户端配置
package messaging

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging/mqtt"
	"github.com/spf13/viper"
)

// ConsulConfig Consul 服务发现配置
type ConsulConfig struct {
	Enabled bool   `yaml:"enabled" json:"enabled" mapstructure:"enabled"` // 是否启用 Consul
	Host    string `yaml:"host" json:"host" mapstructure:"host"`          // Consul 地址
	Port    int    `yaml:"port" json:"port" mapstructure:"port"`          // Consul 端口
}

// MessagingConfig 消息基础设施配置
type MessagingConfig struct {
	// MQTT 配置
	MQTT MQTTConfig `yaml:"mqtt" json:"mqtt"`

	// Consul 配置
	Consul ConsulConfig `yaml:"consul" json:"consul" mapstructure:"consul"`

	// NATS 配置（待实现）
	// NATS NATSConfig `yaml:"nats" json:"nats"`
}

// MQTTConfig MQTT 消息代理配置
type MQTTConfig struct {
	// 基础配置
	BrokerURL   string `yaml:"broker_url" json:"broker_url"`     // MQTT Broker 地址
	ClientID    string `yaml:"client_id" json:"client_id"`       // 客户端 ID
	UseConsul   bool   `yaml:"use_consul" json:"use_consul"`     // 是否使用 Consul 服务发现
	ServiceName string `yaml:"service_name" json:"service_name"` // Consul 服务名
	GRPCPort    int    `yaml:"grpc_port" json:"grpc_port"`       // gRPC 服务端口

	// 认证配置
	Username string `yaml:"username" json:"username"` // 用户名
	Password string `yaml:"password" json:"password"` // 密码

	// 连接配置
	KeepAlive     time.Duration `yaml:"keep_alive" json:"keep_alive"`         // 心跳间隔
	PingTimeout   time.Duration `yaml:"ping_timeout" json:"ping_timeout"`     // Ping 超时
	CleanSession  bool          `yaml:"clean_session" json:"clean_session"`   // 是否清除会话
	AutoReconnect bool          `yaml:"auto_reconnect" json:"auto_reconnect"` // 是否自动重连

	// QoS 配置
	QoS byte `yaml:"qos" json:"qos"` // 默认 QoS（0, 1, 2）

	// TLS 配置
	TLSEnabled bool   `yaml:"tls_enabled" json:"tls_enabled"` // 是否启用 TLS
	TLSCert    string `yaml:"tls_cert" json:"tls_cert"`       // 证书文件路径
	TLSKey     string `yaml:"tls_key" json:"tls_key"`         // 密钥文件路径
	TLSCA      string `yaml:"tls_ca" json:"tls_ca"`           // CA 证书路径

	// 遗嘱消息配置
	WillEnabled bool   `yaml:"will_enabled" json:"will_enabled"` // 是否启用遗嘱消息
	WillTopic   string `yaml:"will_topic" json:"will_topic"`     // 遗嘱主题
	WillPayload string `yaml:"will_payload" json:"will_payload"` // 遗嘱内容
	WillQoS     byte   `yaml:"will_qos" json:"will_qos"`         // 遗嘱 QoS
	WillRetain  bool   `yaml:"will_retain" json:"will_retain"`   // 遗嘱保留
}

// Validate 验证配置
func (c *MQTTConfig) Validate() error {
	if c.BrokerURL == "" && !c.UseConsul {
		return fmt.Errorf("MQTT broker URL is required when not using Consul")
	}

	if c.UseConsul && c.ServiceName == "" {
		return fmt.Errorf("service name is required when using Consul")
	}

	if c.QoS > 2 {
		return fmt.Errorf("QoS must be 0, 1, or 2")
	}

	if c.WillEnabled && c.WillTopic == "" {
		return fmt.Errorf("will topic is required when will is enabled")
	}

	if c.TLSEnabled {
		if c.TLSCert == "" || c.TLSKey == "" {
			return fmt.Errorf("TLS cert and key are required when TLS is enabled")
		}
	}

	return nil
}

// GetServiceName 获取服务名
func (c *MQTTConfig) GetServiceName() string {
	return c.ServiceName
}

// UseConsulDiscovery 是否使用 Consul 服务发现
func (c *MQTTConfig) UseConsulDiscovery() bool {
	return c.UseConsul
}

// SetDefaults 设置默认值
func (c *MQTTConfig) SetDefaults() {
	if c.ClientID == "" {
		c.ClientID = fmt.Sprintf("isa-cloud-%d", time.Now().UnixNano())
	}
	if c.KeepAlive == 0 {
		c.KeepAlive = 60 * time.Second
	}
	if c.PingTimeout == 0 {
		c.PingTimeout = 10 * time.Second
	}
	if c.QoS > 2 {
		c.QoS = 1 // 默认使用 QoS 1
	}
}

// MessagingClientFactory 消息客户端工厂
type MessagingClientFactory struct {
	config *MessagingConfig
}

// LoadMessagingConfig 加载消息配置
func LoadMessagingConfig() (*MessagingConfig, error) {
	v := viper.New()

	// 设置默认值
	setMessagingDefaults(v)

	// 配置文件设置
	v.SetConfigName("messaging")
	v.SetConfigType("yaml")
	v.AddConfigPath("./deployments/configs")
	v.AddConfigPath("../deployments/configs")
	v.AddConfigPath("./configs")
	v.AddConfigPath("../configs")
	v.AddConfigPath("/etc/isa_cloud")
	v.AddConfigPath(".")

	// 读取环境变量 (支持 ISA_CLOUD_MESSAGING_ 前缀)
	v.AutomaticEnv()
	v.SetEnvPrefix("ISA_CLOUD_MESSAGING")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))

	// 尝试读取配置文件
	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("failed to read config file: %w", err)
		}
		// 配置文件不存在，使用默认值和环境变量
	}

	// 解析配置
	var cfg MessagingConfig
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	// 额外支持简化的环境变量名（用于 Docker Compose）
	bindSimpleEnvVars(v, &cfg)

	// 设置默认值
	cfg.MQTT.SetDefaults()

	return &cfg, nil
}

// bindSimpleEnvVars 绑定简化的环境变量名（兼容 Docker Compose）
func bindSimpleEnvVars(v *viper.Viper, cfg *MessagingConfig) {
	// MQTT 配置
	if val := os.Getenv("MQTT_BROKER_URL"); val != "" {
		cfg.MQTT.BrokerURL = val
	}
	if val := os.Getenv("MQTT_USERNAME"); val != "" {
		cfg.MQTT.Username = val
	}
	if val := os.Getenv("MQTT_PASSWORD"); val != "" {
		cfg.MQTT.Password = val
	}

	// Consul 配置
	if val := os.Getenv("CONSUL_ENABLED"); val != "" {
		if enabled, err := strconv.ParseBool(val); err == nil {
			cfg.Consul.Enabled = enabled
		}
	}
	if val := os.Getenv("CONSUL_HOST"); val != "" {
		cfg.Consul.Host = val
	}
	if val := os.Getenv("CONSUL_PORT"); val != "" {
		if port, err := strconv.Atoi(val); err == nil {
			cfg.Consul.Port = port
		}
	}

	// gRPC 配置
	if val := os.Getenv("GRPC_PORT"); val != "" {
		if port, err := strconv.Atoi(val); err == nil {
			cfg.MQTT.GRPCPort = port
		}
	}
	if val := os.Getenv("SERVICE_NAME"); val != "" {
		cfg.MQTT.ServiceName = val
	}
}

// setMessagingDefaults 设置默认配置值
func setMessagingDefaults(v *viper.Viper) {
	// MQTT 默认配置
	v.SetDefault("mqtt.broker_url", "tcp://localhost:1883")
	v.SetDefault("mqtt.client_id", "")
	v.SetDefault("mqtt.use_consul", false)
	v.SetDefault("mqtt.service_name", "mqtt-service")
	v.SetDefault("mqtt.grpc_port", 50053)
	v.SetDefault("mqtt.keep_alive", "60s")
	v.SetDefault("mqtt.ping_timeout", "10s")
	v.SetDefault("mqtt.clean_session", true)
	v.SetDefault("mqtt.auto_reconnect", true)
	v.SetDefault("mqtt.qos", 1)
	v.SetDefault("mqtt.tls_enabled", false)
	v.SetDefault("mqtt.will_enabled", false)

	// Consul 默认配置
	v.SetDefault("consul.enabled", false)
	v.SetDefault("consul.host", "localhost")
	v.SetDefault("consul.port", 8500)
}

// NewMessagingClientFactory 创建消息客户端工厂
func NewMessagingClientFactory() (*MessagingClientFactory, error) {
	cfg, err := LoadMessagingConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load messaging config: %w", err)
	}

	factory := &MessagingClientFactory{
		config: cfg,
	}

	return factory, nil
}

// GetConfig 获取配置
func (f *MessagingClientFactory) GetConfig() *MessagingConfig {
	return f.config
}

// NewMQTTClient 创建 MQTT 客户端
func (f *MessagingClientFactory) NewMQTTClient(ctx context.Context) (*mqtt.Client, error) {
	cfg := &mqtt.Config{
		BrokerURL:     f.config.MQTT.BrokerURL,
		ClientID:      f.config.MQTT.ClientID,
		Username:      f.config.MQTT.Username,
		Password:      f.config.MQTT.Password,
		KeepAlive:     f.config.MQTT.KeepAlive,
		PingTimeout:   f.config.MQTT.PingTimeout,
		CleanSession:  f.config.MQTT.CleanSession,
		AutoReconnect: f.config.MQTT.AutoReconnect,
		QoS:           f.config.MQTT.QoS,
		TLSEnabled:    f.config.MQTT.TLSEnabled,
		TLSCert:       f.config.MQTT.TLSCert,
		TLSKey:        f.config.MQTT.TLSKey,
		TLSCA:         f.config.MQTT.TLSCA,
		WillEnabled:   f.config.MQTT.WillEnabled,
		WillTopic:     f.config.MQTT.WillTopic,
		WillPayload:   f.config.MQTT.WillPayload,
		WillQoS:       f.config.MQTT.WillQoS,
		WillRetain:    f.config.MQTT.WillRetain,
	}

	return mqtt.NewClient(cfg)
}


