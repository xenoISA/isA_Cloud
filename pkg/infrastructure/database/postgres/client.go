// Package postgres provides a unified PostgreSQL client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 PostgreSQL 数据库客户端封装
//
// 示例用法:
//
//	cfg := &postgres.Config{
//	    Host:     "localhost",
//	    Port:     5432,
//	    Database: "mydb",
//	    User:     "postgres",
//	    Password: "password",
//	}
//	client, err := postgres.NewClient(ctx, cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 执行查询
//	rows, err := client.Query(ctx, "SELECT * FROM users WHERE id = $1", userId)
package postgres

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Client PostgreSQL 客户端封装
// 提供线程安全的数据库连接池
type Client struct {
	pool   *pgxpool.Pool
	config *Config
}

// Config PostgreSQL 客户端配置
type Config struct {
	Host              string        // 主机地址
	Port              int           // 端口
	Database          string        // 数据库名
	User              string        // 用户名
	Password          string        // 密码
	SSLMode           string        // SSL模式: disable, require, verify-ca, verify-full
	MaxConns          int32         // 最大连接数
	MinConns          int32         // 最小连接数
	MaxConnLifetime   time.Duration // 连接最大生命周期
	MaxConnIdleTime   time.Duration // 连接最大空闲时间
	HealthCheckPeriod time.Duration // 健康检查周期
	ConnectTimeout    time.Duration // 连接超时
	Schema            string        // 默认模式
}

// NewClient 创建新的 PostgreSQL 客户端
//
// 参数:
//
//	ctx: 上下文
//	cfg: PostgreSQL 配置
//
// 返回:
//
//	*Client: PostgreSQL 客户端实例
//	error: 错误信息
func NewClient(ctx context.Context, cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if cfg.Port == 0 {
		cfg.Port = 5432
	}
	if cfg.SSLMode == "" {
		cfg.SSLMode = "disable"
	}
	if cfg.MaxConns == 0 {
		cfg.MaxConns = 25
	}
	if cfg.MinConns == 0 {
		cfg.MinConns = 5
	}
	if cfg.MaxConnLifetime == 0 {
		cfg.MaxConnLifetime = 1 * time.Hour
	}
	if cfg.MaxConnIdleTime == 0 {
		cfg.MaxConnIdleTime = 30 * time.Minute
	}
	if cfg.HealthCheckPeriod == 0 {
		cfg.HealthCheckPeriod = 1 * time.Minute
	}
	if cfg.ConnectTimeout == 0 {
		cfg.ConnectTimeout = 10 * time.Second
	}
	if cfg.Schema == "" {
		cfg.Schema = "public"
	}

	// 构建连接字符串
	connString := fmt.Sprintf(
		"host=%s port=%d dbname=%s user=%s password=%s sslmode=%s search_path=%s",
		cfg.Host, cfg.Port, cfg.Database, cfg.User, cfg.Password, cfg.SSLMode, cfg.Schema,
	)

	// 配置连接池
	poolConfig, err := pgxpool.ParseConfig(connString)
	if err != nil {
		return nil, fmt.Errorf("failed to parse connection string: %w", err)
	}

	poolConfig.MaxConns = cfg.MaxConns
	poolConfig.MinConns = cfg.MinConns
	poolConfig.MaxConnLifetime = cfg.MaxConnLifetime
	poolConfig.MaxConnIdleTime = cfg.MaxConnIdleTime
	poolConfig.HealthCheckPeriod = cfg.HealthCheckPeriod
	poolConfig.ConnConfig.ConnectTimeout = cfg.ConnectTimeout

	// 创建连接池
	pool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}

	// 测试连接
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return &Client{
		pool:   pool,
		config: cfg,
	}, nil
}

// Close 关闭客户端连接池
func (c *Client) Close() {
	if c.pool != nil {
		c.pool.Close()
	}
}

// Ping 测试数据库连接
func (c *Client) Ping(ctx context.Context) error {
	return c.pool.Ping(ctx)
}

// ============================================
// Query Operations
// ============================================

