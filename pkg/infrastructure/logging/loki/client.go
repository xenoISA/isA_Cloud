// Package loki provides a unified Loki client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 Loki 日志聚合客户端封装
//
// Loki 是 Grafana Labs 开发的日志聚合系统，类似 Prometheus 但用于日志
// 特点：
// - 高效的日志存储和查询
// - 使用标签而非全文索引
// - 与 Grafana 无缝集成
// - 支持 LogQL 查询语言
//
// 示例用法:
//
//	cfg := &loki.Config{
//	    URL:       "http://localhost:3100",
//	    BatchSize: 100,
//	    TenantID:  "tenant-1",
//	}
//	client, err := loki.NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 推送日志
//	client.PushLog("app", "info", "Application started", map[string]string{
//	    "service": "mcp",
//	    "version": "1.0.0",
//	})
package loki

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

// Client Loki 客户端封装
type Client struct {
	config     *Config
	httpClient *http.Client
	buffer     []LogEntry
	bufferMu   sync.Mutex
	stopCh     chan struct{}
	wg         sync.WaitGroup
}

// Config Loki 客户端配置
type Config struct {
	URL          string            // Loki 服务地址，如 "http://localhost:3100"
	TenantID     string            // 租户 ID（多租户模式）
	Username     string            // 基础认证用户名
	Password     string            // 基础认证密码
	BatchSize    int               // 批量发送大小
	BatchWait    time.Duration     // 批量等待时间
	Timeout      time.Duration     // 请求超时时间
	StaticLabels map[string]string // 静态标签（所有日志都会带上）
	MaxRetries   int               // 最大重试次数
	RetryWait    time.Duration     // 重试等待时间
}

// LogEntry 日志条目
type LogEntry struct {
	Timestamp time.Time         // 时间戳
	Line      string            // 日志内容
	Labels    map[string]string // 标签
}

// LogLevel 日志级别
type LogLevel string

const (
	LogLevelDebug LogLevel = "debug"
	LogLevelInfo  LogLevel = "info"
	LogLevelWarn  LogLevel = "warn"
	LogLevelError LogLevel = "error"
	LogLevelFatal LogLevel = "fatal"
)

// NewClient 创建新的 Loki 客户端
//
// 参数:
//
//	cfg: Loki 配置
//
// 返回:
//
//	*Client: Loki 客户端实例
//	error: 错误信息
//
// 示例:
//
//	cfg := &Config{
//	    URL:       "http://localhost:3100",
//	    BatchSize: 100,
//	    BatchWait: 1 * time.Second,
//	}
//	client, err := NewClient(cfg)
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	if cfg.URL == "" {
		return nil, fmt.Errorf("Loki URL is required")
	}

	// 设置默认值
	if cfg.BatchSize == 0 {
		cfg.BatchSize = 100
	}
	if cfg.BatchWait == 0 {
		cfg.BatchWait = 1 * time.Second
	}
	if cfg.Timeout == 0 {
		cfg.Timeout = 10 * time.Second
	}
	if cfg.MaxRetries == 0 {
		cfg.MaxRetries = 3
	}
	if cfg.RetryWait == 0 {
		cfg.RetryWait = 1 * time.Second
	}
	if cfg.StaticLabels == nil {
		cfg.StaticLabels = make(map[string]string)
	}

	client := &Client{
		config: cfg,
		httpClient: &http.Client{
			Timeout: cfg.Timeout,
		},
		buffer: make([]LogEntry, 0, cfg.BatchSize),
		stopCh: make(chan struct{}),
	}

	// 启动后台批量发送
	client.wg.Add(1)
	go client.batchSender()

	return client, nil
}

// Close 关闭客户端并刷新所有缓冲的日志
func (c *Client) Close() error {
	// 停止后台发送
	close(c.stopCh)
	c.wg.Wait()

	// 刷新剩余日志
	return c.Flush()
}

// ============================================
// 日志推送 (Log Push)
// ============================================

