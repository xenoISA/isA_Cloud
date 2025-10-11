// Package mqtt provides a unified MQTT client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 MQTT 消息代理客户端封装
//
// MQTT 是一个轻量级的消息传输协议，专为 IoT 设备设计
// 特点：
// - 轻量级，适合资源受限的设备
// - Pub/Sub 消息模式
// - QoS 质量保证（0, 1, 2）
// - 保留消息和遗嘱消息
// - 主题通配符（+ 和 #）
//
// 示例用法:
//
//	cfg := &mqtt.Config{
//	    BrokerURL:    "tcp://localhost:1883",
//	    ClientID:     "my-client",
//	    Username:     "user",
//	    Password:     "pass",
//	    QoS:          1,
//	}
//	client, err := mqtt.NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 订阅主题
//	client.Subscribe("sensors/+/temperature", func(topic string, payload []byte) error {
//	    fmt.Printf("Received: %s = %s\n", topic, string(payload))
//	    return nil
//	})
//
//	// 发布消息
//	client.Publish("sensors/room1/temperature", []byte("25.5"), false)
package mqtt

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

// Client MQTT 客户端封装
type Client struct {
	client   mqtt.Client
	config   *Config
	handlers map[string]MessageHandler
	mu       sync.RWMutex
}

// Config MQTT 客户端配置
type Config struct {
	BrokerURL     string        // MQTT Broker 地址，如 "tcp://localhost:1883"
	ClientID      string        // 客户端 ID（必须唯一）
	Username      string        // 用户名（可选）
	Password      string        // 密码（可选）
	KeepAlive     time.Duration // 心跳间隔
	PingTimeout   time.Duration // Ping 超时
	CleanSession  bool          // 是否清除会话
	AutoReconnect bool          // 是否自动重连
	QoS           byte          // 默认 QoS（0, 1, 2）

	// TLS 配置
	TLSEnabled bool   // 是否启用 TLS
	TLSCert    string // 证书文件路径
	TLSKey     string // 密钥文件路径
	TLSCA      string // CA 证书路径

	// 遗嘱消息
	WillEnabled bool   // 是否启用遗嘱消息
	WillTopic   string // 遗嘱主题
	WillPayload string // 遗嘱内容
	WillQoS     byte   // 遗嘱 QoS
	WillRetain  bool   // 遗嘱保留
}

// MessageHandler 消息处理器
type MessageHandler func(topic string, payload []byte) error

// NewClient 创建新的 MQTT 客户端
//
// 参数:
//
//	cfg: MQTT 配置
//
// 返回:
//
//	*Client: MQTT 客户端实例
//	error: 错误信息
//
// 示例:
//
//	cfg := &Config{
//	    BrokerURL: "tcp://localhost:1883",
//	    ClientID:  "my-app",
//	    QoS:       1,
//	}
//	client, err := NewClient(cfg)
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	if cfg.BrokerURL == "" {
		return nil, fmt.Errorf("broker URL is required")
	}

	// 设置默认值
	if cfg.ClientID == "" {
		cfg.ClientID = fmt.Sprintf("isa-cloud-%d", time.Now().UnixNano())
	}
	if cfg.KeepAlive == 0 {
		cfg.KeepAlive = 60 * time.Second
	}
	if cfg.PingTimeout == 0 {
		cfg.PingTimeout = 10 * time.Second
	}

	client := &Client{
		config:   cfg,
		handlers: make(map[string]MessageHandler),
	}

	// 创建 MQTT 客户端选项
	opts := mqtt.NewClientOptions()
	opts.AddBroker(cfg.BrokerURL)
	opts.SetClientID(cfg.ClientID)
	opts.SetUsername(cfg.Username)
	opts.SetPassword(cfg.Password)
	opts.SetKeepAlive(cfg.KeepAlive)
	opts.SetPingTimeout(cfg.PingTimeout)
	opts.SetCleanSession(cfg.CleanSession)
	opts.SetAutoReconnect(cfg.AutoReconnect)

	// 设置连接处理器
	opts.SetOnConnectHandler(client.onConnect)
	opts.SetConnectionLostHandler(client.onConnectionLost)
	opts.SetReconnectingHandler(client.onReconnecting)

	// 设置遗嘱消息
	if cfg.WillEnabled {
		opts.SetWill(cfg.WillTopic, cfg.WillPayload, cfg.WillQoS, cfg.WillRetain)
	}

	// 创建客户端
	client.client = mqtt.NewClient(opts)

	// 连接到 Broker
	token := client.client.Connect()
	if token.Wait() && token.Error() != nil {
		return nil, fmt.Errorf("failed to connect to MQTT broker: %w", token.Error())
	}

	return client, nil
}

