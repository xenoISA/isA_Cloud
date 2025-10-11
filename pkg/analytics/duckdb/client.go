// Package duckdb provides a unified DuckDB client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 DuckDB 分析数据库客户端封装
//
// DuckDB 是一个嵌入式 OLAP 数据库，专为分析查询优化
// 支持：
// - SQL 查询（兼容 PostgreSQL 语法）
// - 高性能列式存储
// - Parquet、CSV、JSON 等多种格式
// - 直接查询对象存储中的文件
//
// 示例用法:
//
//	cfg := &duckdb.Config{
//	    DatabasePath: "/path/to/database.db",
//	    MemoryLimit:  "2GB",
//	    Threads:      4,
//	}
//	client, err := duckdb.NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 执行查询
//	rows, err := client.Query(ctx, "SELECT * FROM my_table LIMIT 10")
//	defer rows.Close()
package duckdb

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	_ "github.com/marcboeker/go-duckdb" // DuckDB driver
)

// Client DuckDB 客户端封装
type Client struct {
	db     *sql.DB
	config *Config
}

// Config DuckDB 客户端配置
type Config struct {
	DatabasePath string        // 数据库文件路径（":memory:" 表示内存数据库）
	ReadOnly     bool          // 是否只读模式
	MemoryLimit  string        // 内存限制，如 "2GB"
	Threads      int           // 线程数，0 表示自动
	MaxOpenConns int           // 最大打开连接数
	MaxIdleConns int           // 最大空闲连接数
	ConnMaxLife  time.Duration // 连接最大生命周期
	AccessMode   string        // 访问模式：automatic, read_only, read_write
	Extensions   []string      // 要加载的扩展，如 ["httpfs", "parquet"]
}

// NewClient 创建新的 DuckDB 客户端
//
// 参数:
//
//	cfg: DuckDB 配置
//
// 返回:
//
//	*Client: DuckDB 客户端实例
//	error: 错误信息
//
// 示例:
//
//	cfg := &Config{
//	    DatabasePath: "/data/analytics.db",
//	    MemoryLimit:  "2GB",
//	    Threads:      4,
//	}
//	client, err := NewClient(cfg)
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if cfg.DatabasePath == "" {
		cfg.DatabasePath = ":memory:"
	}
	if cfg.Threads == 0 {
		cfg.Threads = 4
	}
	if cfg.MaxOpenConns == 0 {
		cfg.MaxOpenConns = 10
	}
	if cfg.MaxIdleConns == 0 {
		cfg.MaxIdleConns = 5
	}
	if cfg.ConnMaxLife == 0 {
		cfg.ConnMaxLife = 1 * time.Hour
	}
	if cfg.AccessMode == "" {
		if cfg.ReadOnly {
			cfg.AccessMode = "read_only"
		} else {
			cfg.AccessMode = "read_write"
		}
	}

	// 构建连接字符串
	// 注意：对于 go-duckdb，空字符串表示内存数据库
	connStr := cfg.DatabasePath
	if connStr == ":memory:" {
		connStr = "" // go-duckdb 使用空字符串表示内存数据库
	}

	// 打开数据库连接
	// 对于文件数据库，可以添加参数
	if cfg.DatabasePath != ":memory:" && cfg.DatabasePath != "" {
		var params []string
		if cfg.AccessMode != "" {
			params = append(params, fmt.Sprintf("access_mode=%s", cfg.AccessMode))
		}
		if len(params) > 0 {
			connStr += "?" + strings.Join(params, "&")
		}
	}

	db, err := sql.Open("duckdb", connStr)
	if err != nil {
		return nil, fmt.Errorf("failed to open DuckDB: %w", err)
	}

	// 设置连接池参数
	db.SetMaxOpenConns(cfg.MaxOpenConns)
	db.SetMaxIdleConns(cfg.MaxIdleConns)
	db.SetConnMaxLifetime(cfg.ConnMaxLife)

	client := &Client{
		db:     db,
		config: cfg,
	}

	// 对于内存数据库，使用 PRAGMA 设置参数
	if cfg.DatabasePath == ":memory:" {
		ctx := context.Background()

		if cfg.MemoryLimit != "" {
			_, err := client.Exec(ctx, fmt.Sprintf("SET memory_limit='%s'", cfg.MemoryLimit))
			if err != nil {
				db.Close()
				return nil, fmt.Errorf("failed to set memory limit: %w", err)
			}
		}

		if cfg.Threads > 0 {
			_, err := client.Exec(ctx, fmt.Sprintf("SET threads=%d", cfg.Threads))
			if err != nil {
				db.Close()
				return nil, fmt.Errorf("failed to set threads: %w", err)
			}
		}
	}

	// 加载扩展
	if len(cfg.Extensions) > 0 {
		ctx := context.Background()
		for _, ext := range cfg.Extensions {
			if err := client.InstallExtension(ctx, ext); err != nil {
				db.Close()
				return nil, fmt.Errorf("failed to install extension %s: %w", ext, err)
			}
			if err := client.LoadExtension(ctx, ext); err != nil {
				db.Close()
				return nil, fmt.Errorf("failed to load extension %s: %w", ext, err)
			}
		}
	}

	// 测试连接
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return client, nil
}

