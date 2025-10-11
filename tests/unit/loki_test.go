// Package unit contains unit tests for Loki SDK
// 包含 Loki SDK 的单元测试
package unit

import (
	"context"
	"testing"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

// TestLokiConfig tests Loki configuration validation
// 测试 Loki 配置验证
func TestLokiConfig(t *testing.T) {
	tests := []struct {
		name    string
		config  *loki.Config
		wantErr bool
	}{
		{
			name: "valid config",
			config: &loki.Config{
				URL:       "http://localhost:3100",
				BatchSize: 100,
				BatchWait: 1 * time.Second,
			},
			wantErr: false,
		},
		{
			name: "empty URL",
			config: &loki.Config{
				URL:       "",
				BatchSize: 100,
			},
			wantErr: true,
		},
		{
			name: "with static labels",
			config: &loki.Config{
				URL:       "http://localhost:3100",
				BatchSize: 100,
				StaticLabels: map[string]string{
					"app":         "test",
					"environment": "test",
				},
			},
			wantErr: false,
		},
		{
			name: "with tenant ID",
			config: &loki.Config{
				URL:      "http://localhost:3100",
				TenantID: "test-tenant",
			},
			wantErr: false,
		},
		{
			name: "with authentication",
			config: &loki.Config{
				URL:      "http://localhost:3100",
				Username: "user",
				Password: "pass",
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			client, err := loki.NewClient(tt.config)
			if (err != nil) != tt.wantErr {
				t.Errorf("NewClient() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if client != nil {
				defer client.Close()
			}
		})
	}
}

// TestLokiClientCreation tests Loki client creation
// 测试 Loki 客户端创建
func TestLokiClientCreation(t *testing.T) {
	cfg := &loki.Config{
		URL:       "http://localhost:3100",
		BatchSize: 10,
		BatchWait: 100 * time.Millisecond,
		Timeout:   5 * time.Second,
	}

	client, err := loki.NewClient(cfg)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	if client == nil {
		t.Fatal("Client is nil")
	}
}

// TestLokiConfigDefaults tests default configuration values
// 测试默认配置值
func TestLokiConfigDefaults(t *testing.T) {
	cfg := &loki.Config{
		URL: "http://localhost:3100",
	}

	client, err := loki.NewClient(cfg)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	gotCfg := client.GetConfig()

	// Check defaults
	if gotCfg.BatchSize != 100 {
		t.Errorf("BatchSize = %d, want 100", gotCfg.BatchSize)
	}
	if gotCfg.BatchWait != 1*time.Second {
		t.Errorf("BatchWait = %v, want 1s", gotCfg.BatchWait)
	}
	if gotCfg.Timeout != 10*time.Second {
		t.Errorf("Timeout = %v, want 10s", gotCfg.Timeout)
	}
	if gotCfg.MaxRetries != 3 {
		t.Errorf("MaxRetries = %d, want 3", gotCfg.MaxRetries)
	}
}

// TestLokiLogEntry tests log entry structure
// 测试日志条目结构
func TestLokiLogEntry(t *testing.T) {
	entry := loki.LogEntry{
		Timestamp: time.Now(),
		Line:      "test log message",
		Labels: map[string]string{
			"app":   "test",
			"level": "info",
		},
	}

	if entry.Line == "" {
		t.Error("Log line is empty")
	}
	if len(entry.Labels) != 2 {
		t.Errorf("Labels count = %d, want 2", len(entry.Labels))
	}
}

// TestLokiLogLevels tests log level constants
// 测试日志级别常量
func TestLokiLogLevels(t *testing.T) {
	levels := []loki.LogLevel{
		loki.LogLevelDebug,
		loki.LogLevelInfo,
		loki.LogLevelWarn,
		loki.LogLevelError,
		loki.LogLevelFatal,
	}

	for _, level := range levels {
		if level == "" {
			t.Errorf("Log level is empty")
		}
	}
}

// TestLokiStaticLabels tests static label merging
// 测试静态标签合并
func TestLokiStaticLabels(t *testing.T) {
	cfg := &loki.Config{
		URL:       "http://localhost:3100",
		BatchSize: 10,
		StaticLabels: map[string]string{
			"app":         "test-app",
			"environment": "test",
		},
	}

	client, err := loki.NewClient(cfg)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	stats := client.GetStats()
	staticLabels, ok := stats["static_labels"].(map[string]string)
	if !ok {
		t.Fatal("Failed to get static labels from stats")
	}

	if len(staticLabels) != 2 {
		t.Errorf("Static labels count = %d, want 2", len(staticLabels))
	}
	if staticLabels["app"] != "test-app" {
		t.Errorf("app label = %s, want test-app", staticLabels["app"])
	}
}

// TestLokiGetStats tests client statistics
// 测试客户端统计信息
func TestLokiGetStats(t *testing.T) {
	cfg := &loki.Config{
		URL:       "http://localhost:3100",
		BatchSize: 50,
	}

	client, err := loki.NewClient(cfg)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	stats := client.GetStats()

	if _, ok := stats["buffer_size"]; !ok {
		t.Error("Stats missing buffer_size")
	}
	if _, ok := stats["batch_size"]; !ok {
		t.Error("Stats missing batch_size")
	}
	if batchSize, ok := stats["batch_size"].(int); ok && batchSize != 50 {
		t.Errorf("batch_size = %d, want 50", batchSize)
	}
}

// TestLokiHealthCheck tests health check functionality
// 测试健康检查功能
func TestLokiHealthCheck(t *testing.T) {
	// Note: This test will fail if Loki is not running
	// This is expected for unit tests without actual service
	t.Skip("Skipping health check test - requires running Loki service")

	cfg := &loki.Config{
		URL:     "http://localhost:3100",
		Timeout: 2 * time.Second,
	}

	client, err := loki.NewClient(cfg)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	ctx := context.Background()
	err = client.HealthCheck(ctx)
	if err != nil {
		t.Logf("Health check failed (expected without running service): %v", err)
	}
}

// TestLokiNilConfig tests nil configuration handling
// 测试空配置处理
func TestLokiNilConfig(t *testing.T) {
	_, err := loki.NewClient(nil)
	if err == nil {
		t.Error("Expected error for nil config, got nil")
	}
}

// TestLokiQueryOptions tests query options structure
// 测试查询选项结构
func TestLokiQueryOptions(t *testing.T) {
	opts := loki.QueryOptions{
		Start:     time.Now().Add(-1 * time.Hour),
		End:       time.Now(),
		Limit:     100,
		Direction: "backward",
	}

	if opts.Limit != 100 {
		t.Errorf("Limit = %d, want 100", opts.Limit)
	}
	if opts.Direction != "backward" {
		t.Errorf("Direction = %s, want backward", opts.Direction)
	}
	if opts.Start.After(opts.End) {
		t.Error("Start time is after End time")
	}
}

// TestLokiConfigValidation tests configuration validation
// 测试配置验证
func TestLokiConfigValidation(t *testing.T) {
	tests := []struct {
		name    string
		modify  func(*loki.Config)
		wantErr bool
	}{
		{
			name:    "valid config",
			modify:  func(c *loki.Config) {},
			wantErr: false,
		},
		{
			name: "zero batch size",
			modify: func(c *loki.Config) {
				c.BatchSize = 0 // Will use default
			},
			wantErr: false,
		},
		{
			name: "zero batch wait",
			modify: func(c *loki.Config) {
				c.BatchWait = 0 // Will use default
			},
			wantErr: false,
		},
		{
			name: "empty URL",
			modify: func(c *loki.Config) {
				c.URL = ""
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &loki.Config{
				URL:       "http://localhost:3100",
				BatchSize: 10,
			}
			tt.modify(cfg)

			_, err := loki.NewClient(cfg)
			if (err != nil) != tt.wantErr {
				t.Errorf("NewClient() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

// TestLokiBatchProcessing tests batch processing configuration
// 测试批处理配置
func TestLokiBatchProcessing(t *testing.T) {
	tests := []struct {
		name      string
		batchSize int
		batchWait time.Duration
	}{
		{"small batch", 10, 100 * time.Millisecond},
		{"medium batch", 100, 1 * time.Second},
		{"large batch", 500, 5 * time.Second},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &loki.Config{
				URL:       "http://localhost:3100",
				BatchSize: tt.batchSize,
				BatchWait: tt.batchWait,
			}

			client, err := loki.NewClient(cfg)
			if err != nil {
				t.Fatalf("Failed to create client: %v", err)
			}
			defer client.Close()

			gotCfg := client.GetConfig()
			if gotCfg.BatchSize != tt.batchSize {
				t.Errorf("BatchSize = %d, want %d", gotCfg.BatchSize, tt.batchSize)
			}
			if gotCfg.BatchWait != tt.batchWait {
				t.Errorf("BatchWait = %v, want %v", gotCfg.BatchWait, tt.batchWait)
			}
		})
	}
}