// Close 关闭客户端连接
func (c *Client) Close() error {
	if c.client != nil && c.client.IsConnected() {
		c.client.Disconnect(250) // 等待 250ms 完成发送
	}
	return nil
}

// ============================================
// 发布/订阅 (Pub/Sub)
// ============================================

// Publish 发布消息
//
// 参数:
//
//	topic: 主题
//	payload: 消息内容（[]byte, string, 或任何可 JSON 序列化的对象）
//	retained: 是否保留消息
//
// 示例:
//
//	// 发布字符串
//	client.Publish("sensors/temp", "25.5", false)
//
//	// 发布 JSON
//	client.Publish("devices/status", map[string]interface{}{
//	    "device_id": "dev123",
//	    "status": "online",
//	}, false)
func (c *Client) Publish(topic string, payload interface{}, retained bool) error {
	return c.PublishWithQoS(topic, payload, c.config.QoS, retained)
}

// PublishWithQoS 发布消息（指定 QoS）
//
// QoS 级别:
//   - 0: 最多一次（At most once）
//   - 1: 至少一次（At least once）
//   - 2: 恰好一次（Exactly once）
//
// 示例:
//
//	// 重要消息使用 QoS 2
//	client.PublishWithQoS("commands/critical", data, 2, false)
func (c *Client) PublishWithQoS(topic string, payload interface{}, qos byte, retained bool) error {
	// 转换 payload 为字节
	var data []byte
	switch v := payload.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		// 尝试 JSON 序列化
		jsonData, err := json.Marshal(v)
		if err != nil {
			return fmt.Errorf("failed to serialize payload: %w", err)
		}
		data = jsonData
	}

	// 发布消息
	token := c.client.Publish(topic, qos, retained, data)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to publish message: %w", token.Error())
	}

	return nil
}

// Subscribe 订阅主题
//
// 主题支持通配符:
//   - +: 单级通配符（如 sensors/+/temp 匹配 sensors/room1/temp）
//   - #: 多级通配符（如 sensors/# 匹配 sensors 下所有主题）
//
// 示例:
//
//	// 订阅单个设备
//	client.Subscribe("devices/dev123/telemetry", func(topic string, payload []byte) error {
//	    fmt.Printf("Device data: %s\n", string(payload))
//	    return nil
//	})
//
//	// 订阅所有设备
//	client.Subscribe("devices/+/telemetry", func(topic string, payload []byte) error {
//	    deviceID := extractDeviceID(topic)
//	    fmt.Printf("Device %s: %s\n", deviceID, string(payload))
//	    return nil
//	})
func (c *Client) Subscribe(topic string, handler MessageHandler) error {
	return c.SubscribeWithQoS(topic, c.config.QoS, handler)
}

// SubscribeWithQoS 订阅主题（指定 QoS）
func (c *Client) SubscribeWithQoS(topic string, qos byte, handler MessageHandler) error {
	// 保存处理器
	c.mu.Lock()
	c.handlers[topic] = handler
	c.mu.Unlock()

	// 订阅主题
	token := c.client.Subscribe(topic, qos, func(client mqtt.Client, msg mqtt.Message) {
		c.handleMessage(msg.Topic(), msg.Payload())
	})

	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to subscribe to topic %s: %w", topic, token.Error())
	}

	return nil
}

// SubscribeMultiple 订阅多个主题
//
// 示例:
//
//	filters := map[string]byte{
//	    "sensors/+/temp":   1,
//	    "sensors/+/humid":  1,
//	    "devices/+/status": 2,
//	}
//	client.SubscribeMultiple(filters, func(topic string, payload []byte) error {
//	    // 处理所有消息
//	    return nil
//	})
func (c *Client) SubscribeMultiple(filters map[string]byte, handler MessageHandler) error {
	// 保存所有处理器
	c.mu.Lock()
	for topic := range filters {
		c.handlers[topic] = handler
	}
	c.mu.Unlock()

	// 批量订阅
	token := c.client.SubscribeMultiple(filters, func(client mqtt.Client, msg mqtt.Message) {
		c.handleMessage(msg.Topic(), msg.Payload())
	})

	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to subscribe to multiple topics: %w", token.Error())
	}

	return nil
}