// buildConnString 构建连接字符串
func buildConnString(cfg *Config) string {
	// 对于内存数据库，参数需要在文件名中设置，而不是查询字符串
	// 参考：https://github.com/marcboeker/go-duckdb

	connStr := cfg.DatabasePath

	// 如果不是内存数据库，可以使用查询参数
	if cfg.DatabasePath != ":memory:" {
		var params []string

		if cfg.AccessMode != "" {
			params = append(params, fmt.Sprintf("access_mode=%s", cfg.AccessMode))
		}
		if cfg.MemoryLimit != "" {
			params = append(params, fmt.Sprintf("memory_limit=%s", cfg.MemoryLimit))
		}
		if cfg.Threads > 0 {
			params = append(params, fmt.Sprintf("threads=%d", cfg.Threads))
		}

		if len(params) > 0 {
			connStr += "?" + strings.Join(params, "&")
		}
	}
	// 对于内存数据库，参数会在连接后通过 PRAGMA 设置

	return connStr
}

// Close 关闭数据库连接
func (c *Client) Close() error {
	if c.db != nil {
		return c.db.Close()
	}
	return nil
}

// ============================================
// 查询操作 (Query Operations)
// ============================================

// QueryResult 查询结果
type QueryResult struct {
	Columns []string        // 列名
	Rows    [][]interface{} // 数据行
	Count   int             // 行数
}

// Query 执行 SQL 查询
//
// 参数:
//
//	ctx: 上下文
//	query: SQL 查询语句
//	args: 查询参数（用于参数化查询）
//
// 返回:
//
//	*sql.Rows: 查询结果（使用后需要关闭）
//	error: 错误信息
//
// 示例:
//
//	rows, err := client.Query(ctx, "SELECT * FROM users WHERE age > ?", 18)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer rows.Close()
//
//	for rows.Next() {
//	    var id int
//	    var name string
//	    err := rows.Scan(&id, &name)
//	    fmt.Printf("ID: %d, Name: %s\n", id, name)
//	}
func (c *Client) Query(ctx context.Context, query string, args ...interface{}) (*sql.Rows, error) {
	rows, err := c.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}
	return rows, nil
}

// QueryRow 执行返回单行的查询
//
// 示例:
//
//	var count int
//	err := client.QueryRow(ctx, "SELECT COUNT(*) FROM users").Scan(&count)
func (c *Client) QueryRow(ctx context.Context, query string, args ...interface{}) *sql.Row {
	return c.db.QueryRowContext(ctx, query, args...)
}

// QueryToMap 执行查询并返回 map 切片
//
// 返回:
//
//	[]map[string]interface{}: 查询结果（每行是一个 map）
//	error: 错误信息
//
// 示例:
//
//	results, err := client.QueryToMap(ctx, "SELECT * FROM users LIMIT 10")
//	for _, row := range results {
//	    fmt.Printf("ID: %v, Name: %v\n", row["id"], row["name"])
//	}
func (c *Client) QueryToMap(ctx context.Context, query string, args ...interface{}) ([]map[string]interface{}, error) {
	rows, err := c.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	return scanRowsToMap(rows)
}

