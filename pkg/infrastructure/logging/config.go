// Package logging provides unified logging infrastructure client configuration
// 为 isA Cloud 平台提供统一的日志基础设施客户端配置
package logging

import (
	"fmt"
	"time"
)

// LoggingConfig 日志基础设施配置
type LoggingConfig struct {
	// Loki 配置
	Loki LokiConfig `yaml:"loki" json:"loki"`
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