// PushLog 推送单条日志（简化接口）
//
// 参数:
//
//	app: 应用名称
//	level: 日志级别
//	message: 日志消息
//	labels: 额外标签
//
// 示例:
//
//	client.PushLog("mcp", "info", "User logged in", map[string]string{
//	    "user_id": "123",
//	    "action": "login",
//	})
func (c *Client) PushLog(app string, level LogLevel, message string, labels map[string]string) error {
	allLabels := c.mergeLabels(labels)
	allLabels["app"] = app
	allLabels["level"] = string(level)

	entry := LogEntry{
		Timestamp: time.Now(),
		Line:      message,
		Labels:    allLabels,
	}

	return c.Push(entry)
}

// Push 推送日志条目
func (c *Client) Push(entry LogEntry) error {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()

	// 添加到缓冲区
	c.buffer = append(c.buffer, entry)

	// 如果达到批量大小，立即发送
	if len(c.buffer) >= c.config.BatchSize {
		return c.flushLocked()
	}

	return nil
}

// PushBatch 批量推送日志
//
// 示例:
//
//	entries := []LogEntry{
//	    {Timestamp: time.Now(), Line: "Log 1", Labels: map[string]string{"app": "mcp"}},
//	    {Timestamp: time.Now(), Line: "Log 2", Labels: map[string]string{"app": "mcp"}},
//	}
//	client.PushBatch(entries)
func (c *Client) PushBatch(entries []LogEntry) error {
	if len(entries) == 0 {
		return nil
	}

	return c.sendToLoki(entries)
}

// Flush 刷新所有缓冲的日志
func (c *Client) Flush() error {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()

	return c.flushLocked()
}

// flushLocked 刷新缓冲区（内部使用，需要持有锁）
func (c *Client) flushLocked() error {
	if len(c.buffer) == 0 {
		return nil
	}

	// 复制缓冲区
	entries := make([]LogEntry, len(c.buffer))
	copy(entries, c.buffer)

	// 清空缓冲区
	c.buffer = c.buffer[:0]

	// 发送日志（在锁外执行）
	go func() {
		if err := c.sendToLoki(entries); err != nil {
			// 记录错误（但不能使用 Loki 自身记录）
			fmt.Printf("Failed to send logs to Loki: %v\n", err)
		}
	}()

	return nil
}

// batchSender 后台批量发送器
func (c *Client) batchSender() {
	defer c.wg.Done()

	ticker := time.NewTicker(c.config.BatchWait)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			c.Flush()
		case <-c.stopCh:
			return
		}
	}
}