// Query 执行查询并返回多行结果
//
// 参数:
//
//	ctx: 上下文
//	sql: SQL 查询语句
//	args: 查询参数
//
// 返回:
//
//	pgx.Rows: 查询结果集
//	error: 错误信息
//
// 示例:
//
//	rows, err := client.Query(ctx, "SELECT * FROM users WHERE age > $1", 18)
//	if err != nil {
//	    return err
//	}
//	defer rows.Close()
//
//	for rows.Next() {
//	    var user User
//	    err := rows.Scan(&user.ID, &user.Name, &user.Age)
//	    if err != nil {
//	        return err
//	    }
//	    fmt.Println(user)
//	}
func (c *Client) Query(ctx context.Context, sql string, args ...interface{}) (pgx.Rows, error) {
	rows, err := c.pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}
	return rows, nil
}

// QueryRow 执行查询并返回单行结果
//
// 参数:
//
//	ctx: 上下文
//	sql: SQL 查询语句
//	args: 查询参数
//
// 返回:
//
//	pgx.Row: 查询结果行
//
// 示例:
//
//	var user User
//	err := client.QueryRow(ctx, "SELECT * FROM users WHERE id = $1", userId).Scan(&user.ID, &user.Name)
func (c *Client) QueryRow(ctx context.Context, sql string, args ...interface{}) pgx.Row {
	return c.pool.QueryRow(ctx, sql, args...)
}

// Execute 执行 INSERT/UPDATE/DELETE 语句
//
// 参数:
//
//	ctx: 上下文
//	sql: SQL 语句
//	args: 参数
//
// 返回:
//
//	pgconn.CommandTag: 命令标签 (包含受影响的行数)
//	error: 错误信息
//
// 示例:
//
//	tag, err := client.Execute(ctx, "UPDATE users SET name = $1 WHERE id = $2", "John", 1)
//	fmt.Printf("Rows affected: %d\n", tag.RowsAffected())
func (c *Client) Execute(ctx context.Context, sql string, args ...interface{}) (int64, error) {
	tag, err := c.pool.Exec(ctx, sql, args...)
	if err != nil {
		return 0, fmt.Errorf("execute failed: %w", err)
	}
	return tag.RowsAffected(), nil
}

// ============================================
// Transaction Support
// ============================================

// Tx 事务封装
type Tx struct {
	tx pgx.Tx
}

// BeginTx 开始事务
//
// 参数:
//
//	ctx: 上下文
//	opts: 事务选项
//
// 返回:
//
//	*Tx: 事务对象
//	error: 错误信息
//
// 示例:
//
//	tx, err := client.BeginTx(ctx, pgx.TxOptions{})
//	if err != nil {
//	    return err
//	}
//	defer tx.Rollback(ctx)
//
//	// 执行事务操作
//	_, err = tx.Execute(ctx, "INSERT INTO users ...")
//	if err != nil {
//	    return err
//	}
//
//	return tx.Commit(ctx)
func (c *Client) BeginTx(ctx context.Context, opts pgx.TxOptions) (*Tx, error) {
	tx, err := c.pool.BeginTx(ctx, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	return &Tx{tx: tx}, nil
}

// Query 在事务中执行查询
func (t *Tx) Query(ctx context.Context, sql string, args ...interface{}) (pgx.Rows, error) {
	rows, err := t.tx.Query(ctx, sql, args...)
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}
	return rows, nil
}

// QueryRow 在事务中执行单行查询
func (t *Tx) QueryRow(ctx context.Context, sql string, args ...interface{}) pgx.Row {
	return t.tx.QueryRow(ctx, sql, args...)
}

// Execute 在事务中执行语句
func (t *Tx) Execute(ctx context.Context, sql string, args ...interface{}) (int64, error) {
	tag, err := t.tx.Exec(ctx, sql, args...)
	if err != nil {
		return 0, fmt.Errorf("execute failed: %w", err)
	}
	return tag.RowsAffected(), nil
}

// Commit 提交事务
func (t *Tx) Commit(ctx context.Context) error {
	if err := t.tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}
	return nil
}

