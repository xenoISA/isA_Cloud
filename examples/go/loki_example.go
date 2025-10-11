// Loki SDK 使用示例
//
// 这个示例展示了如何使用 Loki SDK 进行日志推送和查询
//
// 运行示例:
//
//	go run examples/go/loki_client_example.go
package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

func main() {
	fmt.Println("=== Loki SDK 使用示例 ===\n")

	// 1. 创建 Loki 客户端
	cfg := &loki.Config{
		URL:       "http://localhost:3100",
		TenantID:  "demo-tenant",
		BatchSize: 50,
		BatchWait: 2 * time.Second,
		Timeout:   15 * time.Second,
		StaticLabels: map[string]string{
			"environment": "development",
			"app_version": "1.0.0",
		},
	}

	client, err := loki.NewClient(cfg)
	if err != nil {
		log.Fatalf("Failed to create Loki client: %v", err)
	}
	defer client.Close()

	fmt.Println("✓ Loki 客户端创建成功")

	// 2. 健康检查
	ctx := context.Background()
	err = client.HealthCheck(ctx)
	if err != nil {
		log.Printf("⚠ Loki 健康检查失败: %v (继续运行示例...)", err)
	} else {
		fmt.Println("✓ Loki 健康检查通过")
	}

	// 3. 推送单条日志
	fmt.Println("\n--- 推送单条日志 ---")
	err = client.PushLog("mcp-service", loki.LogLevelInfo, "Application started successfully", map[string]string{
		"service": "auth",
		"version": "1.0.0",
	})
	if err != nil {
		log.Printf("Failed to push log: %v", err)
	} else {
		fmt.Println("✓ 单条日志推送成功")
	}

	// 4. 推送不同级别的日志
	fmt.Println("\n--- 推送不同级别的日志 ---")
	logLevels := []struct {
		level   loki.LogLevel
		message string
	}{
		{loki.LogLevelDebug, "Debugging database connection"},
		{loki.LogLevelInfo, "User logged in successfully"},
		{loki.LogLevelWarn, "High memory usage detected"},
		{loki.LogLevelError, "Failed to connect to database"},
		{loki.LogLevelFatal, "Critical system failure"},
	}

	for _, l := range logLevels {
		err := client.PushLog("mcp-service", l.level, l.message, map[string]string{
			"component": "example",
		})
		if err != nil {
			log.Printf("Failed to push %s log: %v", l.level, err)
		} else {
			fmt.Printf("✓ %s 日志推送成功: %s\n", l.level, l.message)
		}
	}

	// 5. 批量推送日志
	fmt.Println("\n--- 批量推送日志 ---")
	entries := []loki.LogEntry{
		{
			Timestamp: time.Now(),
			Line:      "Request received from client",
			Labels: map[string]string{
				"app":        "mcp-service",
				"level":      "info",
				"request_id": "req-001",
			},
		},
		{
			Timestamp: time.Now(),
			Line:      "Processing authentication",
			Labels: map[string]string{
				"app":        "mcp-service",
				"level":      "debug",
				"request_id": "req-001",
			},
		},
		{
			Timestamp: time.Now(),
			Line:      "Response sent to client",
			Labels: map[string]string{
				"app":        "mcp-service",
				"level":      "info",
				"request_id": "req-001",
			},
		},
	}

	err = client.PushBatch(entries)
	if err != nil {
		log.Printf("Failed to push batch: %v", err)
	} else {
		fmt.Printf("✓ 批量推送 %d 条日志成功\n", len(entries))
	}

	// 6. 手动刷新缓冲区
	fmt.Println("\n--- 刷新缓冲区 ---")
	err = client.Flush()
	if err != nil {
		log.Printf("Failed to flush: %v", err)
	} else {
		fmt.Println("✓ 缓冲区刷新成功")
	}

	// 等待一下，让日志被写入 Loki
	time.Sleep(3 * time.Second)

	// 7. 查询日志
	fmt.Println("\n--- 查询日志 ---")
	results, err := client.Query(
		`{app="mcp-service"}`,
		loki.QueryOptions{
			Start:     time.Now().Add(-5 * time.Minute),
			End:       time.Now(),
			Limit:     10,
			Direction: "backward",
		},
	)
	if err != nil {
		log.Printf("Failed to query logs: %v", err)
	} else {
		fmt.Printf("✓ 查询到 %d 个流的日志:\n", len(results))
		for i, result := range results {
			fmt.Printf("\n流 %d - 标签: %v\n", i+1, result.Labels)
			for j, line := range result.Lines {
				fmt.Printf("  [%s] %s\n", line.Timestamp.Format("15:04:05"), line.Line)
				if j >= 2 { // 只显示前3条
					fmt.Printf("  ... (%d 条日志)\n", len(result.Lines)-j-1)
					break
				}
			}
		}
	}

	// 8. 查询错误日志
	fmt.Println("\n--- 查询错误日志 ---")
	errorResults, err := client.Query(
		`{app="mcp-service", level="error"}`,
		loki.QueryOptions{
			Start:     time.Now().Add(-5 * time.Minute),
			End:       time.Now(),
			Limit:     5,
			Direction: "backward",
		},
	)
	if err != nil {
		log.Printf("Failed to query error logs: %v", err)
	} else {
		fmt.Printf("✓ 查询到 %d 个错误日志流\n", len(errorResults))
		for _, result := range errorResults {
			for _, line := range result.Lines {
				fmt.Printf("  ERROR [%s]: %s\n", line.Timestamp.Format("15:04:05"), line.Line)
			}
		}
	}

	// 9. 查询可用的标签
	fmt.Println("\n--- 查询可用标签 ---")
	labels, err := client.QueryLabels(
		time.Now().Add(-1*time.Hour),
		time.Now(),
	)
	if err != nil {
		log.Printf("Failed to query labels: %v", err)
	} else {
		fmt.Printf("✓ 可用标签 (%d):\n", len(labels))
		for _, label := range labels {
			fmt.Printf("  - %s\n", label)
			if len(labels) > 5 {
				fmt.Printf("  ... (共 %d 个标签)\n", len(labels))
				break
			}
		}
	}

	// 10. 查询标签值
	fmt.Println("\n--- 查询 app 标签的值 ---")
	values, err := client.QueryLabelValues(
		"app",
		time.Now().Add(-1*time.Hour),
		time.Now(),
	)
	if err != nil {
		log.Printf("Failed to query label values: %v", err)
	} else {
		fmt.Printf("✓ app 标签的值: %v\n", values)
	}

	// 11. 获取客户端统计信息
	fmt.Println("\n--- 客户端统计信息 ---")
	stats := client.GetStats()
	fmt.Printf("缓冲区大小: %v\n", stats["buffer_size"])
	fmt.Printf("批处理大小: %v\n", stats["batch_size"])
	fmt.Printf("静态标签: %v\n", stats["static_labels"])

	// 12. 获取配置信息
	fmt.Println("\n--- 客户端配置 ---")
	config := client.GetConfig()
	fmt.Printf("Loki URL: %s\n", config.URL)
	fmt.Printf("租户 ID: %s\n", config.TenantID)
	fmt.Printf("批处理大小: %d\n", config.BatchSize)
	fmt.Printf("批处理等待: %v\n", config.BatchWait)

	fmt.Println("\n=== 示例完成 ===")
}