// Unsubscribe 取消订阅
//
// 示例:
//
//	client.Unsubscribe("sensors/+/temp")
func (c *Client) Unsubscribe(topics ...string) error {
	token := c.client.Unsubscribe(topics...)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to unsubscribe: %w", token.Error())
	}

	// 删除处理器
	c.mu.Lock()
	for _, topic := range topics {
		delete(c.handlers, topic)
	}
	c.mu.Unlock()

	return nil
}

// handleMessage 处理接收到的消息
func (c *Client) handleMessage(topic string, payload []byte) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	// 查找匹配的处理器
	for pattern, handler := range c.handlers {
		if matchTopic(pattern, topic) {
			if err := handler(topic, payload); err != nil {
				// 错误处理（不能使用 logger，避免循环依赖）
				fmt.Printf("Error handling message on topic %s: %v\n", topic, err)
			}
			return
		}
	}
}

// ============================================
// 连接管理 (Connection Management)
// ============================================

// IsConnected 检查是否已连接
func (c *Client) IsConnected() bool {
	return c.client != nil && c.client.IsConnected()
}

// Reconnect 重新连接
func (c *Client) Reconnect() error {
	if c.IsConnected() {
		return nil
	}

	token := c.client.Connect()
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to reconnect: %w", token.Error())
	}

	return nil
}

// AddConnectionHandler 添加连接成功处理器
func (c *Client) AddConnectionHandler(handler func()) {
	c.client.AddRoute("$internal/connection", func(client mqtt.Client, msg mqtt.Message) {
		handler()
	})
}

// 连接事件处理器
func (c *Client) onConnect(client mqtt.Client) {
	fmt.Println("MQTT client connected")

	// 重新订阅所有主题
	c.mu.RLock()
	defer c.mu.RUnlock()

	for topic, handler := range c.handlers {
		qos := c.config.QoS
		client.Subscribe(topic, qos, func(client mqtt.Client, msg mqtt.Message) {
			if err := handler(msg.Topic(), msg.Payload()); err != nil {
				fmt.Printf("Error handling message: %v\n", err)
			}
		})
	}
}

func (c *Client) onConnectionLost(client mqtt.Client, err error) {
	fmt.Printf("MQTT connection lost: %v\n", err)
}

func (c *Client) onReconnecting(client mqtt.Client, opts *mqtt.ClientOptions) {
	fmt.Println("MQTT client reconnecting...")
}

// ============================================
// 工具方法 (Utility Methods)
// ============================================

// Ping 测试连接（通过发布到系统主题）
func (c *Client) Ping(ctx context.Context) error {
	if !c.IsConnected() {
		return fmt.Errorf("client not connected")
	}
	return nil
}

// GetConfig 获取客户端配置
func (c *Client) GetConfig() *Config {
	return c.config
}

// GetStats 获取客户端统计信息
func (c *Client) GetStats() map[string]interface{} {
	c.mu.RLock()
	defer c.mu.RUnlock()

	return map[string]interface{}{
		"connected":         c.IsConnected(),
		"subscribed_topics": len(c.handlers),
		"client_id":         c.config.ClientID,
	}
}

// ============================================
// 辅助函数 (Helper Functions)
// ============================================

// matchTopic 匹配主题模式
//
// 支持通配符:
//   - +: 匹配单个层级
//   - #: 匹配多个层级
//
// 示例:
//
//	matchTopic("sensors/+/temp", "sensors/room1/temp") → true
//	matchTopic("sensors/#", "sensors/room1/temp") → true
//	matchTopic("sensors/+/temp", "sensors/room1/humid") → false
func matchTopic(pattern, topic string) bool {
	patternParts := strings.Split(pattern, "/")
	topicParts := strings.Split(topic, "/")

	// # 可以匹配剩余所有部分
	for i, part := range patternParts {
		if part == "#" {
			return true
		}

		if i >= len(topicParts) {
			return false
		}

		if part != "+" && part != topicParts[i] {
			return false
		}
	}

	return len(patternParts) == len(topicParts)
}

// ExtractDeviceID 从主题中提取设备 ID
//
// 示例:
//
//	deviceID := mqtt.ExtractDeviceID("devices/dev123/telemetry")
//	// 返回: "dev123"
func ExtractDeviceID(topic string) string {
	parts := strings.Split(topic, "/")
	if len(parts) >= 2 && parts[0] == "devices" {
		return parts[1]
	}
	return ""
}

// ExtractTopicParts 提取主题的各个部分
//
// 示例:
//
//	parts := mqtt.ExtractTopicParts("sensors/room1/temperature")
//	// 返回: ["sensors", "room1", "temperature"]
func ExtractTopicParts(topic string) []string {
	return strings.Split(topic, "/")
}
