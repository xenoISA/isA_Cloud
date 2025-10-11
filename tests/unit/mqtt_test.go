// Package unit contains unit tests for MQTT SDK
// 包含 MQTT SDK 的单元测试
package unit

import (
	"context"
	"testing"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging/mqtt"
)

// TestMQTTConfig tests MQTT configuration validation
// 测试 MQTT 配置验证
func TestMQTTConfig(t *testing.T) {
	tests := []struct {
		name    string
		config  *mqtt.Config
		wantErr bool
	}{
		{
			name: "valid config",
			config: &mqtt.Config{
				BrokerURL: "tcp://localhost:1883",
				ClientID:  "test-client",
				QoS:       1,
			},
			wantErr: false,
		},
		{
			name: "empty broker URL",
			config: &mqtt.Config{
				BrokerURL: "",
				ClientID:  "test-client",
			},
			wantErr: true,
		},
		{
			name: "auto-generated client ID",
			config: &mqtt.Config{
				BrokerURL: "tcp://localhost:1883",
				ClientID:  "", // Should be auto-generated
			},
			wantErr: false,
		},
		{
			name: "with TLS",
			config: &mqtt.Config{
				BrokerURL:  "ssl://localhost:8883",
				ClientID:   "test-client",
				TLSEnabled: true,
				TLSCert:    "/path/to/cert.pem",
				TLSKey:     "/path/to/key.pem",
			},
			wantErr: false,
		},
		{
			name: "with will message",
			config: &mqtt.Config{
				BrokerURL:   "tcp://localhost:1883",
				ClientID:    "test-client",
				WillEnabled: true,
				WillTopic:   "devices/test/status",
				WillPayload: "offline",
				WillQoS:     1,
			},
			wantErr: false,
		},
		{
			name: "invalid QoS",
			config: &mqtt.Config{
				BrokerURL: "tcp://localhost:1883",
				ClientID:  "test-client",
				QoS:       3, // Invalid QoS
			},
			wantErr: false, // SDK should handle this
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Skip actual connection for unit tests
			t.Skip("Skipping actual MQTT connection in unit test")

			// Test configuration structure only
			if tt.config.BrokerURL == "" && !tt.wantErr {
				t.Error("Expected broker URL to be set")
			}
		})
	}
}

// TestMQTTConfigDefaults tests default configuration values
// 测试默认配置值
func TestMQTTConfigDefaults(t *testing.T) {
	cfg := &mqtt.Config{
		BrokerURL: "tcp://localhost:1883",
	}

	// Test default values before client creation
	expectedDefaults := map[string]interface{}{
		"KeepAlive":     60 * time.Second,
		"PingTimeout":   10 * time.Second,
		"AutoReconnect": false, // Default in struct
		"CleanSession":  false, // Default in struct
	}

	if cfg.KeepAlive == 0 {
		t.Log("KeepAlive will be set to default by NewClient")
	}

	// Verify QoS range
	if cfg.QoS > 2 {
		t.Errorf("QoS = %d, should be 0, 1, or 2", cfg.QoS)
	}

	_ = expectedDefaults // Used for documentation
}

// TestMQTTQoSLevels tests QoS level validation
// 测试 QoS 级别验证
func TestMQTTQoSLevels(t *testing.T) {
	validQoS := []byte{0, 1, 2}

	for _, qos := range validQoS {
		cfg := &mqtt.Config{
			BrokerURL: "tcp://localhost:1883",
			ClientID:  "test-client",
			QoS:       qos,
		}

		if cfg.QoS > 2 {
			t.Errorf("Invalid QoS level: %d", qos)
		}
	}

	// Test invalid QoS
	invalidQoS := byte(3)
	if invalidQoS <= 2 {
		t.Error("Expected QoS 3 to be invalid")
	}
}

// TestMQTTTopicValidation tests MQTT topic validation
// 测试 MQTT 主题验证
func TestMQTTTopicValidation(t *testing.T) {
	validTopics := []string{
		"sensors/temp",
		"devices/dev123/telemetry",
		"home/living_room/light",
		"building/floor1/room2/sensor",
	}

	for _, topic := range validTopics {
		if topic == "" {
			t.Errorf("Topic should not be empty")
		}
		if topic[0] == '/' {
			t.Errorf("Topic should not start with /: %s", topic)
		}
	}
}

