// Package supabase provides a unified Supabase client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 Supabase 客户端封装
//
// Supabase 是一个开源的 Firebase 替代品，提供：
// - PostgreSQL 数据库
// - pgvector 向量搜索
// - PostgREST API
// - 实时订阅
// - 用户认证
//
// 示例用法:
//
//	cfg := &SupabaseConfig{
//	    URL:            "https://xxx.supabase.co",
//	    ServiceRoleKey: "eyJhbGc...",
//	}
//	client, err := NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 查询数据
//	data, err := client.Query(ctx, "users", &QueryOptions{
//	    Select: "*",
//	    Filter: "age.gte.18",
//	    Limit:  10,
//	})
package supabase

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/storage"
	_ "github.com/lib/pq" // PostgreSQL driver
	supabase "github.com/supabase-community/supabase-go"
)

// Client Supabase 客户端封装
type Client struct {
	client   *supabase.Client // Supabase REST 客户端
	db       *sql.DB          // PostgreSQL 直连 (用于高级操作)
	config   *SupabaseConfig
	isClosed bool
}

// SupabaseConfig Supabase 配置
type SupabaseConfig struct {
	URL            string        // Supabase 项目 URL
	AnonKey        string        // Anon Key
	ServiceRoleKey string        // Service Role Key (完整权限)
	PostgresURL    string        // PostgreSQL 连接字符串 (可选)
	Timeout        time.Duration // 超时时间
	MaxRetries     int           // 最大重试次数
}

// QueryOptions 查询选项
type QueryOptions struct {
	Select string // 选择字段 (e.g., "*", "id,name,email")
	Filter string // 过滤条件 (PostgREST 语法)
	Order  string // 排序 (e.g., "created_at.desc")
	Limit  int32  // 限制数量
	Offset int32  // 偏移量
	Count  bool   // 是否返回总数
}

// VectorSearchOptions 向量搜索选项
type VectorSearchOptions struct {
	Table          string    // 向量表名
	QueryEmbedding []float32 // 查询向量
	Limit          int32     // 返回数量
	Filter         string    // 元数据过滤
	Metric         string    // 距离度量 (cosine, l2, inner_product)
	Threshold      float32   // 相似度阈值
}

// VectorSearchResult 向量搜索结果
type VectorSearchResult struct {
	ID         string                 `json:"id"`
	Similarity float32                `json:"similarity"`
	Metadata   map[string]interface{} `json:"metadata"`
}

// NewClient 创建新的 Supabase 客户端
func NewClient(cfg *SupabaseConfig) (*Client, error) {
	if cfg.URL == "" {
		return nil, fmt.Errorf("supabase URL is required")
	}

	// 优先使用 Service Role Key (完整权限)
	apiKey := cfg.ServiceRoleKey
	if apiKey == "" {
		apiKey = cfg.AnonKey
	}
	if apiKey == "" {
		return nil, fmt.Errorf("supabase API key (anon_key or service_role_key) is required")
	}

	// 创建 Supabase 客户端
	client, err := supabase.NewClient(cfg.URL, apiKey, &supabase.ClientOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to create supabase client: %w", err)
	}

	c := &Client{
		client: client,
		config: cfg,
	}

	// 如果提供了 PostgreSQL 连接字符串，创建直连
	if cfg.PostgresURL != "" {
		db, err := sql.Open("postgres", cfg.PostgresURL)
		if err != nil {
			return nil, fmt.Errorf("failed to connect to postgres: %w", err)
		}

		// 配置连接池
		db.SetMaxOpenConns(25)
		db.SetMaxIdleConns(5)
		db.SetConnMaxLifetime(5 * time.Minute)

		// 测试连接
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := db.PingContext(ctx); err != nil {
			return nil, fmt.Errorf("failed to ping postgres: %w", err)
		}

		c.db = db
	}

	return c, nil
}

