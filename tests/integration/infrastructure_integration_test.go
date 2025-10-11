// 测试 MinIO + DuckDB 集成
// 文件名: examples/test_integration.go
//
// 使用方法:
//   go run examples/test_integration.go
//
// 前提条件:
//   - MinIO 运行在 localhost:9000
//   - 访问密钥: minioadmin / minioadmin

package main

import (
	"bytes"
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/analytics/duckdb"
	"github.com/isa-cloud/isa_cloud/pkg/storage/minio"
)

func main() {
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("MinIO + DuckDB 集成测试")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println()

	ctx := context.Background()

	// 测试 1: MinIO 连接和基本操作
	fmt.Println("🔧 测试 1: MinIO 连接和基本操作")
	fmt.Println(strings.Repeat("-", 60))

	minioClient, err := testMinIO(ctx)
	if err != nil {
		log.Fatalf("❌ MinIO 测试失败: %v", err)
	}
	defer minioClient.Close()

	fmt.Println("✅ MinIO 测试通过！")
	fmt.Println()

	// 测试 2: DuckDB 基本操作
	fmt.Println("🔧 测试 2: DuckDB 基本操作")
	fmt.Println(strings.Repeat("-", 60))

	duckdbClient, err := testDuckDB(ctx)
	if err != nil {
		log.Fatalf("❌ DuckDB 测试失败: %v", err)
	}
	defer duckdbClient.Close()

	fmt.Println("✅ DuckDB 测试通过！")
	fmt.Println()

	// 测试 3: MinIO + DuckDB 集成
	fmt.Println("🔧 测试 3: MinIO + DuckDB 集成")
	fmt.Println(strings.Repeat("-", 60))

	err = testIntegration(ctx, minioClient, duckdbClient)
	if err != nil {
		log.Fatalf("❌ 集成测试失败: %v", err)
	}

	fmt.Println("✅ 集成测试通过！")
	fmt.Println()

	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("🎉 所有测试通过！MinIO + DuckDB 工作正常")
	fmt.Println(strings.Repeat("=", 60))
}

// testMinIO 测试 MinIO 连接和基本操作
func testMinIO(ctx context.Context) (*minio.Client, error) {
	// 1. 创建客户端
	cfg := &minio.Config{
		Endpoint:  "localhost:9000",
		AccessKey: "minioadmin",
		SecretKey: "minioadmin",
		UseSSL:    false,
		Region:    "us-east-1",
	}

	client, err := minio.NewClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("创建 MinIO 客户端失败: %w", err)
	}
	fmt.Println("  ✓ MinIO 客户端创建成功")

	// 2. 健康检查
	err = client.HealthCheck(ctx)
	if err != nil {
		return nil, fmt.Errorf("MinIO 健康检查失败: %w", err)
	}
	fmt.Println("  ✓ MinIO 健康检查通过")

	// 3. 列出所有桶
	buckets, err := client.ListBuckets(ctx)
	if err != nil {
		return nil, fmt.Errorf("列出桶失败: %w", err)
	}
	fmt.Printf("  ✓ 当前桶数量: %d\n", len(buckets))
	for _, bucket := range buckets {
		fmt.Printf("    - %s (创建于: %s)\n", bucket.Name, bucket.CreationDate.Format("2006-01-02"))
	}

	// 4. 创建测试桶
	testBucket := "test-integration-bucket"
	exists, err := client.BucketExists(ctx, testBucket)
	if err != nil {
		return nil, fmt.Errorf("检查桶存在性失败: %w", err)
	}

	if !exists {
		err = client.MakeBucket(ctx, testBucket, "us-east-1")
		if err != nil {
			return nil, fmt.Errorf("创建桶失败: %w", err)
		}
		fmt.Printf("  ✓ 创建测试桶: %s\n", testBucket)
	} else {
		fmt.Printf("  ✓ 测试桶已存在: %s\n", testBucket)
	}

	// 5. 上传测试文件
	testData := []byte("Hello, MinIO! This is a test file from integration test.")
	reader := bytes.NewReader(testData)

	objInfo, err := client.PutObject(ctx, testBucket, "test.txt",
		reader, int64(len(testData)), minio.PutOptions{
			ContentType: "text/plain",
			Metadata: map[string]string{
				"test":      "integration",
				"timestamp": time.Now().Format(time.RFC3339),
			},
		})
	if err != nil {
		return nil, fmt.Errorf("上传文件失败: %w", err)
	}
	fmt.Printf("  ✓ 上传测试文件: %s (%d bytes)\n", objInfo.Key, objInfo.Size)

	// 6. 下载并验证
	object, err := client.GetObject(ctx, testBucket, "test.txt", minio.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("下载文件失败: %w", err)
	}
	defer object.Close()

	downloadedData := make([]byte, len(testData))
	_, err = object.Read(downloadedData)
	if err != nil && err.Error() != "EOF" {
		return nil, fmt.Errorf("读取文件失败: %w", err)
	}

	if string(downloadedData) == string(testData) {
		fmt.Println("  ✓ 文件下载并验证成功")
	} else {
		return nil, fmt.Errorf("下载的文件内容不匹配")
	}

	return client, nil
}

