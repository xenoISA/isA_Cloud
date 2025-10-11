## DuckDB SDK Client

## 文件名：`duckdb/client.go`

DuckDB SDK Client 为 isA Cloud 平台提供高性能的 OLAP 分析能力。DuckDB 是一个嵌入式列式数据库，专为分析查询优化，主要用于数据分析和 BI 报表。

## 主要功能

- **SQL 查询**：兼容 PostgreSQL 语法的 SQL 查询
- **高性能列式存储**：优化的列式存储引擎
- **多格式支持**：Parquet、CSV、JSON 等
- **直接查询文件**：无需导入即可查询 MinIO 中的文件
- **扩展系统**：支持加载各种扩展（httpfs、parquet、json 等）
- **用户隔离**：数据库文件独立存储，支持多租户

## 快速开始

### 1. 安装依赖

```bash
go get github.com/marcboeker/go-duckdb
```

### 2. 创建客户端

```go
package main

import (
    "context"
    "log"
    
    "github.com/isa-cloud/isa_cloud/pkg/analytics/duckdb"
)

func main() {
    // 配置 DuckDB 客户端
    cfg := &duckdb.Config{
        DatabasePath: "/data/analytics.db",
        MemoryLimit:  "2GB",
        Threads:      4,
        Extensions:   []string{"httpfs", "parquet"},
    }
    
    // 创建客户端
    client, err := duckdb.NewClient(cfg)
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()
    
    // 使用客户端...
}
```

## 使用示例

### 查询操作

#### 执行查询

```go
ctx := context.Background()

// 执行查询
rows, err := client.Query(ctx, "SELECT * FROM users WHERE age > ?", 18)
if err != nil {
    log.Fatal(err)
}
defer rows.Close()

// 遍历结果
for rows.Next() {
    var id int
    var name string
    var age int
    
    err := rows.Scan(&id, &name, &age)
    if err != nil {
        log.Fatal(err)
    }
    
    fmt.Printf("ID: %d, Name: %s, Age: %d\n", id, name, age)
}
```

#### 查询单行

```go
var count int
err := client.QueryRow(ctx, "SELECT COUNT(*) FROM users").Scan(&count)
if err != nil {
    log.Fatal(err)
}
fmt.Printf("Total users: %d\n", count)
```

#### 查询返回 Map

```go
// 返回 []map[string]interface{}
results, err := client.QueryToMap(ctx, "SELECT * FROM users LIMIT 10")
if err != nil {
    log.Fatal(err)
}

for _, row := range results {
    fmt.Printf("User: %+v\n", row)
    fmt.Printf("  ID: %v\n", row["id"])
    fmt.Printf("  Name: %v\n", row["name"])
}
```

#### 查询返回结构化数据

```go
result, err := client.QueryToStruct(ctx, "SELECT * FROM sales ORDER BY date DESC LIMIT 100")
if err != nil {
    log.Fatal(err)
}

fmt.Printf("Columns: %v\n", result.Columns)
fmt.Printf("Row Count: %d\n", result.Count)

for _, row := range result.Rows {
    fmt.Printf("Row: %v\n", row)
}
```

### 数据写入

#### 执行 INSERT/UPDATE/DELETE

```go
// INSERT
result, err := client.Exec(ctx, 
    "INSERT INTO users (name, age, email) VALUES (?, ?, ?)",
    "Alice", 30, "alice@example.com")
if err != nil {
    log.Fatal(err)
}

rowsAffected, _ := result.RowsAffected()
fmt.Printf("Inserted %d rows\n", rowsAffected)

// UPDATE
result, err = client.Exec(ctx, "UPDATE users SET age = age + 1 WHERE name = ?", "Alice")

// DELETE
result, err = client.Exec(ctx, "DELETE FROM users WHERE age < ?", 18)
```

#### 批量执行

```go
queries := []string{
    "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR, age INTEGER)",
    "INSERT INTO users VALUES (1, 'Alice', 30)",
    "INSERT INTO users VALUES (2, 'Bob', 25)",
    "INSERT INTO users VALUES (3, 'Charlie', 35)",
}

err := client.ExecMulti(ctx, queries)
if err != nil {
    log.Fatal(err)
}
```

### 表管理

#### 创建表

```go
columns := []duckdb.ColumnInfo{
    {Name: "id", Type: "INTEGER", Nullable: false},
    {Name: "name", Type: "VARCHAR", Nullable: false},
    {Name: "email", Type: "VARCHAR", Nullable: true},
    {Name: "age", Type: "INTEGER", Nullable: true},
    {Name: "created_at", Type: "TIMESTAMP", Default: "CURRENT_TIMESTAMP"},
}

err := client.CreateTable(ctx, "users", columns)
if err != nil {
    log.Fatal(err)
}
```

#### 列出表

```go
tables, err := client.ListTables(ctx, "main")
if err != nil {
    log.Fatal(err)
}

for _, table := range tables {
    fmt.Printf("Table: %s.%s\n", table.Schema, table.Name)
}
```

#### 获取表结构

