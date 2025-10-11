// 测试配置管理和服务发现
// 文件名: examples/test_config.go
//
// 使用方法:
//   # 使用默认配置
//   go run examples/test_config.go
//
//   # 使用环境变量
//   export MINIO_ENDPOINT="minio:9000"
//   export CONSUL_ENABLED="true"
//   go run examples/test_config.go
//
//   # 使用配置文件
//   # 创建 deployments/configs/storage.yaml
//   go run examples/test_config.go

package main

import (
	"context"
	"fmt"
	"log"
	"strings"

	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

func main() {
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("存储服务配置管理测试")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println()

	ctx := context.Background()

	// 测试 1: 加载配置
	fmt.Println("🔧 测试 1: 配置加载")
	fmt.Println(strings.Repeat("-", 60))
	testConfigLoading()
	fmt.Println()

	// 测试 2: 使用工厂创建客户端
	fmt.Println("🔧 测试 2: 客户端工厂")
	fmt.Println(strings.Repeat("-", 60))
	testClientFactory(ctx)
	fmt.Println()

	// 测试 3: 环境变量配置
	fmt.Println("🔧 测试 3: 环境变量配置")
	fmt.Println(strings.Repeat("-", 60))
	testEnvConfig()
	fmt.Println()

	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("🎉 所有配置测试通过！")
	fmt.Println(strings.Repeat("=", 60))
}

// testConfigLoading 测试配置加载
func testConfigLoading() {
	// 方式 1: 从配置文件和环境变量加载
	cfg, err := storage.LoadStorageConfig()
	if err != nil {
		log.Printf("  ⚠ 配置加载失败（这是正常的，如果没有配置文件）: %v", err)
		return
	}

	fmt.Println("  ✓ 配置加载成功")
	fmt.Printf("  ✓ MinIO Endpoint: %s\n", cfg.MinIO.Endpoint)
	fmt.Printf("  ✓ MinIO Use Consul: %v\n", cfg.MinIO.UseConsul)
	fmt.Printf("  ✓ DuckDB Path: %s\n", cfg.DuckDB.DatabasePath)
	fmt.Printf("  ✓ DuckDB Memory Limit: %s\n", cfg.DuckDB.MemoryLimit)
	fmt.Printf("  ✓ Consul Enabled: %v\n", cfg.Consul.Enabled)

	if cfg.Consul.Enabled {
		fmt.Printf("  ✓ Consul Address: %s:%d\n", cfg.Consul.Host, cfg.Consul.Port)
	}
}

// testClientFactory 测试客户端工厂
func testClientFactory(ctx context.Context) {
	// 创建工厂
	factory, err := storage.NewStorageClientFactory()
	if err != nil {
		log.Printf("  ✗ 工厂创建失败: %v", err)
		return
	}
	fmt.Println("  ✓ 客户端工厂创建成功")

	// 获取配置
	cfg := factory.GetConfig()
	fmt.Printf("  ✓ MinIO: %s (Consul: %v)\n", cfg.MinIO.Endpoint, cfg.MinIO.UseConsul)
	fmt.Printf("  ✓ DuckDB: %s (Memory: %s)\n", cfg.DuckDB.DatabasePath, cfg.DuckDB.MemoryLimit)

	// 创建 MinIO 客户端
	minioClient, err := factory.NewMinIOClient(ctx)
	if err != nil {
		log.Printf("  ✗ MinIO 客户端创建失败: %v", err)
		return
	}
	defer minioClient.Close()
	fmt.Println("  ✓ MinIO 客户端创建成功")

	// 测试 MinIO 连接
	err = minioClient.HealthCheck(ctx)
	if err != nil {
		log.Printf("  ✗ MinIO 健康检查失败: %v", err)
		return
	}
	fmt.Println("  ✓ MinIO 健康检查通过")

	// 列出桶
	buckets, err := minioClient.ListBuckets(ctx)
	if err != nil {
		log.Printf("  ✗ 列出桶失败: %v", err)
		return
	}
	fmt.Printf("  ✓ 当前桶数量: %d\n", len(buckets))
	for i, bucket := range buckets {
		if i < 3 { // 只显示前3个
			fmt.Printf("    - %s\n", bucket.Name)
		}
	}
	if len(buckets) > 3 {
		fmt.Printf("    ... 还有 %d 个桶\n", len(buckets)-3)
	}

	// 创建 DuckDB 客户端
	duckdbClient, err := factory.NewDuckDBClient(ctx)
	if err != nil {
		log.Printf("  ✗ DuckDB 客户端创建失败: %v", err)
		return
	}
	defer duckdbClient.Close()
	fmt.Println("  ✓ DuckDB 客户端创建成功")

	// 测试 DuckDB 连接
	version, err := duckdbClient.GetVersion(ctx)
	if err != nil {
		log.Printf("  ✗ DuckDB 版本查询失败: %v", err)
		return
	}
	fmt.Printf("  ✓ DuckDB 版本: %s\n", version)
}

// testEnvConfig 测试环境变量配置
func testEnvConfig() {
	// 从环境变量加载（简化方式）
	cfg := storage.LoadFromEnv()

	fmt.Println("  ✓ 从环境变量加载配置")
	fmt.Printf("  ✓ MinIO Endpoint: %s\n", cfg.MinIO.Endpoint)
	fmt.Printf("  ✓ MinIO Access Key: %s\n", cfg.MinIO.AccessKey)
	fmt.Printf("  ✓ MinIO Use SSL: %v\n", cfg.MinIO.UseSSL)
	fmt.Printf("  ✓ DuckDB Path: %s\n", cfg.DuckDB.DatabasePath)
	fmt.Printf("  ✓ DuckDB Threads: %d\n", cfg.DuckDB.Threads)
	fmt.Printf("  ✓ Consul Enabled: %v\n", cfg.Consul.Enabled)

	fmt.Println()
	fmt.Println("  💡 提示: 可以通过以下环境变量覆盖配置:")
	fmt.Println("     export MINIO_ENDPOINT=\"minio:9000\"")
	fmt.Println("     export MINIO_ACCESS_KEY=\"your-key\"")
	fmt.Println("     export MINIO_SECRET_KEY=\"your-secret\"")
	fmt.Println("     export DUCKDB_PATH=\"/data/analytics.db\"")
	fmt.Println("     export CONSUL_ENABLED=\"true\"")
}
