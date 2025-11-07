// Package neo4j provides a unified Neo4j client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 Neo4j 图数据库客户端封装
//
// 示例用法:
//
//	cfg := &neo4j.Config{
//	    URI:      "bolt://localhost:7687",
//	    Username: "neo4j",
//	    Password: "password",
//	}
//	client, err := neo4j.NewClient(ctx, cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 执行 Cypher 查询
//	result, err := client.Run(ctx, "CREATE (n:Person {name: $name}) RETURN n", map[string]interface{}{"name": "Alice"})
package neo4j

import (
	"context"
	"fmt"
	"time"

	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
)

// Client Neo4j 客户端封装
// 提供线程安全的图数据库操作
type Client struct {
	driver neo4j.DriverWithContext
	config *Config
}

// Config Neo4j 客户端配置
type Config struct {
	URI                   string        // 连接URI (bolt://host:port 或 neo4j://host:port)
	Username              string        // 用户名
	Password              string        // 密码
	Database              string        // 数据库名 (默认: neo4j)
	MaxConnectionPoolSize int           // 最大连接池大小
	ConnectionTimeout     time.Duration // 连接超时
	MaxTransactionRetry   int           // 最大事务重试次数
	FetchSize             int           // 查询结果批量大小
	Encrypted             bool          // 是否加密连接
}

// NewClient 创建新的 Neo4j 客户端
//
// 参数:
//
//	ctx: 上下文
//	cfg: Neo4j 配置
//
// 返回:
//
//	*Client: Neo4j 客户端实例
//	error: 错误信息
func NewClient(ctx context.Context, cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if cfg.Database == "" {
		cfg.Database = "neo4j"
	}
	if cfg.MaxConnectionPoolSize == 0 {
		cfg.MaxConnectionPoolSize = 50
	}
	if cfg.ConnectionTimeout == 0 {
		cfg.ConnectionTimeout = 30 * time.Second
	}
	if cfg.MaxTransactionRetry == 0 {
		cfg.MaxTransactionRetry = 3
	}
	if cfg.FetchSize == 0 {
		cfg.FetchSize = 1000
	}

	// 配置驱动
	auth := neo4j.BasicAuth(cfg.Username, cfg.Password, "")

	driver, err := neo4j.NewDriverWithContext(
		cfg.URI,
		auth,
		func(config *neo4j.Config) {
			config.MaxConnectionPoolSize = cfg.MaxConnectionPoolSize
			config.ConnectionAcquisitionTimeout = cfg.ConnectionTimeout
			config.MaxTransactionRetryTime = time.Duration(cfg.MaxTransactionRetry) * time.Second
			config.FetchSize = cfg.FetchSize
			// Note: Encryption is now handled via URI scheme (bolt:// vs bolt+s://)
			// The Encrypted field is removed in v5
		},
	)

	if err != nil {
		return nil, fmt.Errorf("failed to create Neo4j driver: %w", err)
	}

	// 验证连接
	if err := driver.VerifyConnectivity(ctx); err != nil {
		driver.Close(ctx)
		return nil, fmt.Errorf("failed to verify connectivity: %w", err)
	}

	return &Client{
		driver: driver,
		config: cfg,
	}, nil
}

// Close 关闭客户端连接
func (c *Client) Close(ctx context.Context) error {
	if c.driver != nil {
		return c.driver.Close(ctx)
	}
	return nil
}

// ============================================
// Cypher Query Operations
// ============================================

// QueryResult Cypher 查询结果
type QueryResult struct {
	Records []map[string]interface{}
	Summary neo4j.ResultSummary
}

// Run 执行 Cypher 查询
//
// 参数:
//
//	ctx: 上下文
//	cypher: Cypher 查询语句
//	params: 查询参数
//
// 返回:
//
//	*QueryResult: 查询结果
//	error: 错误信息
//
// 示例:
//
//	result, err := client.Run(ctx,
//	    "MATCH (n:Person) WHERE n.age > $age RETURN n.name",
//	    map[string]interface{}{"age": 25})
func (c *Client) Run(ctx context.Context, cypher string, params map[string]interface{}) (*QueryResult, error) {
	session := c.driver.NewSession(ctx, neo4j.SessionConfig{
		AccessMode:   neo4j.AccessModeRead,
		DatabaseName: c.config.Database,
	})
	defer session.Close(ctx)

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return nil, fmt.Errorf("failed to run query: %w", err)
	}

	records, err := result.Collect(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to collect results: %w", err)
	}

	summary, err := result.Consume(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get summary: %w", err)
	}

	// 转换记录为 map
	recordMaps := make([]map[string]interface{}, len(records))
	for i, record := range records {
		recordMaps[i] = record.AsMap()
	}

	return &QueryResult{
		Records: recordMaps,
		Summary: summary,
	}, nil
}