// sendToLoki 发送日志到 Loki
func (c *Client) sendToLoki(entries []LogEntry) error {
	if len(entries) == 0 {
		return nil
	}

	// 构建 Loki 推送请求
	payload := c.buildPushPayload(entries)

	// 序列化
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	// 发送 HTTP 请求（带重试）
	url := fmt.Sprintf("%s/loki/api/v1/push", c.config.URL)

	for attempt := 0; attempt <= c.config.MaxRetries; attempt++ {
		if attempt > 0 {
			time.Sleep(c.config.RetryWait * time.Duration(attempt))
		}

		req, err := http.NewRequest("POST", url, bytes.NewReader(data))
		if err != nil {
			return fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Content-Type", "application/json")

		// 添加租户 ID
		if c.config.TenantID != "" {
			req.Header.Set("X-Scope-OrgID", c.config.TenantID)
		}

		// 添加认证
		if c.config.Username != "" {
			req.SetBasicAuth(c.config.Username, c.config.Password)
		}

		resp, err := c.httpClient.Do(req)
		if err != nil {
			if attempt == c.config.MaxRetries {
				return fmt.Errorf("failed to send request after %d retries: %w", attempt, err)
			}
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			body, _ := io.ReadAll(resp.Body)
			if attempt == c.config.MaxRetries {
				return fmt.Errorf("Loki returned error status %d: %s", resp.StatusCode, string(body))
			}
			continue
		}

		// 成功
		return nil
	}

	return fmt.Errorf("failed after %d retries", c.config.MaxRetries)
}

// buildPushPayload 构建 Loki 推送请求体
func (c *Client) buildPushPayload(entries []LogEntry) map[string]interface{} {
	// 按标签分组
	streams := make(map[string][]LogEntry)
	for _, entry := range entries {
		labelKey := c.labelsToKey(entry.Labels)
		streams[labelKey] = append(streams[labelKey], entry)
	}

	// 构建 streams
	var lokiStreams []map[string]interface{}
	for _, entries := range streams {
		// 构建值数组 [[timestamp, line], ...]
		values := make([][]interface{}, len(entries))
		for i, entry := range entries {
			values[i] = []interface{}{
				fmt.Sprintf("%d", entry.Timestamp.UnixNano()),
				entry.Line,
			}
		}

		lokiStreams = append(lokiStreams, map[string]interface{}{
			"stream": entries[0].Labels, // 使用第一个条目的标签
			"values": values,
		})
	}

	return map[string]interface{}{
		"streams": lokiStreams,
	}
}

// labelsToKey 将标签转换为唯一键
func (c *Client) labelsToKey(labels map[string]string) string {
	// 简单实现：可以优化为更高效的方式
	data, _ := json.Marshal(labels)
	return string(data)
}

// mergeLabels 合并静态标签和动态标签
func (c *Client) mergeLabels(labels map[string]string) map[string]string {
	result := make(map[string]string)

	// 先添加静态标签
	for k, v := range c.config.StaticLabels {
		result[k] = v
	}

	// 再添加动态标签（会覆盖静态标签）
	for k, v := range labels {
		result[k] = v
	}

	return result
}

// ============================================
// 日志查询 (Log Query)
// ============================================

// QueryOptions 查询选项
type QueryOptions struct {
	Start     time.Time // 开始时间
	End       time.Time // 结束时间
	Limit     int       // 最大返回数量
	Direction string    // backward 或 forward
}

// QueryResult 查询结果
type QueryResult struct {
	Labels map[string]string
	Lines  []LogLine
}

// LogLine 日志行
type LogLine struct {
	Timestamp time.Time
	Line      string
}

// Query 查询日志
//
// 参数:
//
//	query: LogQL 查询语句
//	opts: 查询选项
//
// 返回:
//
//	[]QueryResult: 查询结果
//	error: 错误信息
//
// 示例:
//
//	results, err := client.Query(
//	    `{app="mcp", level="error"}`,
//	    QueryOptions{
//	        Start: time.Now().Add(-1 * time.Hour),
//	        End:   time.Now(),
//	        Limit: 100,
//	    },
//	)
//	for _, result := range results {
//	    fmt.Printf("Labels: %v\n", result.Labels)
//	    for _, line := range result.Lines {
//	        fmt.Printf("  [%s] %s\n", line.Timestamp, line.Line)
//	    }
//	}
func (c *Client) Query(query string, opts QueryOptions) ([]QueryResult, error) {
	// 设置默认值
	if opts.Limit == 0 {
		opts.Limit = 100
	}
	if opts.Direction == "" {
		opts.Direction = "backward"
	}
	if opts.End.IsZero() {
		opts.End = time.Now()
	}
	if opts.Start.IsZero() {
		opts.Start = opts.End.Add(-1 * time.Hour)
	}

	// 构建查询 URL
	url := fmt.Sprintf("%s/loki/api/v1/query_range", c.config.URL)
	url += fmt.Sprintf("?query=%s", query)
	url += fmt.Sprintf("&start=%d", opts.Start.UnixNano())
	url += fmt.Sprintf("&end=%d", opts.End.UnixNano())
	url += fmt.Sprintf("&limit=%d", opts.Limit)
	url += fmt.Sprintf("&direction=%s", opts.Direction)

	// 创建请求
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// 添加认证
	if c.config.Username != "" {
		req.SetBasicAuth(c.config.Username, c.config.Password)
	}
	if c.config.TenantID != "" {
		req.Header.Set("X-Scope-OrgID", c.config.TenantID)
	}

	// 发送请求
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Loki returned error status %d: %s", resp.StatusCode, string(body))
	}

	// 解析响应
	var response map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	// 提取结果
	return c.parseQueryResponse(response)
}