// testDuckDB 测试 DuckDB 基本操作
func testDuckDB(ctx context.Context) (*duckdb.Client, error) {
	// 1. 创建客户端（内存数据库）
	cfg := &duckdb.Config{
		DatabasePath: ":memory:",
		MemoryLimit:  "1GB",
		Threads:      4,
		Extensions:   []string{"httpfs", "parquet"},
	}

	client, err := duckdb.NewClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("创建 DuckDB 客户端失败: %w", err)
	}
	fmt.Println("  ✓ DuckDB 客户端创建成功")

	// 2. 检查版本
	version, err := client.GetVersion(ctx)
	if err != nil {
		return nil, fmt.Errorf("获取 DuckDB 版本失败: %w", err)
	}
	fmt.Printf("  ✓ DuckDB 版本: %s\n", version)

	// 3. 创建测试表
	_, err = client.Exec(ctx, `
		CREATE TABLE test_users (
			id INTEGER PRIMARY KEY,
			name VARCHAR,
			age INTEGER,
			email VARCHAR
		)
	`)
	if err != nil {
		return nil, fmt.Errorf("创建表失败: %w", err)
	}
	fmt.Println("  ✓ 创建测试表成功")

	// 4. 插入测试数据
	users := []struct {
		ID    int
		Name  string
		Age   int
		Email string
	}{
		{1, "Alice", 30, "alice@example.com"},
		{2, "Bob", 25, "bob@example.com"},
		{3, "Charlie", 35, "charlie@example.com"},
		{4, "Diana", 28, "diana@example.com"},
	}

	for _, user := range users {
		_, err = client.Exec(ctx,
			"INSERT INTO test_users (id, name, age, email) VALUES (?, ?, ?, ?)",
			user.ID, user.Name, user.Age, user.Email)
		if err != nil {
			return nil, fmt.Errorf("插入数据失败: %w", err)
		}
	}
	fmt.Printf("  ✓ 插入 %d 条测试数据\n", len(users))

	// 5. 查询测试
	result, err := client.QueryToMap(ctx, "SELECT * FROM test_users WHERE age > 26 ORDER BY age")
	if err != nil {
		return nil, fmt.Errorf("查询数据失败: %w", err)
	}
	fmt.Printf("  ✓ 查询成功，返回 %d 条记录\n", len(result))
	for _, row := range result {
		fmt.Printf("    - %v: %v (年龄: %v)\n", row["id"], row["name"], row["age"])
	}

	// 6. 聚合查询
	var count int
	var avgAge float64
	err = client.QueryRow(ctx,
		"SELECT COUNT(*) as count, AVG(age) as avg_age FROM test_users").Scan(&count, &avgAge)
	if err != nil {
		return nil, fmt.Errorf("聚合查询失败: %w", err)
	}
	fmt.Printf("  ✓ 统计: 总用户数=%d, 平均年龄=%.1f\n", count, avgAge)

	return client, nil
}