// Write 执行写操作 Cypher 查询
//
// 参数:
//
//	ctx: 上下文
//	cypher: Cypher 查询语句
//	params: 查询参数
//
// 示例:
//
//	result, err := client.Write(ctx,
//	    "CREATE (n:Person {name: $name, age: $age}) RETURN n",
//	    map[string]interface{}{"name": "Alice", "age": 30})
func (c *Client) Write(ctx context.Context, cypher string, params map[string]interface{}) (*QueryResult, error) {
	session := c.driver.NewSession(ctx, neo4j.SessionConfig{
		AccessMode:   neo4j.AccessModeWrite,
		DatabaseName: c.config.Database,
	})
	defer session.Close(ctx)

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return nil, fmt.Errorf("failed to run write query: %w", err)
	}

	records, err := result.Collect(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to collect results: %w", err)
	}

	summary, err := result.Consume(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get summary: %w", err)
	}

	// 转换记录为 map
	recordMaps := make([]map[string]interface{}, len(records))
	for i, record := range records {
		recordMaps[i] = record.AsMap()
	}

	return &QueryResult{
		Records: recordMaps,
		Summary: summary,
	}, nil
}

// ============================================
// Transaction Support
// ============================================

// TransactionWork 事务工作函数类型
type TransactionWork func(ctx context.Context, tx neo4j.ExplicitTransaction) (interface{}, error)

// ExecuteWriteTransaction 执行写事务
//
// 参数:
//
//	ctx: 上下文
//	work: 事务工作函数
//
// 示例:
//
//	result, err := client.ExecuteWriteTransaction(ctx, func(ctx context.Context, tx neo4j.ExplicitTransaction) (interface{}, error) {
//	    result, err := tx.Run(ctx, "CREATE (n:Person {name: $name}) RETURN n", map[string]interface{}{"name": "Bob"})
//	    if err != nil {
//	        return nil, err
//	    }
//	    record, err := result.Single(ctx)
//	    if err != nil {
//	        return nil, err
//	    }
//	    return record.Values[0], nil
//	})
func (c *Client) ExecuteWriteTransaction(ctx context.Context, work TransactionWork) (interface{}, error) {
	session := c.driver.NewSession(ctx, neo4j.SessionConfig{
		AccessMode:   neo4j.AccessModeWrite,
		DatabaseName: c.config.Database,
	})
	defer session.Close(ctx)

	return session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (interface{}, error) {
		// Convert ManagedTransaction to ExplicitTransaction interface
		explicitTx, ok := tx.(neo4j.ExplicitTransaction)
		if !ok {
			return nil, fmt.Errorf("failed to convert to explicit transaction")
		}
		return work(ctx, explicitTx)
	})
}

// ExecuteReadTransaction 执行读事务
func (c *Client) ExecuteReadTransaction(ctx context.Context, work TransactionWork) (interface{}, error) {
	session := c.driver.NewSession(ctx, neo4j.SessionConfig{
		AccessMode:   neo4j.AccessModeRead,
		DatabaseName: c.config.Database,
	})
	defer session.Close(ctx)

	return session.ExecuteRead(ctx, func(tx neo4j.ManagedTransaction) (interface{}, error) {
		// Convert ManagedTransaction to ExplicitTransaction interface
		explicitTx, ok := tx.(neo4j.ExplicitTransaction)
		if !ok {
			return nil, fmt.Errorf("failed to convert to explicit transaction")
		}
		return work(ctx, explicitTx)
	})
}

// ============================================
// Node Operations
// ============================================

// Node 节点数据结构
type Node struct {
	ID         int64
	Labels     []string
	Properties map[string]interface{}
}

// CreateNode 创建节点
//
// 参数:
//
//	ctx: 上下文
//	labels: 节点标签
//	properties: 节点属性
//
// 返回:
//
//	*Node: 创建的节点
//	error: 错误信息
func (c *Client) CreateNode(ctx context.Context, labels []string, properties map[string]interface{}) (*Node, error) {
	// 构建标签字符串
	labelStr := ""
	for _, label := range labels {
		labelStr += ":" + label
	}

	cypher := fmt.Sprintf("CREATE (n%s $props) RETURN n", labelStr)

	result, err := c.Write(ctx, cypher, map[string]interface{}{"props": properties})
	if err != nil {
		return nil, err
	}

	if len(result.Records) == 0 {
		return nil, fmt.Errorf("no node created")
	}

	nodeValue := result.Records[0]["n"]
	node, ok := nodeValue.(neo4j.Node)
	if !ok {
		return nil, fmt.Errorf("invalid node type")
	}

	return &Node{
		ID:         node.GetId(),
		Labels:     node.Labels,
		Properties: node.Props,
	}, nil
}