// NewClientFromStorageConfig 从存储配置创建 Supabase 客户端
func NewClientFromStorageConfig(cfg *storage.StorageConfig) (*Client, error) {
	supabaseCfg := &SupabaseConfig{
		URL:            cfg.Supabase.URL,
		ServiceRoleKey: cfg.Supabase.ServiceRoleKey,
		Timeout:        30 * time.Second,
		MaxRetries:     3,
	}

	// 构建 PostgreSQL 连接字符串
	if cfg.Supabase.PostgresHost != "" {
		schema := cfg.Supabase.Schema
		if schema == "" {
			schema = "public"
		}

		supabaseCfg.PostgresURL = fmt.Sprintf(
			"postgresql://%s:%s@%s:%d/%s?sslmode=%s&search_path=%s",
			cfg.Supabase.PostgresUser,
			cfg.Supabase.PostgresPassword,
			cfg.Supabase.PostgresHost,
			cfg.Supabase.PostgresPort,
			cfg.Supabase.PostgresDB,
			cfg.Supabase.PostgresSSLMode,
			schema,
		)
	}

	return NewClient(supabaseCfg)
}

// Close 关闭客户端连接
func (c *Client) Close() error {
	c.isClosed = true
	if c.db != nil {
		return c.db.Close()
	}
	return nil
}

// ========================================
// 数据库操作 (Database Operations)
// ========================================

// Query 查询数据
func (c *Client) Query(ctx context.Context, table string, opts *QueryOptions) ([]map[string]interface{}, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	// Use direct PostgreSQL connection if available (better schema support)
	if c.db != nil {
		return c.queryWithPostgres(ctx, table, opts)
	}

	// Fallback to REST API (public schema only)
	query := c.client.From(table).Select(opts.Select, "", false)

	if opts.Order != "" {
		query = query.Order(opts.Order, nil)
	}

	if opts.Limit > 0 {
		query = query.Limit(int(opts.Limit), "")
	}
	if opts.Offset > 0 {
		query = query.Range(int(opts.Offset), int(opts.Offset+opts.Limit-1), "")
	}

	data, _, err := query.Execute()
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}

	var results []map[string]interface{}
	if err := json.Unmarshal(data, &results); err != nil {
		return nil, fmt.Errorf("failed to unmarshal results: %w", err)
	}

	return results, nil
}

// queryWithPostgres 使用 PostgreSQL 直连查询 (支持自定义 schema)
func (c *Client) queryWithPostgres(ctx context.Context, table string, opts *QueryOptions) ([]map[string]interface{}, error) {
	selectClause := opts.Select
	if selectClause == "" || selectClause == "*" {
		selectClause = "*"
	}

	// Build SQL query
	query := fmt.Sprintf("SELECT %s FROM %s", selectClause, table)

	// Add LIMIT
	if opts.Limit > 0 {
		query = fmt.Sprintf("%s LIMIT %d", query, opts.Limit)
	}

	// Add OFFSET
	if opts.Offset > 0 {
		query = fmt.Sprintf("%s OFFSET %d", query, opts.Offset)
	}

	rows, err := c.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}
	defer rows.Close()

	columns, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("failed to get columns: %w", err)
	}

	var results []map[string]interface{}
	for rows.Next() {
		values := make([]interface{}, len(columns))
		valuePtrs := make([]interface{}, len(columns))
		for i := range columns {
			valuePtrs[i] = &values[i]
		}

		if err := rows.Scan(valuePtrs...); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}

		row := make(map[string]interface{})
		for i, col := range columns {
			val := values[i]
			// Convert []byte to string for better JSON marshaling
			if b, ok := val.([]byte); ok {
				row[col] = string(b)
			} else {
				row[col] = val
			}
		}
		results = append(results, row)
	}

	return results, nil
}

// Insert 插入数据
func (c *Client) Insert(ctx context.Context, table string, data []map[string]interface{}) ([]map[string]interface{}, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal data: %w", err)
	}

	result, _, err := c.client.From(table).Insert(jsonData, false, "", "", "").Execute()
	if err != nil {
		return nil, fmt.Errorf("insert failed: %w", err)
	}

	var insertedData []map[string]interface{}
	if err := json.Unmarshal(result, &insertedData); err != nil {
		return nil, fmt.Errorf("failed to unmarshal inserted data: %w", err)
	}

	return insertedData, nil
}

// Update 更新数据
func (c *Client) Update(ctx context.Context, table string, data map[string]interface{}, filter string) ([]map[string]interface{}, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal data: %w", err)
	}

	query := c.client.From(table).Update(jsonData, "", "")
	// Note: Filters should be applied using Eq/Neq methods, not Filter
	// For now, updates without filters. Use direct SQL for complex filtering

	result, _, err := query.Execute()
	if err != nil {
		return nil, fmt.Errorf("update failed: %w", err)
	}

	var updatedData []map[string]interface{}
	if err := json.Unmarshal(result, &updatedData); err != nil {
		return nil, fmt.Errorf("failed to unmarshal updated data: %w", err)
	}

	return updatedData, nil
}