```go
columns, err := client.GetTableSchema(ctx, "users")
if err != nil {
    log.Fatal(err)
}

for _, col := range columns {
    fmt.Printf("Column: %s, Type: %s, Nullable: %v\n", 
        col.Name, col.Type, col.Nullable)
}
```

#### 删除表

```go
// 删除表（如果存在）
err := client.DropTable(ctx, "old_table", true)
```

### 数据导入/导出

#### 从 CSV 导入

```go
// 从 CSV 文件导入数据
err := client.ImportCSV(ctx, "users", "/path/to/users.csv", map[string]string{
    "header":    "true",
    "delimiter": ",",
    "quote":     "\"",
})
if err != nil {
    log.Fatal(err)
}
```

#### 从 Parquet 导入

```go
// 从 Parquet 文件导入（高性能）
err := client.ImportParquet(ctx, "sales_data", "/path/to/sales.parquet")
if err != nil {
    log.Fatal(err)
}
```

#### 导出到 CSV

```go
// 导出查询结果到 CSV
err := client.ExportCSV(ctx, 
    "SELECT * FROM users WHERE age > 25", 
    "/path/to/output.csv",
    map[string]string{
        "header": "true",
    })
```

#### 导出到 Parquet

```go
// 导出到 Parquet（推荐，压缩率高，性能好）
err := client.ExportParquet(ctx,
    "SELECT * FROM sales WHERE date >= '2024-01-01'",
    "/path/to/sales_2024.parquet")
```

#### 直接查询文件（无需导入）

```go
// 查询 CSV 文件
result, err := client.QueryFile(ctx, `
    SELECT * FROM read_csv_auto('/path/to/data.csv')
    WHERE age > 25
    LIMIT 100
`)

// 查询 Parquet 文件
result, err := client.QueryFile(ctx, `
    SELECT date, SUM(amount) as total
    FROM '/path/to/sales.parquet'
    GROUP BY date
    ORDER BY date DESC
`)

// 查询 JSON 文件
result, err := client.QueryFile(ctx, `
    SELECT * FROM read_json_auto('/path/to/data.json')
`)
```

### 与 MinIO 集成

#### 配置 S3/MinIO 访问

```go
// 安装和加载 httpfs 扩展
err := client.InstallExtension(ctx, "httpfs")
err = client.LoadExtension(ctx, "httpfs")

// 配置 S3 凭证
_, err = client.Exec(ctx, `
    SET s3_endpoint='localhost:9000';
    SET s3_access_key_id='minioadmin';
    SET s3_secret_access_key='minioadmin';
    SET s3_use_ssl=false;
`)
```

#### 直接查询 MinIO 中的文件

```go
// 查询 MinIO 中的 Parquet 文件
result, err := client.QueryFile(ctx, `
    SELECT *
    FROM 's3://my-bucket/data/sales.parquet'
    WHERE date BETWEEN '2024-01-01' AND '2024-12-31'
`)

// 多个文件聚合查询
result, err := client.QueryFile(ctx, `
    SELECT 
        DATE_TRUNC('month', date) as month,
        SUM(amount) as monthly_total
    FROM 's3://my-bucket/data/*.parquet'
    GROUP BY month
    ORDER BY month
`)
```

#### 从 MinIO 导入到表

```go
// 创建表并从 S3 导入
_, err := client.Exec(ctx, `
    CREATE TABLE sales AS
    SELECT * FROM 's3://my-bucket/data/sales.parquet'
`)

// 或者插入到已存在的表
_, err = client.Exec(ctx, `
    INSERT INTO sales
    SELECT * FROM 's3://my-bucket/data/new_sales.parquet'
`)
```

### 扩展管理

#### 安装和加载扩展

```go
// 安装扩展
err := client.InstallExtension(ctx, "httpfs")
err = client.InstallExtension(ctx, "parquet")
err = client.InstallExtension(ctx, "json")

// 加载扩展
err = client.LoadExtension(ctx, "httpfs")
err = client.LoadExtension(ctx, "parquet")
err = client.LoadExtension(ctx, "json")
```

#### 列出已安装的扩展

```go
extensions, err := client.ListExtensions(ctx)
if err != nil {
    log.Fatal(err)
}

for _, ext := range extensions {
    fmt.Printf("Extension: %s\n", ext)
}
```

### 事务管理

```go
// 开始事务
tx, err := client.BeginTx(ctx, nil)
if err != nil {
    log.Fatal(err)
}
defer tx.Rollback() // 如果没有提交，则回滚

// 在事务中执行操作
_, err = tx.ExecContext(ctx, "INSERT INTO users VALUES (?, ?, ?)", 1, "Alice", 30)
if err != nil {
    return err
}

_, err = tx.ExecContext(ctx, "UPDATE accounts SET balance = balance - 100 WHERE user_id = ?", 1)
if err != nil {
    return err
}

// 提交事务
err = tx.Commit()
if err != nil {
    log.Fatal(err)
}
```

## 配置选项