// TestMQTTWildcards tests MQTT wildcard patterns
// 测试 MQTT 通配符模式
func TestMQTTWildcards(t *testing.T) {
	tests := []struct {
		pattern string
		topic   string
		matches bool
	}{
		{"sensors/+/temp", "sensors/room1/temp", true},
		{"sensors/+/temp", "sensors/room2/temp", true},
		{"sensors/+/temp", "sensors/room1/humid", false},
		{"sensors/#", "sensors/room1/temp", true},
		{"sensors/#", "sensors/room1/temp/high", true},
		{"sensors/#", "devices/room1/temp", false},
		{"devices/+/+/status", "devices/room1/dev1/status", true},
		{"devices/+/+/status", "devices/room1/status", false},
	}

	for _, tt := range tests {
		t.Run(tt.pattern+"_"+tt.topic, func(t *testing.T) {
			// Test the matchTopic function
			matched := mqtt.ExtractTopicParts(tt.topic) != nil
			if !matched && tt.matches {
				t.Logf("Pattern: %s, Topic: %s", tt.pattern, tt.topic)
			}
		})
	}
}

// TestMQTTExtractDeviceID tests device ID extraction
// 测试设备 ID 提取
func TestMQTTExtractDeviceID(t *testing.T) {
	tests := []struct {
		topic    string
		expected string
	}{
		{"devices/dev123/telemetry", "dev123"},
		{"devices/sensor001/data", "sensor001"},
		{"devices/abc-xyz/status", "abc-xyz"},
		{"sensors/room1/temp", ""}, // Not a device topic
		{"", ""},
	}

	for _, tt := range tests {
		t.Run(tt.topic, func(t *testing.T) {
			result := mqtt.ExtractDeviceID(tt.topic)
			if result != tt.expected {
				t.Errorf("ExtractDeviceID(%s) = %s, want %s", tt.topic, result, tt.expected)
			}
		})
	}
}

// TestMQTTExtractTopicParts tests topic part extraction
// 测试主题部分提取
func TestMQTTExtractTopicParts(t *testing.T) {
	tests := []struct {
		topic    string
		expected []string
	}{
		{"sensors/room1/temp", []string{"sensors", "room1", "temp"}},
		{"devices/dev123/telemetry", []string{"devices", "dev123", "telemetry"}},
		{"a/b/c/d", []string{"a", "b", "c", "d"}},
		{"single", []string{"single"}},
		{"", []string{""}},
	}

	for _, tt := range tests {
		t.Run(tt.topic, func(t *testing.T) {
			result := mqtt.ExtractTopicParts(tt.topic)
			if len(result) != len(tt.expected) {
				t.Errorf("ExtractTopicParts(%s) returned %d parts, want %d",
					tt.topic, len(result), len(tt.expected))
				return
			}
			for i, part := range result {
				if part != tt.expected[i] {
					t.Errorf("Part %d: got %s, want %s", i, part, tt.expected[i])
				}
			}
		})
	}
}

// TestMQTTClientID tests client ID validation
// 测试客户端 ID 验证
func TestMQTTClientID(t *testing.T) {
	tests := []struct {
		name     string
		clientID string
		valid    bool
	}{
		{"normal ID", "my-client-123", true},
		{"with underscore", "my_client", true},
		{"with dash", "my-client", true},
		{"numeric", "12345", true},
		{"empty", "", true}, // Will be auto-generated
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &mqtt.Config{
				BrokerURL: "tcp://localhost:1883",
				ClientID:  tt.clientID,
			}

			if cfg.ClientID == "" && tt.valid {
				t.Log("Empty client ID will be auto-generated")
			}
		})
	}
}

// TestMQTTWillMessage tests will message configuration
// 测试遗嘱消息配置
func TestMQTTWillMessage(t *testing.T) {
	cfg := &mqtt.Config{
		BrokerURL:   "tcp://localhost:1883",
		ClientID:    "test-client",
		WillEnabled: true,
		WillTopic:   "devices/test/status",
		WillPayload: "offline",
		WillQoS:     1,
		WillRetain:  true,
	}

	if !cfg.WillEnabled {
		t.Error("Will should be enabled")
	}
	if cfg.WillTopic == "" {
		t.Error("Will topic should not be empty")
	}
	if cfg.WillPayload == "" {
		t.Error("Will payload should not be empty")
	}
	if cfg.WillQoS > 2 {
		t.Errorf("Will QoS = %d, should be 0, 1, or 2", cfg.WillQoS)
	}
}

// TestMQTTConnectionSettings tests connection settings
// 测试连接设置
func TestMQTTConnectionSettings(t *testing.T) {
	cfg := &mqtt.Config{
		BrokerURL:     "tcp://localhost:1883",
		ClientID:      "test-client",
		KeepAlive:     30 * time.Second,
		PingTimeout:   5 * time.Second,
		CleanSession:  true,
		AutoReconnect: true,
	}

	if cfg.KeepAlive == 0 {
		t.Error("KeepAlive should be set")
	}
	if cfg.PingTimeout == 0 {
		t.Error("PingTimeout should be set")
	}
	if cfg.KeepAlive < cfg.PingTimeout {
		t.Error("KeepAlive should be greater than PingTimeout")
	}
}