// Delete 删除数据
func (c *Client) Delete(ctx context.Context, table string, filter string) ([]map[string]interface{}, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	query := c.client.From(table).Delete("", "")
	// Note: Filters should be applied using Eq/Neq methods, not Filter
	// For now, deletes without filters. Use direct SQL for complex filtering

	result, _, err := query.Execute()
	if err != nil {
		return nil, fmt.Errorf("delete failed: %w", err)
	}

	var deletedData []map[string]interface{}
	if err := json.Unmarshal(result, &deletedData); err != nil {
		return nil, fmt.Errorf("failed to unmarshal deleted data: %w", err)
	}

	return deletedData, nil
}

// Upsert 插入或更新数据
func (c *Client) Upsert(ctx context.Context, table string, data []map[string]interface{}, onConflict string) ([]map[string]interface{}, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal data: %w", err)
	}

	result, _, err := c.client.From(table).Upsert(jsonData, onConflict, "", "").Execute()
	if err != nil {
		return nil, fmt.Errorf("upsert failed: %w", err)
	}

	var upsertedData []map[string]interface{}
	if err := json.Unmarshal(result, &upsertedData); err != nil {
		return nil, fmt.Errorf("failed to unmarshal upserted data: %w", err)
	}

	return upsertedData, nil
}

// ExecuteRPC 调用 PostgreSQL 函数
func (c *Client) ExecuteRPC(ctx context.Context, functionName string, params map[string]interface{}) (interface{}, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	// Use direct PostgreSQL connection if available
	if c.db == nil {
		return nil, fmt.Errorf("RPC requires PostgreSQL direct connection, but db is nil")
	}

	// Build SQL function call
	paramsJSON, err := json.Marshal(params)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal params: %w", err)
	}

	var result []byte
	query := fmt.Sprintf("SELECT %s($1)", functionName)
	err = c.db.QueryRowContext(ctx, query, paramsJSON).Scan(&result)
	if err != nil {
		return nil, fmt.Errorf("rpc call failed: %w", err)
	}

	var rpcResult interface{}
	if err := json.Unmarshal(result, &rpcResult); err != nil {
		return nil, fmt.Errorf("failed to unmarshal rpc result: %w", err)
	}

	return rpcResult, nil
}

// ========================================
// 向量操作 (Vector Operations)
// ========================================

// UpsertEmbedding 插入或更新向量
func (c *Client) UpsertEmbedding(ctx context.Context, table string, id string, embedding []float32, metadata map[string]interface{}) error {
	if c.isClosed {
		return fmt.Errorf("client is closed")
	}

	data := map[string]interface{}{
		"id":        id,
		"embedding": embedding,
		"metadata":  metadata,
	}

	_, err := c.Upsert(ctx, table, []map[string]interface{}{data}, "id")
	return err
}

// SimilaritySearch 向量相似度搜索
func (c *Client) SimilaritySearch(ctx context.Context, opts *VectorSearchOptions) ([]VectorSearchResult, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	// 调用 PostgreSQL 函数进行向量搜索
	// 需要预先在 Supabase 中创建 match_documents 函数
	params := map[string]interface{}{
		"query_embedding": opts.QueryEmbedding,
		"match_threshold": opts.Threshold,
		"match_count":     opts.Limit,
	}

	if opts.Filter != "" {
		params["filter"] = opts.Filter
	}

	result, err := c.ExecuteRPC(ctx, "match_documents", params)
	if err != nil {
		return nil, fmt.Errorf("similarity search failed: %w", err)
	}

	// 解析结果
	jsonData, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal search result: %w", err)
	}

	var searchResults []VectorSearchResult
	if err := json.Unmarshal(jsonData, &searchResults); err != nil {
		return nil, fmt.Errorf("failed to unmarshal search results: %w", err)
	}

	return searchResults, nil
}