// Rollback 回滚事务
func (t *Tx) Rollback(ctx context.Context) error {
	if err := t.tx.Rollback(ctx); err != nil && err != pgx.ErrTxClosed {
		return fmt.Errorf("failed to rollback transaction: %w", err)
	}
	return nil
}

// SendBatch 在事务中发送批量操作
func (t *Tx) SendBatch(ctx context.Context, batch *pgx.Batch) pgx.BatchResults {
	return t.tx.SendBatch(ctx, batch)
}

// ============================================
// Batch Operations
// ============================================

// Batch 批量操作封装
type Batch struct {
	batch *pgx.Batch
}

// NewBatch 创建新的批量操作
//
// 返回:
//
//	*Batch: 批量操作对象
//
// 示例:
//
//	batch := client.NewBatch()
//	batch.Queue("INSERT INTO users (name) VALUES ($1)", "Alice")
//	batch.Queue("INSERT INTO users (name) VALUES ($1)", "Bob")
//
//	results, err := client.SendBatch(ctx, batch)
//	if err != nil {
//	    return err
//	}
//	defer results.Close()
func (c *Client) NewBatch() *Batch {
	return &Batch{
		batch: &pgx.Batch{},
	}
}

// Queue 添加操作到批次
func (b *Batch) Queue(sql string, args ...interface{}) {
	b.batch.Queue(sql, args...)
}

// Len 返回批次中的操作数量
func (b *Batch) Len() int {
	return b.batch.Len()
}

// SendBatch 发送批量操作
func (c *Client) SendBatch(ctx context.Context, batch *Batch) (pgx.BatchResults, error) {
	return c.pool.SendBatch(ctx, batch.batch), nil
}

// ============================================
// Connection Pool Stats
// ============================================

// PoolStats 连接池统计信息
type PoolStats struct {
	AcquireCount            int64
	AcquireDuration         time.Duration
	AcquiredConns           int32
	CanceledAcquireCount    int64
	ConstructingConns       int32
	EmptyAcquireCount       int64
	IdleConns               int32
	MaxConns                int32
	TotalConns              int32
	NewConnsCount           int64
	MaxLifetimeDestroyCount int64
	MaxIdleDestroyCount     int64
}

// Stats 获取连接池统计信息
func (c *Client) Stats() *PoolStats {
	stats := c.pool.Stat()
	return &PoolStats{
		AcquireCount:            stats.AcquireCount(),
		AcquireDuration:         stats.AcquireDuration(),
		AcquiredConns:           stats.AcquiredConns(),
		CanceledAcquireCount:    stats.CanceledAcquireCount(),
		ConstructingConns:       stats.ConstructingConns(),
		EmptyAcquireCount:       stats.EmptyAcquireCount(),
		IdleConns:               stats.IdleConns(),
		MaxConns:                stats.MaxConns(),
		TotalConns:              stats.TotalConns(),
		NewConnsCount:           stats.NewConnsCount(),
		MaxLifetimeDestroyCount: stats.MaxLifetimeDestroyCount(),
		MaxIdleDestroyCount:     stats.MaxIdleDestroyCount(),
	}
}

// ============================================
// Utility Functions
// ============================================

// TableExists 检查表是否存在
func (c *Client) TableExists(ctx context.Context, tableName string) (bool, error) {
	var exists bool
	sql := `
		SELECT EXISTS (
			SELECT FROM information_schema.tables
			WHERE table_schema = $1
			AND table_name = $2
		)
	`
	err := c.pool.QueryRow(ctx, sql, c.config.Schema, tableName).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("failed to check table existence: %w", err)
	}
	return exists, nil
}

// GetDatabaseVersion 获取数据库版本
func (c *Client) GetDatabaseVersion(ctx context.Context) (string, error) {
	var version string
	err := c.pool.QueryRow(ctx, "SELECT version()").Scan(&version)
	if err != nil {
		return "", fmt.Errorf("failed to get database version: %w", err)
	}
	return version, nil
}

// GetPool 获取底层连接池 (用于高级用法)
func (c *Client) GetPool() *pgxpool.Pool {
	return c.pool
}