```go
cfg := &duckdb.Config{
    DatabasePath: "/data/analytics.db",  // 数据库文件路径（":memory:" 表示内存数据库）
    ReadOnly:     false,                 // 是否只读模式
    MemoryLimit:  "2GB",                 // 内存限制
    Threads:      4,                     // 线程数
    MaxOpenConns: 10,                    // 最大打开连接数
    MaxIdleConns: 5,                     // 最大空闲连接数
    ConnMaxLife:  1 * time.Hour,         // 连接最大生命周期
    AccessMode:   "read_write",          // 访问模式
    Extensions:   []string{"httpfs", "parquet"}, // 自动加载的扩展
}
```

## 用户隔离实践

为了实现多租户隔离，每个用户/组织使用独立的数据库文件：

```go
func createUserDatabase(userID string) (*duckdb.Client, error) {
    // 数据库文件存储在用户专属目录
    dbPath := fmt.Sprintf("/data/users/%s/analytics.db", userID)
    
    // 确保目录存在
    os.MkdirAll(filepath.Dir(dbPath), 0755)
    
    cfg := &duckdb.Config{
        DatabasePath: dbPath,
        MemoryLimit:  "1GB",
        Threads:      2,
        Extensions:   []string{"httpfs", "parquet"},
    }
    
    return duckdb.NewClient(cfg)
}
```

## 性能优化

### 1. 使用列式存储

```go
// 使用 Parquet 格式存储大数据集
_, err := client.Exec(ctx, `
    COPY (SELECT * FROM large_table)
    TO 'data.parquet' (FORMAT PARQUET, COMPRESSION 'SNAPPY')
`)

// 直接查询 Parquet 文件
result, err := client.QueryFile(ctx, "SELECT * FROM 'data.parquet' WHERE ...")
```

### 2. 创建索引

```go
// 创建索引加速查询
_, err := client.Exec(ctx, "CREATE INDEX idx_users_email ON users(email)")
```

### 3. 使用视图

```go
// 创建视图简化复杂查询
_, err := client.Exec(ctx, `
    CREATE VIEW active_users AS
    SELECT * FROM users
    WHERE last_login > CURRENT_DATE - INTERVAL 30 DAY
`)

// 查询视图
result, err := client.Query(ctx, "SELECT * FROM active_users")
```

### 4. 分区数据

```go
// 按日期分区存储数据
_, err := client.Exec(ctx, `
    CREATE TABLE sales (
        date DATE,
        product_id INTEGER,
        amount DECIMAL
    ) PARTITION BY (date)
`)
```

## 常用分析查询

### 时间序列分析

```go
result, err := client.QueryToMap(ctx, `
    SELECT 
        DATE_TRUNC('day', created_at) as day,
        COUNT(*) as user_count,
        SUM(total_spent) as revenue
    FROM users
    WHERE created_at >= CURRENT_DATE - INTERVAL 30 DAY
    GROUP BY day
    ORDER BY day
`)
```

### 聚合分析

```go
result, err := client.QueryToMap(ctx, `
    SELECT 
        category,
        COUNT(*) as product_count,
        AVG(price) as avg_price,
        SUM(quantity_sold) as total_sold
    FROM products
    GROUP BY category
    ORDER BY total_sold DESC
`)
```

### 窗口函数

```go
result, err := client.QueryToMap(ctx, `
    SELECT 
        user_id,
        order_date,
        amount,
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_date DESC) as order_rank,
        SUM(amount) OVER (PARTITION BY user_id) as total_spent
    FROM orders
`)
```

## 错误处理

```go
rows, err := client.Query(ctx, "SELECT * FROM users")
if err != nil {
    if strings.Contains(err.Error(), "does not exist") {
        log.Println("Table does not exist")
    } else if strings.Contains(err.Error(), "syntax error") {
        log.Println("SQL syntax error")
    } else {
        log.Printf("Query error: %v", err)
    }
    return err
}
defer rows.Close()
```

## 集成到 gRPC 服务

参考 `cmd/duckdb-service/` 目录中的 gRPC 服务实现示例。

## 与 isA_MCP 集成

DuckDB 主要在 isA_MCP 项目中用于数据分析：

```go
// 在 MCP 中使用 DuckDB 进行数据分析
func analyzeUserBehavior(userID string) (*AnalysisResult, error) {
    // 创建用户专属数据库
    client, err := createUserDatabase(userID)
    if err != nil {
        return nil, err
    }
    defer client.Close()
    
    // 从 MinIO 加载用户数据
    _, err = client.Exec(ctx, fmt.Sprintf(`
        CREATE TABLE user_events AS
        SELECT * FROM 's3://analytics/users/%s/events/*.parquet'
    `, userID))
    
    // 执行分析查询
    result, err := client.QueryToMap(ctx, `
        SELECT 
            event_type,
            COUNT(*) as count,
            AVG(duration) as avg_duration
        FROM user_events
        WHERE date >= CURRENT_DATE - INTERVAL 7 DAY
        GROUP BY event_type
        ORDER BY count DESC
    `)
    
    return result, err
}
```

## 相关文档

- [DuckDB 官方文档](https://duckdb.org/docs/)
- [DuckDB SQL 参考](https://duckdb.org/docs/sql/introduction)
- [go-duckdb GitHub](https://github.com/marcboeker/go-duckdb)
- isA Cloud 项目架构文档