// FindNodes 查找节点
//
// 参数:
//
//	ctx: 上下文
//	label: 节点标签
//	properties: 匹配属性
//
// 返回:
//
//	[]*Node: 节点列表
//	error: 错误信息
func (c *Client) FindNodes(ctx context.Context, label string, properties map[string]interface{}) ([]*Node, error) {
	// 构建 WHERE 子句
	whereClause := ""
	if len(properties) > 0 {
		whereClause = " WHERE "
		first := true
		for key := range properties {
			if !first {
				whereClause += " AND "
			}
			whereClause += fmt.Sprintf("n.%s = $props.%s", key, key)
			first = false
		}
	}

	cypher := fmt.Sprintf("MATCH (n:%s)%s RETURN n", label, whereClause)

	result, err := c.Run(ctx, cypher, map[string]interface{}{"props": properties})
	if err != nil {
		return nil, err
	}

	nodes := make([]*Node, len(result.Records))
	for i, record := range result.Records {
		nodeValue := record["n"]
		node, ok := nodeValue.(neo4j.Node)
		if !ok {
			continue
		}

		nodes[i] = &Node{
			ID:         node.GetId(),
			Labels:     node.Labels,
			Properties: node.Props,
		}
	}

	return nodes, nil
}

// DeleteNode 删除节点
func (c *Client) DeleteNode(ctx context.Context, nodeID int64, detach bool) error {
	cypher := "MATCH (n) WHERE id(n) = $id DELETE n"
	if detach {
		cypher = "MATCH (n) WHERE id(n) = $id DETACH DELETE n"
	}

	_, err := c.Write(ctx, cypher, map[string]interface{}{"id": nodeID})
	return err
}

// ============================================
// Relationship Operations
// ============================================

// Relationship 关系数据结构
type Relationship struct {
	ID         int64
	Type       string
	StartID    int64
	EndID      int64
	Properties map[string]interface{}
}

// CreateRelationship 创建关系
//
// 参数:
//
//	ctx: 上下文
//	startNodeID: 起始节点ID
//	endNodeID: 结束节点ID
//	relType: 关系类型
//	properties: 关系属性
func (c *Client) CreateRelationship(ctx context.Context, startNodeID, endNodeID int64, relType string, properties map[string]interface{}) (*Relationship, error) {
	cypher := fmt.Sprintf(`
		MATCH (start), (end)
		WHERE id(start) = $startID AND id(end) = $endID
		CREATE (start)-[r:%s $props]->(end)
		RETURN r
	`, relType)

	result, err := c.Write(ctx, cypher, map[string]interface{}{
		"startID": startNodeID,
		"endID":   endNodeID,
		"props":   properties,
	})

	if err != nil {
		return nil, err
	}

	if len(result.Records) == 0 {
		return nil, fmt.Errorf("no relationship created")
	}

	relValue := result.Records[0]["r"]
	rel, ok := relValue.(neo4j.Relationship)
	if !ok {
		return nil, fmt.Errorf("invalid relationship type")
	}

	return &Relationship{
		ID:         rel.GetId(),
		Type:       rel.Type,
		StartID:    rel.StartId,
		EndID:      rel.EndId,
		Properties: rel.Props,
	}, nil
}

// ============================================
// Utility Functions
// ============================================

// VerifyConnectivity 验证连接
func (c *Client) VerifyConnectivity(ctx context.Context) error {
	return c.driver.VerifyConnectivity(ctx)
}

// GetServerInfo 获取服务器信息
func (c *Client) GetServerInfo(ctx context.Context) (neo4j.ServerInfo, error) {
	return c.driver.GetServerInfo(ctx)
}

// ExecuteCypher 执行原始 Cypher (便捷方法)
func (c *Client) ExecuteCypher(ctx context.Context, cypher string, params map[string]interface{}, write bool) (*QueryResult, error) {
	if write {
		return c.Write(ctx, cypher, params)
	}
	return c.Run(ctx, cypher, params)
}

// GetDriver 获取底层驱动 (用于高级用法)
func (c *Client) GetDriver() neo4j.DriverWithContext {
	return c.driver
}

// NewSession 创建新会话 (用于高级用法)
func (c *Client) NewSession(ctx context.Context, config neo4j.SessionConfig) neo4j.SessionWithContext {
	if config.DatabaseName == "" {
		config.DatabaseName = c.config.Database
	}
	return c.driver.NewSession(ctx, config)
}