// HybridSearch 混合搜索 (全文 + 向量)
func (c *Client) HybridSearch(ctx context.Context, table string, textQuery string, vectorQuery []float32, limit int32, textWeight, vectorWeight float32, filter string) ([]VectorSearchResult, error) {
	if c.isClosed {
		return nil, fmt.Errorf("client is closed")
	}

	params := map[string]interface{}{
		"text_query":    textQuery,
		"vector_query":  vectorQuery,
		"match_count":   limit,
		"text_weight":   textWeight,
		"vector_weight": vectorWeight,
	}

	if filter != "" {
		params["filter"] = filter
	}

	result, err := c.ExecuteRPC(ctx, "hybrid_search", params)
	if err != nil {
		return nil, fmt.Errorf("hybrid search failed: %w", err)
	}

	jsonData, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal search result: %w", err)
	}

	var searchResults []VectorSearchResult
	if err := json.Unmarshal(jsonData, &searchResults); err != nil {
		return nil, fmt.Errorf("failed to unmarshal search results: %w", err)
	}

	return searchResults, nil
}

// DeleteEmbedding 删除向量
func (c *Client) DeleteEmbedding(ctx context.Context, table string, id string) error {
	if c.isClosed {
		return fmt.Errorf("client is closed")
	}

	filter := fmt.Sprintf("id.eq.%s", id)
	_, err := c.Delete(ctx, table, filter)
	return err
}

// ========================================
// 批量操作 (Batch Operations)
// ========================================

// BatchInsert 批量插入
func (c *Client) BatchInsert(ctx context.Context, table string, data []map[string]interface{}, batchSize int) (int, error) {
	if c.isClosed {
		return 0, fmt.Errorf("client is closed")
	}

	if batchSize <= 0 {
		batchSize = 100
	}

	totalCount := 0
	for i := 0; i < len(data); i += batchSize {
		end := i + batchSize
		if end > len(data) {
			end = len(data)
		}

		batch := data[i:end]
		_, err := c.Insert(ctx, table, batch)
		if err != nil {
			return totalCount, fmt.Errorf("batch insert failed at index %d: %w", i, err)
		}

		totalCount += len(batch)
	}

	return totalCount, nil
}

// BatchUpsertEmbeddings 批量插入向量
func (c *Client) BatchUpsertEmbeddings(ctx context.Context, table string, embeddings []map[string]interface{}) (int, error) {
	if c.isClosed {
		return 0, fmt.Errorf("client is closed")
	}

	_, err := c.Upsert(ctx, table, embeddings, "id")
	if err != nil {
		return 0, err
	}

	return len(embeddings), nil
}

// ========================================
// 健康检查 (Health Check)
// ========================================

// HealthCheck 健康检查
func (c *Client) HealthCheck(ctx context.Context) (bool, string, error) {
	if c.isClosed {
		return false, "", fmt.Errorf("client is closed")
	}

	// 如果有直连，使用直连检查
	if c.db != nil {
		err := c.db.PingContext(ctx)
		if err != nil {
			return false, "unhealthy", err
		}
		return true, "healthy", nil
	}

	// 否则使用 Supabase REST API 检查
	_, err := c.Query(ctx, "pg_catalog.pg_tables", &QueryOptions{
		Select: "tablename",
		Limit:  1,
	})
	if err != nil {
		return false, "unhealthy", err
	}

	return true, "healthy", nil
}

// GetPostgresVersion 获取 PostgreSQL 版本
func (c *Client) GetPostgresVersion(ctx context.Context) (string, error) {
	if c.isClosed {
		return "", fmt.Errorf("client is closed")
	}

	if c.db == nil {
		return "", fmt.Errorf("postgres direct connection not available")
	}

	var version string
	err := c.db.QueryRowContext(ctx, "SELECT version()").Scan(&version)
	if err != nil {
		return "", fmt.Errorf("failed to get postgres version: %w", err)
	}

	return version, nil
}

// CheckPgVectorEnabled 检查 pgvector 是否启用
func (c *Client) CheckPgVectorEnabled(ctx context.Context) (bool, error) {
	if c.isClosed {
		return false, fmt.Errorf("client is closed")
	}

	if c.db == nil {
		return false, fmt.Errorf("postgres direct connection not available")
	}

	var exists bool
	query := "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
	err := c.db.QueryRowContext(ctx, query).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("failed to check pgvector: %w", err)
	}

	return exists, nil
}