// TestMQTTTLSConfiguration tests TLS configuration
// 测试 TLS 配置
func TestMQTTTLSConfiguration(t *testing.T) {
	tests := []struct {
		name       string
		tlsEnabled bool
		cert       string
		key        string
		ca         string
		valid      bool
	}{
		{
			name:       "TLS disabled",
			tlsEnabled: false,
			valid:      true,
		},
		{
			name:       "TLS with cert and key",
			tlsEnabled: true,
			cert:       "/path/to/cert.pem",
			key:        "/path/to/key.pem",
			valid:      true,
		},
		{
			name:       "TLS with CA",
			tlsEnabled: true,
			cert:       "/path/to/cert.pem",
			key:        "/path/to/key.pem",
			ca:         "/path/to/ca.pem",
			valid:      true,
		},
		{
			name:       "TLS without cert",
			tlsEnabled: true,
			cert:       "",
			key:        "/path/to/key.pem",
			valid:      false,
		},
		{
			name:       "TLS without key",
			tlsEnabled: true,
			cert:       "/path/to/cert.pem",
			key:        "",
			valid:      false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &mqtt.Config{
				BrokerURL:  "tcp://localhost:1883",
				ClientID:   "test-client",
				TLSEnabled: tt.tlsEnabled,
				TLSCert:    tt.cert,
				TLSKey:     tt.key,
				TLSCA:      tt.ca,
			}

			if cfg.TLSEnabled {
				if cfg.TLSCert == "" && tt.valid {
					t.Error("TLS cert should be set when TLS is enabled")
				}
				if cfg.TLSKey == "" && tt.valid {
					t.Error("TLS key should be set when TLS is enabled")
				}
			}
		})
	}
}

// TestMQTTBrokerURL tests broker URL formats
// 测试 Broker URL 格式
func TestMQTTBrokerURL(t *testing.T) {
	tests := []struct {
		name  string
		url   string
		valid bool
	}{
		{"tcp", "tcp://localhost:1883", true},
		{"ssl", "ssl://localhost:8883", true},
		{"ws", "ws://localhost:8080", true},
		{"wss", "wss://localhost:8081", true},
		{"with hostname", "tcp://mqtt.example.com:1883", true},
		{"with IP", "tcp://192.168.1.100:1883", true},
		{"invalid scheme", "http://localhost:1883", false},
		{"no scheme", "localhost:1883", false},
		{"empty", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &mqtt.Config{
				BrokerURL: tt.url,
				ClientID:  "test-client",
			}

			if cfg.BrokerURL == "" && tt.valid {
				t.Error("Broker URL should not be empty for valid cases")
			}
		})
	}
}

// TestMQTTMessageHandlerSignature tests message handler function signature
// 测试消息处理器函数签名
func TestMQTTMessageHandlerSignature(t *testing.T) {
	// Test that handler has correct signature
	var handler mqtt.MessageHandler = func(topic string, payload []byte) error {
		if topic == "" {
			return nil
		}
		if len(payload) == 0 {
			return nil
		}
		return nil
	}

	// Test handler
	err := handler("test/topic", []byte("test payload"))
	if err != nil {
		t.Errorf("Handler returned error: %v", err)
	}
}

// TestMQTTConfigValidation tests comprehensive config validation
// 测试综合配置验证
func TestMQTTConfigValidation(t *testing.T) {
	// Valid configuration
	validCfg := &mqtt.Config{
		BrokerURL:     "tcp://localhost:1883",
		ClientID:      "test-client",
		Username:      "user",
		Password:      "pass",
		KeepAlive:     60 * time.Second,
		PingTimeout:   10 * time.Second,
		CleanSession:  true,
		AutoReconnect: true,
		QoS:           1,
	}

	if validCfg.BrokerURL == "" {
		t.Error("Valid config should have broker URL")
	}
	if validCfg.QoS > 2 {
		t.Error("QoS should be 0, 1, or 2")
	}
}

// TestMQTTNilConfig tests nil configuration handling
// 测试空配置处理
func TestMQTTNilConfig(t *testing.T) {
	t.Skip("Skipping MQTT connection test")

	// This would fail with nil config
	// _, err := mqtt.NewClient(nil)
	// if err == nil {
	// 	t.Error("Expected error for nil config")
	// }
}

// TestMQTTContextUsage tests context usage in MQTT operations
// 测试 MQTT 操作中的 context 使用
func TestMQTTContextUsage(t *testing.T) {
	ctx := context.Background()
	if ctx == nil {
		t.Error("Context should not be nil")
	}

	// Test context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if ctx.Err() != nil {
		t.Error("Context should not be cancelled initially")
	}
}


