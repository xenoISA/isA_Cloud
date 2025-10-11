// Package nats provides a unified NATS client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 NATS 事件总线客户端封装
//
// NATS 是一个高性能的消息系统，专为云原生应用设计
// 特点：
// - 高性能 Pub/Sub
// - JetStream 持久化
// - 请求/响应模式
// - 键值存储
// - 对象存储
//
// 示例用法:
//
//	cfg := &nats.Config{
//	    URLs:      []string{"nats://localhost:4222"},
//	    ClusterID: "isa-cloud-cluster",
//	}
//	client, err := nats.NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 发布消息
//	client.Publish(ctx, "events.user.created", []byte("data"))
//
//	// 订阅消息
//	client.Subscribe(ctx, "events.>", func(msg *Message) error {
//	    fmt.Printf("Received: %s\n", string(msg.Data))
//	    return nil
//	})
package nats

import (
	"context"
	"fmt"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// Client NATS 客户端封装
type Client struct {
	conn   *nats.Conn
	js     jetstream.JetStream
	config *Config
}

// Config NATS 客户端配置
type Config struct {
	// 基础配置
	URLs      []string // NATS 服务器地址列表
	ClusterID string   // 集群 ID
	ClientID  string   // 客户端 ID
	Username  string   // 用户名
	Password  string   // 密码
	Token     string   // Token
	NKeySeed  string   // NKey Seed

	// 连接配置
	MaxReconnect  int           // 最大重连次数
	ReconnectWait time.Duration // 重连等待时间
	Timeout       time.Duration // 连接超时
	PingInterval  time.Duration // Ping 间隔
	MaxPingsOut   int           // 最大未确认 Ping 数

	// JetStream 配置
	JetStreamEnabled bool   // 是否启用 JetStream
	JetStreamDomain  string // JetStream 域名

	// TLS 配置
	TLSEnabled bool   // 是否启用 TLS
	TLSCert    string // 证书文件路径
	TLSKey     string // 密钥文件路径
	TLSCA      string // CA 证书路径
}

// Message NATS 消息
type Message struct {
	Subject string
	Data    []byte
	Headers map[string][]string
	Reply   string
}

// MessageHandler 消息处理函数
type MessageHandler func(msg *Message) error

// NewClient 创建新的 NATS 客户端
//
// 参数:
//
//	cfg: NATS 配置
//
// 返回:
//
//	*Client: NATS 客户端实例
//	error: 错误信息
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if len(cfg.URLs) == 0 {
		cfg.URLs = []string{nats.DefaultURL}
	}
	if cfg.MaxReconnect == 0 {
		cfg.MaxReconnect = 10
	}
	if cfg.ReconnectWait == 0 {
		cfg.ReconnectWait = 2 * time.Second
	}
	if cfg.Timeout == 0 {
		cfg.Timeout = 10 * time.Second
	}
	if cfg.PingInterval == 0 {
		cfg.PingInterval = 2 * time.Minute
	}
	if cfg.MaxPingsOut == 0 {
		cfg.MaxPingsOut = 2
	}
	if cfg.ClientID == "" {
		cfg.ClientID = fmt.Sprintf("isa-cloud-%d", time.Now().UnixNano())
	}

	// 创建连接选项
	opts := []nats.Option{
		nats.Name(cfg.ClientID),
		nats.MaxReconnects(cfg.MaxReconnect),
		nats.ReconnectWait(cfg.ReconnectWait),
		nats.Timeout(cfg.Timeout),
		nats.PingInterval(cfg.PingInterval),
		nats.MaxPingsOutstanding(cfg.MaxPingsOut),
	}

	// 认证
	if cfg.Username != "" && cfg.Password != "" {
		opts = append(opts, nats.UserInfo(cfg.Username, cfg.Password))
	} else if cfg.Token != "" {
		opts = append(opts, nats.Token(cfg.Token))
	}

	// 连接到 NATS
	nc, err := nats.Connect(nats.FormatUrls(cfg.URLs), opts...)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to NATS: %w", err)
	}

	client := &Client{
		conn:   nc,
		config: cfg,
	}

	// 如果启用 JetStream，创建 JetStream 上下文
	if cfg.JetStreamEnabled {
		js, err := jetstream.New(nc)
		if err != nil {
			nc.Close()
			return nil, fmt.Errorf("failed to create JetStream: %w", err)
		}
		client.js = js
	}

	return client, nil
}

// Close 关闭客户端连接
func (c *Client) Close() error {
	if c.conn != nil {
		c.conn.Close()
	}
	return nil
}

// Ping 健康检查
func (c *Client) Ping(ctx context.Context) error {
	if err := c.conn.FlushWithContext(ctx); err != nil {
		return err
	}
	return nil
}

// ============================================
// 基础 Pub/Sub 操作
// ============================================

// Publish 发布消息
//
// 参数:
//
//	subject: 主题
//	data: 消息数据
//
// 示例:
//
//	err := client.Publish(ctx, "events.user.created", []byte("data"))
func (c *Client) Publish(ctx context.Context, subject string, data []byte) error {
	return c.conn.Publish(subject, data)
}

// PublishWithReply 发布消息并指定回复主题
func (c *Client) PublishWithReply(ctx context.Context, subject, reply string, data []byte) error {
	return c.conn.PublishRequest(subject, reply, data)
}