// QueryToStruct 执行查询并返回结构化结果
func (c *Client) QueryToStruct(ctx context.Context, query string, args ...interface{}) (*QueryResult, error) {
	rows, err := c.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	// 获取列名
	columns, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("failed to get columns: %w", err)
	}

	// 扫描行数据
	var data [][]interface{}
	for rows.Next() {
		values := make([]interface{}, len(columns))
		valuePtrs := make([]interface{}, len(columns))
		for i := range values {
			valuePtrs[i] = &values[i]
		}

		if err := rows.Scan(valuePtrs...); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}

		data = append(data, values)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows error: %w", err)
	}

	return &QueryResult{
		Columns: columns,
		Rows:    data,
		Count:   len(data),
	}, nil
}

// Exec 执行 SQL 语句（INSERT、UPDATE、DELETE、CREATE 等）
//
// 返回:
//
//	sql.Result: 执行结果（包含影响行数等信息）
//	error: 错误信息
//
// 示例:
//
//	result, err := client.Exec(ctx, "INSERT INTO users (name, age) VALUES (?, ?)", "Alice", 25)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	rowsAffected, _ := result.RowsAffected()
//	fmt.Printf("Inserted %d rows\n", rowsAffected)
func (c *Client) Exec(ctx context.Context, query string, args ...interface{}) (sql.Result, error) {
	result, err := c.db.ExecContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("exec failed: %w", err)
	}
	return result, nil
}

