// Package messaging provides unified messaging infrastructure client configuration
// 为 isA Cloud 平台提供统一的消息基础设施客户端配置
package messaging

import (
	"fmt"
	"time"
)

// MessagingConfig 消息基础设施配置
type MessagingConfig struct {
	// MQTT 配置
	MQTT MQTTConfig `yaml:"mqtt" json:"mqtt"`

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


