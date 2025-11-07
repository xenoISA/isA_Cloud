// Package server tests
// 文件名: cmd/postgres-service/server/server_test.go
package server

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/types/known/structpb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/postgres"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/postgres"
)

// 测试辅助函数: 创建测试数据库连接
func setupTestDB(t *testing.T) *postgres.Client {
	cfg := &postgres.Config{
		Host:     "localhost",
		Port:     5432,
		Database: "isa_platform",
		User:     "postgres",
		Password: "staging_postgres_2024",
		SSLMode:  "disable",
	}

	ctx := context.Background()
	client, err := postgres.NewClient(ctx, cfg)
	require.NoError(t, err, "Failed to connect to test database")

	return client
}

// 测试辅助函数: 创建测试表
func createTestTable(t *testing.T, client *postgres.Client) {
	ctx := context.Background()

	// 删除测试表（如果存在）
	_, _ = client.Execute(ctx, "DROP TABLE IF EXISTS test_users")

	// 创建测试表
	createSQL := `
		CREATE TABLE test_users (
			id SERIAL PRIMARY KEY,
			username VARCHAR(50) UNIQUE NOT NULL,
			email VARCHAR(100) UNIQUE NOT NULL,
			age INTEGER,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`
	_, err := client.Execute(ctx, createSQL)
	require.NoError(t, err, "Failed to create test table")

	// 插入测试数据
	insertSQL := "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)"
	_, err = client.Execute(ctx, insertSQL, "john_doe", "john@example.com", 30)
	require.NoError(t, err, "Failed to insert test data")

	_, err = client.Execute(ctx, insertSQL, "jane_smith", "jane@example.com", 28)
	require.NoError(t, err, "Failed to insert test data")
}

// 测试辅助函数: 清理测试表
func cleanupTestTable(t *testing.T, client *postgres.Client) {
	ctx := context.Background()
	_, _ = client.Execute(ctx, "DROP TABLE IF EXISTS test_users")
}

// ============================================
// QueryRow 性能优化测试
// ============================================

// TestQueryRow_Found 测试查询存在的行
func TestQueryRow_Found(t *testing.T) {
	client := setupTestDB(t)
	defer client.Close()

	createTestTable(t, client)
	defer cleanupTestTable(t, client)

	server := NewPostgresServer(client, "isa_platform")

	// 准备请求
	req := &pb.QueryRowRequest{
		Sql: "SELECT id, username, email, age FROM test_users WHERE username = $1",
		Params: []*structpb.Value{
			structpb.NewStringValue("john_doe"),
		},
		Schema: "public",
	}

	// 执行查询
	ctx := context.Background()
	resp, err := server.QueryRow(ctx, req)

	// 验证结果
	require.NoError(t, err, "QueryRow should not return error")
	assert.True(t, resp.Metadata.Success, "Response should be successful")
	assert.True(t, resp.Found, "Row should be found")
	assert.NotNil(t, resp.Row, "Row data should not be nil")

	// 验证数据正确性
	rowMap := resp.Row.AsMap()
	assert.Equal(t, "john_doe", rowMap["username"], "Username should match")
	assert.Equal(t, "john@example.com", rowMap["email"], "Email should match")
	assert.Equal(t, float64(30), rowMap["age"], "Age should match")

	t.Log("✅ TestQueryRow_Found: PASSED")
	t.Logf("   Retrieved user: %s (%s)", rowMap["username"], rowMap["email"])
}

// TestQueryRow_NotFound 测试查询不存在的行
func TestQueryRow_NotFound(t *testing.T) {
	client := setupTestDB(t)
	defer client.Close()

	createTestTable(t, client)
	defer cleanupTestTable(t, client)

	server := NewPostgresServer(client, "isa_platform")

	// 准备请求（查询不存在的用户）
	req := &pb.QueryRowRequest{
		Sql: "SELECT id, username, email FROM test_users WHERE username = $1",
		Params: []*structpb.Value{
			structpb.NewStringValue("nonexistent_user"),
		},
		Schema: "public",
	}

	// 执行查询
	ctx := context.Background()
	resp, err := server.QueryRow(ctx, req)

	// 验证结果
	require.NoError(t, err, "QueryRow should not return error")
	assert.True(t, resp.Metadata.Success, "Response should be successful")
	assert.False(t, resp.Found, "Row should not be found")
	assert.Nil(t, resp.Row, "Row data should be nil")

	t.Log("✅ TestQueryRow_NotFound: PASSED")
	t.Log("   Correctly returned Found=false for non-existent row")
}