// ExecMulti 批量执行 SQL 语句
//
// 示例:
//
//	queries := []string{
//	    "CREATE TABLE users (id INTEGER, name VARCHAR)",
//	    "INSERT INTO users VALUES (1, 'Alice')",
//	    "INSERT INTO users VALUES (2, 'Bob')",
//	}
//	err := client.ExecMulti(ctx, queries)
func (c *Client) ExecMulti(ctx context.Context, queries []string) error {
	tx, err := c.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	for _, query := range queries {
		if _, err := tx.ExecContext(ctx, query); err != nil {
			return fmt.Errorf("failed to execute query: %w", err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// ============================================
// 表管理 (Table Management)
// ============================================

// TableInfo 表信息
type TableInfo struct {
	Name        string
	Schema      string
	RowCount    int64
	ColumnCount int
}

// ListTables 列出所有表
//
// 示例:
//
//	tables, err := client.ListTables(ctx, "main")
//	for _, table := range tables {
//	    fmt.Printf("Table: %s.%s\n", table.Schema, table.Name)
//	}
func (c *Client) ListTables(ctx context.Context, schema string) ([]TableInfo, error) {
	if schema == "" {
		schema = "main"
	}

	query := `
		SELECT table_schema, table_name, estimated_size
		FROM information_schema.tables
		WHERE table_schema = ?
		ORDER BY table_name
	`

	rows, err := c.Query(ctx, query, schema)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tables []TableInfo
	for rows.Next() {
		var table TableInfo
		var size sql.NullInt64
		if err := rows.Scan(&table.Schema, &table.Name, &size); err != nil {
			return nil, err
		}
		tables = append(tables, table)
	}

	return tables, nil
}

// GetTableSchema 获取表结构
//
// 示例:
//
//	columns, err := client.GetTableSchema(ctx, "users")
//	for _, col := range columns {
//	    fmt.Printf("Column: %s, Type: %s\n", col.Name, col.Type)
//	}
func (c *Client) GetTableSchema(ctx context.Context, tableName string) ([]ColumnInfo, error) {
	query := `
		SELECT column_name, data_type, is_nullable, column_default
		FROM information_schema.columns
		WHERE table_name = ?
		ORDER BY ordinal_position
	`

	rows, err := c.Query(ctx, query, tableName)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var columns []ColumnInfo
	for rows.Next() {
		var col ColumnInfo
		var nullable string
		var defaultVal sql.NullString

		if err := rows.Scan(&col.Name, &col.Type, &nullable, &defaultVal); err != nil {
			return nil, err
		}

		col.Nullable = (nullable == "YES")
		if defaultVal.Valid {
			col.Default = defaultVal.String
		}

		columns = append(columns, col)
	}

	return columns, nil
}

// ColumnInfo 列信息
type ColumnInfo struct {
	Name     string
	Type     string
	Nullable bool
	Default  string
}

// CreateTable 创建表
//
// 示例:
//
//	err := client.CreateTable(ctx, "users", []ColumnInfo{
//	    {Name: "id", Type: "INTEGER", Nullable: false},
//	    {Name: "name", Type: "VARCHAR", Nullable: true},
//	    {Name: "age", Type: "INTEGER", Nullable: true},
//	})
func (c *Client) CreateTable(ctx context.Context, tableName string, columns []ColumnInfo) error {
	var colDefs []string
	for _, col := range columns {
		def := fmt.Sprintf("%s %s", col.Name, col.Type)
		if !col.Nullable {
			def += " NOT NULL"
		}
		if col.Default != "" {
			def += " DEFAULT " + col.Default
		}
		colDefs = append(colDefs, def)
	}

	query := fmt.Sprintf("CREATE TABLE %s (%s)", tableName, strings.Join(colDefs, ", "))
	_, err := c.Exec(ctx, query)
	return err
}

// DropTable 删除表
func (c *Client) DropTable(ctx context.Context, tableName string, ifExists bool) error {
	query := "DROP TABLE "
	if ifExists {
		query += "IF EXISTS "
	}
	query += tableName

	_, err := c.Exec(ctx, query)
	return err
}

// ============================================
// 数据导入/导出 (Import/Export)
// ============================================

// ImportCSV 从 CSV 文件导入数据
//
// 参数:
//
//	ctx: 上下文
//	tableName: 目标表名
//	filePath: CSV 文件路径
//	options: 导入选项（如分隔符、头部等）
//
// 示例:
//
//	err := client.ImportCSV(ctx, "users", "/path/to/users.csv", map[string]string{
//	    "header": "true",
//	    "delimiter": ",",
//	})
func (c *Client) ImportCSV(ctx context.Context, tableName, filePath string, options map[string]string) error {
	query := fmt.Sprintf("COPY %s FROM '%s'", tableName, filePath)

	var opts []string
	for k, v := range options {
		opts = append(opts, fmt.Sprintf("%s %s", k, v))
	}
	if len(opts) > 0 {
		query += " (" + strings.Join(opts, ", ") + ")"
	}

	_, err := c.Exec(ctx, query)
	return err
}

// ImportParquet 从 Parquet 文件导入数据
//
// 示例:
//
//	err := client.ImportParquet(ctx, "users", "/path/to/users.parquet")
func (c *Client) ImportParquet(ctx context.Context, tableName, filePath string) error {
	query := fmt.Sprintf("COPY %s FROM '%s' (FORMAT PARQUET)", tableName, filePath)
	_, err := c.Exec(ctx, query)
	return err
}

// ExportCSV 导出数据到 CSV 文件
//
// 示例:
//
//	err := client.ExportCSV(ctx, "SELECT * FROM users", "/path/to/output.csv", map[string]string{
//	    "header": "true",
//	})
func (c *Client) ExportCSV(ctx context.Context, query, filePath string, options map[string]string) error {
	exportQuery := fmt.Sprintf("COPY (%s) TO '%s'", query, filePath)

	var opts []string
	for k, v := range options {
		opts = append(opts, fmt.Sprintf("%s %s", k, v))
	}
	if len(opts) > 0 {
		exportQuery += " (" + strings.Join(opts, ", ") + ")"
	}

	_, err := c.Exec(ctx, exportQuery)
	return err
}

// ExportParquet 导出数据到 Parquet 文件
func (c *Client) ExportParquet(ctx context.Context, query, filePath string) error {
	exportQuery := fmt.Sprintf("COPY (%s) TO '%s' (FORMAT PARQUET)", query, filePath)
	_, err := c.Exec(ctx, exportQuery)
	return err
}

// QueryFile 直接查询文件（无需导入）
//
// 支持的格式: CSV, Parquet, JSON
//
// 示例:
//
//	// 查询 Parquet 文件
//	result, err := client.QueryFile(ctx, "SELECT * FROM 's3://bucket/data.parquet' LIMIT 10")
//
//	// 查询 CSV 文件
//	result, err := client.QueryFile(ctx, "SELECT * FROM read_csv_auto('/path/to/data.csv')")
func (c *Client) QueryFile(ctx context.Context, query string) (*QueryResult, error) {
	return c.QueryToStruct(ctx, query)
}

// ============================================
// 扩展管理 (Extension Management)
// ============================================

// InstallExtension 安装扩展
//
// 常用扩展:
//   - httpfs: 访问 HTTP/S3 文件系统
//   - parquet: Parquet 文件支持
//   - json: JSON 处理
//   - icu: 国际化支持
//
// 示例:
//
//	err := client.InstallExtension(ctx, "httpfs")
func (c *Client) InstallExtension(ctx context.Context, extension string) error {
	query := fmt.Sprintf("INSTALL %s", extension)
	_, err := c.Exec(ctx, query)
	return err
}

// LoadExtension 加载扩展
func (c *Client) LoadExtension(ctx context.Context, extension string) error {
	query := fmt.Sprintf("LOAD %s", extension)
	_, err := c.Exec(ctx, query)
	return err
}

// ListExtensions 列出已安装的扩展
func (c *Client) ListExtensions(ctx context.Context) ([]string, error) {
	query := "SELECT extension_name FROM duckdb_extensions() WHERE installed"
	rows, err := c.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var extensions []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		extensions = append(extensions, name)
	}

	return extensions, nil
}

// ============================================
// 事务管理 (Transaction Management)
// ============================================

// BeginTx 开始事务
//
// 示例:
//
//	tx, err := client.BeginTx(ctx, nil)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer tx.Rollback()
//
//	_, err = tx.ExecContext(ctx, "INSERT INTO users VALUES (?, ?)", 1, "Alice")
//	if err != nil {
//	    return err
//	}
//
//	err = tx.Commit()
func (c *Client) BeginTx(ctx context.Context, opts *sql.TxOptions) (*sql.Tx, error) {
	return c.db.BeginTx(ctx, opts)
}

// ============================================
// 工具方法 (Utility Methods)
// ============================================

// Ping 测试数据库连接
func (c *Client) Ping(ctx context.Context) error {
	return c.db.PingContext(ctx)
}

// GetVersion 获取 DuckDB 版本
func (c *Client) GetVersion(ctx context.Context) (string, error) {
	var version string
	err := c.QueryRow(ctx, "SELECT version()").Scan(&version)
	if err != nil {
		return "", err
	}
	return version, nil
}

// GetConfig 获取客户端配置
func (c *Client) GetConfig() *Config {
	return c.config
}

// GetDB 获取底层 sql.DB 对象（用于高级用法）
func (c *Client) GetDB() *sql.DB {
	return c.db
}

// ============================================
// 辅助函数 (Helper Functions)
// ============================================

// scanRowsToMap 将 sql.Rows 转换为 map 切片
func scanRowsToMap(rows *sql.Rows) ([]map[string]interface{}, error) {
	columns, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("failed to get columns: %w", err)
	}

	var results []map[string]interface{}

	for rows.Next() {
		values := make([]interface{}, len(columns))
		valuePtrs := make([]interface{}, len(columns))
		for i := range values {
			valuePtrs[i] = &values[i]
		}

		if err := rows.Scan(valuePtrs...); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}

		row := make(map[string]interface{})
		for i, col := range columns {
			row[col] = values[i]
		}

		results = append(results, row)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows error: %w", err)
	}

	return results, nil
}