// testIntegration 测试 MinIO + DuckDB 集成
func testIntegration(ctx context.Context, minioClient *minio.Client, duckdbClient *duckdb.Client) error {
	testBucket := "test-integration-bucket"

	// 1. 准备 CSV 数据
	csvData := []byte(`id,product,quantity,price,date
1,Laptop,10,999.99,2024-01-15
2,Mouse,100,29.99,2024-01-15
3,Keyboard,50,79.99,2024-01-16
4,Monitor,25,299.99,2024-01-16
5,Headphones,75,149.99,2024-01-17`)

	// 2. 上传 CSV 到 MinIO
	reader := bytes.NewReader(csvData)
	_, err := minioClient.PutObject(ctx, testBucket, "sales.csv",
		reader, int64(len(csvData)), minio.PutOptions{
			ContentType: "text/csv",
		})
	if err != nil {
		return fmt.Errorf("上传 CSV 失败: %w", err)
	}
	fmt.Println("  ✓ 上传 sales.csv 到 MinIO")

	// 3. 配置 DuckDB 访问 MinIO (S3 兼容模式)
	_, err = duckdbClient.Exec(ctx, `
		SET s3_endpoint='localhost:9000';
		SET s3_access_key_id='minioadmin';
		SET s3_secret_access_key='minioadmin';
		SET s3_use_ssl=false;
		SET s3_url_style='path';
	`)
	if err != nil {
		return fmt.Errorf("配置 S3 访问失败: %w", err)
	}
	fmt.Println("  ✓ 配置 DuckDB 访问 MinIO")

	// 4. 直接查询 MinIO 中的 CSV 文件
	fmt.Println("  ✓ 直接查询 MinIO 中的 CSV 文件...")

	query := fmt.Sprintf(`
		SELECT 
			product,
			SUM(quantity) as total_quantity,
			SUM(quantity * price) as total_revenue
		FROM read_csv_auto('s3://%s/sales.csv')
		GROUP BY product
		ORDER BY total_revenue DESC
	`, testBucket)

	result, err := duckdbClient.QueryToMap(ctx, query)
	if err != nil {
		return fmt.Errorf("查询 CSV 失败: %w", err)
	}

	fmt.Println("  ✓ 查询结果 (按收入排序):")
	for _, row := range result {
		fmt.Printf("    - 产品: %v, 数量: %v, 收入: $%.2f\n",
			row["product"], row["total_quantity"], row["total_revenue"])
	}

	// 5. 创建表并导入数据
	_, err = duckdbClient.Exec(ctx, fmt.Sprintf(`
		CREATE TABLE sales AS
		SELECT * FROM read_csv_auto('s3://%s/sales.csv')
	`, testBucket))
	if err != nil {
		return fmt.Errorf("创建表失败: %w", err)
	}
	fmt.Println("  ✓ 从 CSV 创建表成功")

	// 6. 执行分析查询
	analysisQuery := `
		SELECT 
			date,
			COUNT(*) as order_count,
			SUM(quantity * price) as daily_revenue
		FROM sales
		GROUP BY date
		ORDER BY date
	`

	analysisResult, err := duckdbClient.QueryToMap(ctx, analysisQuery)
	if err != nil {
		return fmt.Errorf("分析查询失败: %w", err)
	}

	fmt.Println("  ✓ 每日销售分析:")
	for _, row := range analysisResult {
		fmt.Printf("    - 日期: %v, 订单数: %v, 收入: $%.2f\n",
			row["date"], row["order_count"], row["daily_revenue"])
	}

	// 7. 导出结果到临时文件 (Parquet 格式)
	tmpDir := os.TempDir()
	parquetFile := fmt.Sprintf("%s/sales_report.parquet", tmpDir)

	exportQuery := fmt.Sprintf(`
		COPY (SELECT * FROM sales ORDER BY date)
		TO '%s' (FORMAT PARQUET)
	`, parquetFile)

	_, err = duckdbClient.Exec(ctx, exportQuery)
	if err != nil {
		return fmt.Errorf("导出 Parquet 失败: %w", err)
	}
	fmt.Printf("  ✓ 导出到 Parquet: %s\n", parquetFile)

	// 8. 读取 Parquet 并上传到 MinIO
	parquetData, err := os.ReadFile(parquetFile)
	if err != nil {
		return fmt.Errorf("读取 Parquet 文件失败: %w", err)
	}

	parquetReader := bytes.NewReader(parquetData)
	_, err = minioClient.PutObject(ctx, testBucket, "reports/sales_report.parquet",
		parquetReader, int64(len(parquetData)), minio.PutOptions{
			ContentType: "application/octet-stream",
		})
	if err != nil {
		return fmt.Errorf("上传 Parquet 到 MinIO 失败: %w", err)
	}
	fmt.Println("  ✓ 上传 Parquet 到 MinIO: reports/sales_report.parquet")

	// 9. 直接查询 MinIO 中的 Parquet 文件
	parquetQuery := fmt.Sprintf(`
		SELECT product, AVG(price) as avg_price
		FROM 's3://%s/reports/sales_report.parquet'
		GROUP BY product
		ORDER BY avg_price DESC
	`, testBucket)

	parquetResult, err := duckdbClient.QueryToMap(ctx, parquetQuery)
	if err != nil {
		return fmt.Errorf("查询 Parquet 失败: %w", err)
	}

	fmt.Println("  ✓ 查询 Parquet 文件结果 (平均价格):")
	for _, row := range parquetResult {
		fmt.Printf("    - 产品: %v, 平均价格: $%.2f\n",
			row["product"], row["avg_price"])
	}

	// 10. 清理临时文件
	os.Remove(parquetFile)
	fmt.Println("  ✓ 清理临时文件")

	return nil
}