// TestQueryRow_AllTypes 测试各种数据类型
func TestQueryRow_AllTypes(t *testing.T) {
	client := setupTestDB(t)
	defer client.Close()

	ctx := context.Background()

	// 创建包含多种数据类型的测试表
	_, _ = client.Execute(ctx, "DROP TABLE IF EXISTS test_types")
	createSQL := `
		CREATE TABLE test_types (
			id SERIAL PRIMARY KEY,
			text_col TEXT,
			int_col INTEGER,
			bool_col BOOLEAN,
			timestamp_col TIMESTAMP,
			json_col JSONB
		)
	`
	_, err := client.Execute(ctx, createSQL)
	require.NoError(t, err)
	defer cleanupTestTable(t, client)
	defer client.Execute(ctx, "DROP TABLE IF EXISTS test_types")

	// 插入测试数据
	insertSQL := `
		INSERT INTO test_types (text_col, int_col, bool_col, timestamp_col, json_col)
		VALUES ($1, $2, $3, $4, $5)
	`
	_, err = client.Execute(ctx, insertSQL, "test", 42, true, time.Now(), `{"key": "value"}`)
	require.NoError(t, err)

	server := NewPostgresServer(client, "isa_platform")

	// 查询数据
	req := &pb.QueryRowRequest{
		Sql:    "SELECT text_col, int_col, bool_col FROM test_types WHERE id = 1",
		Schema: "public",
	}

	resp, err := server.QueryRow(ctx, req)

	// 验证结果
	require.NoError(t, err)
	assert.True(t, resp.Found)
	rowMap := resp.Row.AsMap()
	assert.Equal(t, "test", rowMap["text_col"])
	assert.Equal(t, float64(42), rowMap["int_col"])
	assert.Equal(t, true, rowMap["bool_col"])

	t.Log("✅ TestQueryRow_AllTypes: PASSED")
	t.Logf("   Successfully handled multiple data types")
}

// ============================================
// 性能基准测试
// ============================================

// BenchmarkQueryRow_Old 模拟旧实现的性能（双查询）
func BenchmarkQueryRow_Old(b *testing.B) {
	client := setupTestDBBench(b)
	defer client.Close()

	ctx := context.Background()
	pool := client.GetPool()

	sql := "SELECT id, username, email, age FROM test_users WHERE username = $1"
	params := []interface{}{"john_doe"}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		// 模拟旧实现: 执行两次查询
		// 第一次: 获取列描述
		rows1, _ := pool.Query(ctx, sql+" LIMIT 0", params...)
		_ = rows1.FieldDescriptions()
		rows1.Close()

		// 第二次: 获取实际数据
		row := pool.QueryRow(ctx, sql, params...)
		var id int
		var username, email string
		var age int
		_ = row.Scan(&id, &username, &email, &age)
	}
}

// BenchmarkQueryRow_New 新实现的性能（单查询）
func BenchmarkQueryRow_New(b *testing.B) {
	client := setupTestDBBench(b)
	defer client.Close()

	ctx := context.Background()
	pool := client.GetPool()

	sql := "SELECT id, username, email, age FROM test_users WHERE username = $1"
	params := []interface{}{"john_doe"}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		// 新实现: 只执行一次查询
		rows, _ := pool.Query(ctx, sql, params...)
		if rows.Next() {
			_ = rows.FieldDescriptions()
			_, _ = rows.Values()
		}
		rows.Close()
	}
}

// 测试辅助函数: 创建 Benchmark 测试数据库
func setupTestDBBench(b *testing.B) *postgres.Client {
	cfg := &postgres.Config{
		Host:     "localhost",
		Port:     5432,
		Database: "isa_platform",
		User:     "postgres",
		Password: "staging_postgres_2024",
		SSLMode:  "disable",
	}

	ctx := context.Background()
	client, err := postgres.NewClient(ctx, cfg)
	if err != nil {
		b.Fatalf("Failed to connect to test database: %v", err)
	}

	// 确保测试数据存在
	_, _ = client.Execute(ctx, "DROP TABLE IF EXISTS test_users")
	createSQL := `
		CREATE TABLE test_users (
			id SERIAL PRIMARY KEY,
			username VARCHAR(50) UNIQUE NOT NULL,
			email VARCHAR(100) UNIQUE NOT NULL,
			age INTEGER,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`
	_, _ = client.Execute(ctx, createSQL)
	insertSQL := "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)"
	_, _ = client.Execute(ctx, insertSQL, "john_doe", "john@example.com", 30)

	return client
}