// Subscribe 订阅主题
//
// 参数:
//
//	subject: 主题（支持通配符 *, >）
//	handler: 消息处理函数
//
// 示例:
//
//	sub, err := client.Subscribe(ctx, "events.>", func(msg *Message) error {
//	    fmt.Printf("Received: %s\n", string(msg.Data))
//	    return nil
//	})
func (c *Client) Subscribe(ctx context.Context, subject string, handler MessageHandler) (*nats.Subscription, error) {
	return c.conn.Subscribe(subject, func(m *nats.Msg) {
		msg := &Message{
			Subject: m.Subject,
			Data:    m.Data,
			Reply:   m.Reply,
		}
		if err := handler(msg); err != nil {
			// 记录错误
			fmt.Printf("Handler error: %v\n", err)
		}
	})
}

// QueueSubscribe 队列组订阅（负载均衡）
//
// 示例:
//
//	sub, err := client.QueueSubscribe(ctx, "work.>", "workers", handler)
func (c *Client) QueueSubscribe(ctx context.Context, subject, queue string, handler MessageHandler) (*nats.Subscription, error) {
	return c.conn.QueueSubscribe(subject, queue, func(m *nats.Msg) {
		msg := &Message{
			Subject: m.Subject,
			Data:    m.Data,
			Reply:   m.Reply,
		}
		if err := handler(msg); err != nil {
			fmt.Printf("Handler error: %v\n", err)
		}
	})
}

// Request 请求/响应模式
//
// 示例:
//
//	resp, err := client.Request(ctx, "service.ping", []byte("hello"), 5*time.Second)
func (c *Client) Request(ctx context.Context, subject string, data []byte, timeout time.Duration) (*Message, error) {
	msg, err := c.conn.RequestWithContext(ctx, subject, data)
	if err != nil {
		return nil, err
	}

	return &Message{
		Subject: msg.Subject,
		Data:    msg.Data,
		Reply:   msg.Reply,
	}, nil
}

// ============================================
// JetStream 操作
// ============================================

// CreateStream 创建流
//
// 示例:
//
//	stream, err := client.CreateStream(ctx, &StreamConfig{
//	    Name:     "EVENTS",
//	    Subjects: []string{"events.>"},
//	})
func (c *Client) CreateStream(ctx context.Context, cfg *jetstream.StreamConfig) (jetstream.Stream, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.CreateStream(ctx, *cfg)
}

// GetStream 获取流信息
func (c *Client) GetStream(ctx context.Context, name string) (jetstream.Stream, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.Stream(ctx, name)
}

// DeleteStream 删除流
func (c *Client) DeleteStream(ctx context.Context, name string) error {
	if c.js == nil {
		return fmt.Errorf("JetStream not enabled")
	}
	return c.js.DeleteStream(ctx, name)
}

// PublishToStream 发布消息到流
//
// 示例:
//
//	ack, err := client.PublishToStream(ctx, "events.user.created", []byte("data"))
func (c *Client) PublishToStream(ctx context.Context, subject string, data []byte) (*jetstream.PubAck, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.Publish(ctx, subject, data)
}

// CreateConsumer 创建消费者
//
// 示例:
//
//	consumer, err := client.CreateConsumer(ctx, "EVENTS", &jetstream.ConsumerConfig{
//	    Name:          "my-consumer",
//	    FilterSubject: "events.user.>",
//	    AckPolicy:     jetstream.AckExplicitPolicy,
//	})
func (c *Client) CreateConsumer(ctx context.Context, streamName string, cfg *jetstream.ConsumerConfig) (jetstream.Consumer, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}

	stream, err := c.js.Stream(ctx, streamName)
	if err != nil {
		return nil, err
	}

	return stream.CreateConsumer(ctx, *cfg)
}

// ============================================
// 键值存储 (KV Store)
// ============================================

// CreateKeyValue 创建键值存储
//
// 示例:
//
//	kv, err := client.CreateKeyValue(ctx, "my-kv")
func (c *Client) CreateKeyValue(ctx context.Context, bucket string) (jetstream.KeyValue, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.CreateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket: bucket,
	})
}

// GetKeyValue 获取键值存储
func (c *Client) GetKeyValue(ctx context.Context, bucket string) (jetstream.KeyValue, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.KeyValue(ctx, bucket)
}

// ============================================
// 对象存储 (Object Store)
// ============================================

// CreateObjectStore 创建对象存储
//
// 示例:
//
//	obj, err := client.CreateObjectStore(ctx, "my-objects")
func (c *Client) CreateObjectStore(ctx context.Context, bucket string) (jetstream.ObjectStore, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.CreateObjectStore(ctx, jetstream.ObjectStoreConfig{
		Bucket: bucket,
	})
}

// GetObjectStore 获取对象存储
func (c *Client) GetObjectStore(ctx context.Context, bucket string) (jetstream.ObjectStore, error) {
	if c.js == nil {
		return nil, fmt.Errorf("JetStream not enabled")
	}
	return c.js.ObjectStore(ctx, bucket)
}

// ============================================
// 工具方法
// ============================================

// GetConfig 获取配置
func (c *Client) GetConfig() *Config {
	return c.config
}

// IsConnected 检查是否已连接
func (c *Client) IsConnected() bool {
	return c.conn != nil && c.conn.IsConnected()
}

// GetStats 获取统计信息
func (c *Client) GetStats() nats.Statistics {
	return c.conn.Stats()
}

// Flush 刷新缓冲区
func (c *Client) Flush(ctx context.Context) error {
	return c.conn.FlushWithContext(ctx)
}