// QueryLabels 查询可用的标签
//
// 示例:
//
//	labels, err := client.QueryLabels(time.Now().Add(-24*time.Hour), time.Now())
//	for _, label := range labels {
//	    fmt.Println("Label:", label)
//	}
func (c *Client) QueryLabels(start, end time.Time) ([]string, error) {
	url := fmt.Sprintf("%s/loki/api/v1/labels", c.config.URL)
	url += fmt.Sprintf("?start=%d&end=%d", start.UnixNano(), end.UnixNano())

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	if c.config.Username != "" {
		req.SetBasicAuth(c.config.Username, c.config.Password)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	var response map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	// 提取标签
	if data, ok := response["data"].([]interface{}); ok {
		labels := make([]string, len(data))
		for i, label := range data {
			if labelStr, ok := label.(string); ok {
				labels[i] = labelStr
			}
		}
		return labels, nil
	}

	return nil, fmt.Errorf("invalid response format")
}

// QueryLabelValues 查询标签的可能值
//
// 示例:
//
//	values, err := client.QueryLabelValues("app", time.Now().Add(-24*time.Hour), time.Now())
//	// 返回: ["mcp", "model", "agent"]
func (c *Client) QueryLabelValues(label string, start, end time.Time) ([]string, error) {
	url := fmt.Sprintf("%s/loki/api/v1/label/%s/values", c.config.URL, label)
	url += fmt.Sprintf("?start=%d&end=%d", start.UnixNano(), end.UnixNano())

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	if c.config.Username != "" {
		req.SetBasicAuth(c.config.Username, c.config.Password)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	var response map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if data, ok := response["data"].([]interface{}); ok {
		values := make([]string, len(data))
		for i, val := range data {
			if valStr, ok := val.(string); ok {
				values[i] = valStr
			}
		}
		return values, nil
	}

	return nil, fmt.Errorf("invalid response format")
}

// parseQueryResponse 解析查询响应
func (c *Client) parseQueryResponse(response map[string]interface{}) ([]QueryResult, error) {
	dataField, ok := response["data"].(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid response format: missing data field")
	}

	resultField, ok := dataField["result"].([]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid response format: missing result field")
	}

	var results []QueryResult
	for _, item := range resultField {
		itemMap, ok := item.(map[string]interface{})
		if !ok {
			continue
		}

		// 提取标签
		streamLabels, _ := itemMap["stream"].(map[string]interface{})
		labels := make(map[string]string)
		for k, v := range streamLabels {
			if vStr, ok := v.(string); ok {
				labels[k] = vStr
			}
		}

		// 提取日志行
		valuesField, _ := itemMap["values"].([]interface{})
		var lines []LogLine
		for _, value := range valuesField {
			valueArray, _ := value.([]interface{})
			if len(valueArray) >= 2 {
				timestampStr, _ := valueArray[0].(string)
				lineStr, _ := valueArray[1].(string)

				// 解析时间戳
				var timestamp time.Time
				var tsNano int64
				fmt.Sscanf(timestampStr, "%d", &tsNano)
				timestamp = time.Unix(0, tsNano)

				lines = append(lines, LogLine{
					Timestamp: timestamp,
					Line:      lineStr,
				})
			}
		}

		results = append(results, QueryResult{
			Labels: labels,
			Lines:  lines,
		})
	}

	return results, nil
}

// ============================================
// 工具方法 (Utility Methods)
// ============================================

// HealthCheck 健康检查
//
// 示例:
//
//	err := client.HealthCheck(ctx)
//	if err != nil {
//	    log.Printf("Loki health check failed: %v", err)
//	}
func (c *Client) HealthCheck(ctx context.Context) error {
	url := fmt.Sprintf("%s/ready", c.config.URL)

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed with status: %d", resp.StatusCode)
	}

	return nil
}

// GetConfig 获取客户端配置
func (c *Client) GetConfig() *Config {
	return c.config
}

// GetStats 获取客户端统计信息
func (c *Client) GetStats() map[string]interface{} {
	c.bufferMu.Lock()
	defer c.bufferMu.Unlock()

	return map[string]interface{}{
		"buffer_size":   len(c.buffer),
		"batch_size":    c.config.BatchSize,
		"static_labels": c.config.StaticLabels,
	}
}
