// Package qdrant provides a unified Qdrant client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 Qdrant 向量数据库客户端封装
//
// 示例用法:
//
//	cfg := &qdrant.Config{
//	    Host: "localhost",
//	    Port: 6333,
//	}
//	client, err := qdrant.NewClient(ctx, cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 创建集合
//	err = client.CreateCollection(ctx, "my_collection", 384)
package qdrant

import (
	"context"
	"fmt"
	"time"

	qdrant_go "github.com/qdrant/go-client/qdrant"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// Client Qdrant 客户端封装
// 提供线程安全的向量数据库操作
type Client struct {
	conn           *grpc.ClientConn
	collections    qdrant_go.CollectionsClient
	points         qdrant_go.PointsClient
	snapshots      qdrant_go.SnapshotsClient
	qdrant         qdrant_go.QdrantClient
	config         *Config
}

// Config Qdrant 客户端配置
type Config struct {
	Host           string        // 主机地址
	Port           int           // 端口 (默认: 6334 for gRPC)
	APIKey         string        // API密钥 (如果启用)
	UseSSL         bool          // 是否使用SSL
	Timeout        time.Duration // 请求超时
	ConnectTimeout time.Duration // 连接超时
}

// Distance 距离度量类型 - aligned with Qdrant official proto
type Distance int32

const (
	DistanceUnknown   Distance = 0  // Unknown/unspecified
	DistanceCosine    Distance = 1  // Cosine similarity
	DistanceEuclid    Distance = 2  // Euclidean distance
	DistanceDot       Distance = 3  // Dot product
	DistanceManhattan Distance = 4  // Manhattan distance
)

// NewClient 创建新的 Qdrant 客户端
//
// 参数:
//
//	ctx: 上下文
//	cfg: Qdrant 配置
//
// 返回:
//
//	*Client: Qdrant 客户端实例
//	error: 错误信息
func NewClient(ctx context.Context, cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if cfg.Port == 0 {
		cfg.Port = 6334 // gRPC 默认端口
	}
	if cfg.Timeout == 0 {
		cfg.Timeout = 30 * time.Second
	}
	if cfg.ConnectTimeout == 0 {
		cfg.ConnectTimeout = 10 * time.Second
	}

	// 构建连接地址
	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)

	// gRPC 连接选项
	var opts []grpc.DialOption
	if cfg.UseSSL {
		// TODO: 添加 TLS 配置
		opts = append(opts, grpc.WithTransportCredentials(insecure.NewCredentials()))
	} else {
		opts = append(opts, grpc.WithTransportCredentials(insecure.NewCredentials()))
	}

	// 创建 gRPC 连接
	conn, err := grpc.Dial(addr, opts...)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to Qdrant: %w", err)
	}

	// 创建客户端
	client := &Client{
		conn:        conn,
		collections: qdrant_go.NewCollectionsClient(conn),
		points:      qdrant_go.NewPointsClient(conn),
		snapshots:   qdrant_go.NewSnapshotsClient(conn),
		qdrant:      qdrant_go.NewQdrantClient(conn),
		config:      cfg,
	}

	// 测试连接
	if err := client.HealthCheck(ctx); err != nil {
		conn.Close()
		return nil, fmt.Errorf("health check failed: %w", err)
	}

	return client, nil
}

// Close 关闭客户端连接
func (c *Client) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// ============================================
// Collection Operations
// ============================================

// CreateCollection 创建向量集合
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	vectorSize: 向量维度
//	distance: 距离度量
//
// 示例:
//
//	err := client.CreateCollection(ctx, "my_vectors", 384, DistanceCosine)
func (c *Client) CreateCollection(ctx context.Context, collectionName string, vectorSize uint64, distance Distance) error {
	_, err := c.collections.Create(ctx, &qdrant_go.CreateCollection{
		CollectionName: collectionName,
		VectorsConfig: &qdrant_go.VectorsConfig{
			Config: &qdrant_go.VectorsConfig_Params{
				Params: &qdrant_go.VectorParams{
					Size:     vectorSize,
					Distance: qdrant_go.Distance(distance),
				},
			},
		},
	})

	if err != nil {
		return fmt.Errorf("failed to create collection: %w", err)
	}
	return nil
}

// DeleteCollection 删除集合
func (c *Client) DeleteCollection(ctx context.Context, collectionName string) error {
	_, err := c.collections.Delete(ctx, &qdrant_go.DeleteCollection{
		CollectionName: collectionName,
	})

	if err != nil {
		return fmt.Errorf("failed to delete collection: %w", err)
	}
	return nil
}

// ListCollections 列出所有集合
func (c *Client) ListCollections(ctx context.Context) ([]string, error) {
	resp, err := c.collections.List(ctx, &qdrant_go.ListCollectionsRequest{})
	if err != nil {
		return nil, fmt.Errorf("failed to list collections: %w", err)
	}

	collections := make([]string, len(resp.Collections))
	for i, col := range resp.Collections {
		collections[i] = col.Name
	}
	return collections, nil
}

// CollectionExists 检查集合是否存在
func (c *Client) CollectionExists(ctx context.Context, collectionName string) (bool, error) {
	resp, err := c.collections.Get(ctx, &qdrant_go.GetCollectionInfoRequest{
		CollectionName: collectionName,
	})

	if err != nil {
		return false, nil // 集合不存在
	}
	return resp != nil, nil
}

// GetCollectionInfo 获取集合信息
func (c *Client) GetCollectionInfo(ctx context.Context, collectionName string) (*qdrant_go.CollectionInfo, error) {
	resp, err := c.collections.Get(ctx, &qdrant_go.GetCollectionInfoRequest{
		CollectionName: collectionName,
	})

	if err != nil {
		return nil, fmt.Errorf("failed to get collection info: %w", err)
	}
	return resp.Result, nil
}

// ============================================
// Point (Vector) Operations
// ============================================

// Point 向量点数据结构
type Point struct {
	ID      interface{}            // uint64 或 string
	Vector  []float32              // 向量数据
	Payload map[string]interface{} // 元数据负载
}

// UpsertPoints 插入或更新向量点
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	points: 向量点列表
//
// 示例:
//
//	points := []qdrant.Point{
//	    {
//	        ID:      uint64(1),
//	        Vector:  []float32{0.1, 0.2, 0.3, ...},
//	        Payload: map[string]interface{}{"category": "documents"},
//	    },
//	}
//	err := client.UpsertPoints(ctx, "my_collection", points)
func (c *Client) UpsertPoints(ctx context.Context, collectionName string, points []Point) error {
	qdrantPoints := make([]*qdrant_go.PointStruct, len(points))

	for i, p := range points {
		point := &qdrant_go.PointStruct{
			Vectors: &qdrant_go.Vectors{
				VectorsOptions: &qdrant_go.Vectors_Vector{
					Vector: &qdrant_go.Vector{
						Data: p.Vector,
					},
				},
			},
		}

		// 设置 ID
		switch id := p.ID.(type) {
		case uint64:
			point.Id = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: id},
			}
		case string:
			point.Id = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: id},
			}
		default:
			return fmt.Errorf("invalid point ID type: must be uint64 or string")
		}

		// 设置 Payload
		if p.Payload != nil {
			payload := make(map[string]*qdrant_go.Value)
			for k, v := range p.Payload {
				payload[k] = convertToQdrantValue(v)
			}
			point.Payload = payload
		}

		qdrantPoints[i] = point
	}

	_, err := c.points.Upsert(ctx, &qdrant_go.UpsertPoints{
		CollectionName: collectionName,
		Points:         qdrantPoints,
	})

	if err != nil {
		return fmt.Errorf("failed to upsert points: %w", err)
	}
	return nil
}

// SearchPoints 向量相似度搜索
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	vector: 查询向量
//	limit: 返回结果数量
//
// 返回:
//
//	[]*qdrant_go.ScoredPoint: 搜索结果
//	error: 错误信息
func (c *Client) SearchPoints(ctx context.Context, collectionName string, vector []float32, limit uint64) ([]*qdrant_go.ScoredPoint, error) {
	resp, err := c.points.Search(ctx, &qdrant_go.SearchPoints{
		CollectionName: collectionName,
		Vector:         vector,
		Limit:          limit,
		WithPayload:    &qdrant_go.WithPayloadSelector{SelectorOptions: &qdrant_go.WithPayloadSelector_Enable{Enable: true}},
	})

	if err != nil {
		return nil, fmt.Errorf("failed to search points: %w", err)
	}
	return resp.Result, nil
}

// DeletePoints 删除向量点
func (c *Client) DeletePoints(ctx context.Context, collectionName string, ids []interface{}) error {
	qdrantIDs := make([]*qdrant_go.PointId, len(ids))

	for i, id := range ids {
		switch v := id.(type) {
		case uint64:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		default:
			return fmt.Errorf("invalid ID type at index %d: must be uint64 or string", i)
		}
	}

	_, err := c.points.Delete(ctx, &qdrant_go.DeletePoints{
		CollectionName: collectionName,
		Points: &qdrant_go.PointsSelector{
			PointsSelectorOneOf: &qdrant_go.PointsSelector_Points{
				Points: &qdrant_go.PointsIdsList{
					Ids: qdrantIDs,
				},
			},
		},
	})

	if err != nil {
		return fmt.Errorf("failed to delete points: %w", err)
	}
	return nil
}

// GetPoints 获取向量点
func (c *Client) GetPoints(ctx context.Context, collectionName string, ids []interface{}) ([]*qdrant_go.RetrievedPoint, error) {
	qdrantIDs := make([]*qdrant_go.PointId, len(ids))

	for i, id := range ids {
		switch v := id.(type) {
		case uint64:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		default:
			return nil, fmt.Errorf("invalid ID type at index %d: must be uint64 or string", i)
		}
	}

	resp, err := c.points.Get(ctx, &qdrant_go.GetPoints{
		CollectionName: collectionName,
		Ids:            qdrantIDs,
		WithPayload:    &qdrant_go.WithPayloadSelector{SelectorOptions: &qdrant_go.WithPayloadSelector_Enable{Enable: true}},
	})

	if err != nil {
		return nil, fmt.Errorf("failed to get points: %w", err)
	}
	return resp.Result, nil
}

// CountPoints 统计向量点数量
func (c *Client) CountPoints(ctx context.Context, collectionName string) (uint64, error) {
	resp, err := c.points.Count(ctx, &qdrant_go.CountPoints{
		CollectionName: collectionName,
	})

	if err != nil {
		return 0, fmt.Errorf("failed to count points: %w", err)
	}
	return resp.Result.Count, nil
}

// ============================================
// Health Check
// ============================================

// HealthCheck 健康检查
func (c *Client) HealthCheck(ctx context.Context) error {
	_, err := c.qdrant.HealthCheck(ctx, &qdrant_go.HealthCheckRequest{})
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}
	return nil
}

// ============================================
// Utility Functions
// ============================================

// convertToQdrantValue 转换 Go 值到 Qdrant Value
func convertToQdrantValue(v interface{}) *qdrant_go.Value {
	switch val := v.(type) {
	case string:
		return &qdrant_go.Value{
			Kind: &qdrant_go.Value_StringValue{StringValue: val},
		}
	case int:
		return &qdrant_go.Value{
			Kind: &qdrant_go.Value_IntegerValue{IntegerValue: int64(val)},
		}
	case int64:
		return &qdrant_go.Value{
			Kind: &qdrant_go.Value_IntegerValue{IntegerValue: val},
		}
	case float64:
		return &qdrant_go.Value{
			Kind: &qdrant_go.Value_DoubleValue{DoubleValue: val},
		}
	case bool:
		return &qdrant_go.Value{
			Kind: &qdrant_go.Value_BoolValue{BoolValue: val},
		}
	default:
		// 默认转为字符串
		return &qdrant_go.Value{
			Kind: &qdrant_go.Value_StringValue{StringValue: fmt.Sprintf("%v", val)},
		}
	}
}

// GetClient 获取底层客户端 (用于高级用法)
func (c *Client) GetPointsClient() qdrant_go.PointsClient {
	return c.points
}

// GetCollectionsClient 获取集合客户端
func (c *Client) GetCollectionsClient() qdrant_go.CollectionsClient {
	return c.collections
}

// ============================================
// Advanced Search Operations
// ============================================

// SearchPointsWithOptions 带高级选项的向量搜索
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	vector: 查询向量
//	limit: 返回结果数量
//	filter: 过滤条件 (可选)
//	scoreThreshold: 分数阈值 (可选)
//	offset: 偏移量 (可选)
//	withPayload: 是否返回payload
//	withVectors: 是否返回向量
//	params: 搜索参数 (hnsw_ef, exact等)
//
// 返回:
//
//	[]*qdrant_go.ScoredPoint: 搜索结果
//	error: 错误信息
func (c *Client) SearchPointsWithOptions(ctx context.Context, collectionName string, vector []float32,
	limit uint64, filter *qdrant_go.Filter, scoreThreshold *float32, offset *uint64,
	withPayload bool, withVectors bool, params map[string]interface{}) ([]*qdrant_go.ScoredPoint, error) {

	searchReq := &qdrant_go.SearchPoints{
		CollectionName: collectionName,
		Vector:         vector,
		Limit:          limit,
	}

	// Set filter if provided
	if filter != nil {
		searchReq.Filter = filter
	}

	// Set score threshold if provided
	if scoreThreshold != nil {
		searchReq.ScoreThreshold = scoreThreshold
	}

	// Set offset if provided
	if offset != nil {
		searchReq.Offset = offset
	}

	// Set payload selector
	if withPayload {
		searchReq.WithPayload = &qdrant_go.WithPayloadSelector{
			SelectorOptions: &qdrant_go.WithPayloadSelector_Enable{Enable: true},
		}
	}

	// Set vector selector
	if withVectors {
		searchReq.WithVectors = &qdrant_go.WithVectorsSelector{
			SelectorOptions: &qdrant_go.WithVectorsSelector_Enable{Enable: true},
		}
	}

	// Set search params if provided
	if params != nil {
		searchReq.Params = &qdrant_go.SearchParams{}
		if hnswEf, ok := params["hnsw_ef"].(uint64); ok {
			searchReq.Params.HnswEf = &hnswEf
		}
		if exact, ok := params["exact"].(bool); ok {
			searchReq.Params.Exact = &exact
		}
	}

	resp, err := c.points.Search(ctx, searchReq)
	if err != nil {
		return nil, fmt.Errorf("failed to search points: %w", err)
	}

	return resp.Result, nil
}

// Scroll 遍历集合中的所有点
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	filter: 过滤条件 (可选)
//	limit: 每页数量
//	offset: 起始点ID (可选)
//	withPayload: 是否返回payload
//	withVectors: 是否返回向量
//
// 返回:
//
//	[]*qdrant_go.RetrievedPoint: 点列表
//	*qdrant_go.PointId: 下一页的offset
//	error: 错误信息
func (c *Client) Scroll(ctx context.Context, collectionName string, filter *qdrant_go.Filter,
	limit uint32, offset *qdrant_go.PointId, withPayload bool, withVectors bool) (
	[]*qdrant_go.RetrievedPoint, *qdrant_go.PointId, error) {

	scrollReq := &qdrant_go.ScrollPoints{
		CollectionName: collectionName,
		Limit:          &limit,
	}

	if filter != nil {
		scrollReq.Filter = filter
	}

	if offset != nil {
		scrollReq.Offset = offset
	}

	if withPayload {
		scrollReq.WithPayload = &qdrant_go.WithPayloadSelector{
			SelectorOptions: &qdrant_go.WithPayloadSelector_Enable{Enable: true},
		}
	}

	if withVectors {
		scrollReq.WithVectors = &qdrant_go.WithVectorsSelector{
			SelectorOptions: &qdrant_go.WithVectorsSelector_Enable{Enable: true},
		}
	}

	resp, err := c.points.Scroll(ctx, scrollReq)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to scroll points: %w", err)
	}

	return resp.Result, resp.NextPageOffset, nil
}

// RecommendPoints 基于正负样本的推荐搜索
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	positive: 正样本ID列表
//	negative: 负样本ID列表
//	limit: 返回结果数量
//	filter: 过滤条件 (可选)
//	withPayload: 是否返回payload
//	withVectors: 是否返回向量
//
// 返回:
//
//	[]*qdrant_go.ScoredPoint: 推荐结果
//	error: 错误信息
func (c *Client) RecommendPoints(ctx context.Context, collectionName string, positive []interface{},
	negative []interface{}, limit uint64, filter *qdrant_go.Filter, withPayload bool, withVectors bool) (
	[]*qdrant_go.ScoredPoint, error) {

	// Convert positive IDs
	positiveIDs := make([]*qdrant_go.PointId, len(positive))
	for i, id := range positive {
		switch v := id.(type) {
		case uint64:
			positiveIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			positiveIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		}
	}

	// Convert negative IDs
	negativeIDs := make([]*qdrant_go.PointId, len(negative))
	for i, id := range negative {
		switch v := id.(type) {
		case uint64:
			negativeIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			negativeIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		}
	}

	recommendReq := &qdrant_go.RecommendPoints{
		CollectionName: collectionName,
		Positive:       positiveIDs,
		Negative:       negativeIDs,
		Limit:          limit,
	}

	if filter != nil {
		recommendReq.Filter = filter
	}

	if withPayload {
		recommendReq.WithPayload = &qdrant_go.WithPayloadSelector{
			SelectorOptions: &qdrant_go.WithPayloadSelector_Enable{Enable: true},
		}
	}

	if withVectors {
		recommendReq.WithVectors = &qdrant_go.WithVectorsSelector{
			SelectorOptions: &qdrant_go.WithVectorsSelector_Enable{Enable: true},
		}
	}

	resp, err := c.points.Recommend(ctx, recommendReq)
	if err != nil {
		return nil, fmt.Errorf("failed to recommend points: %w", err)
	}

	return resp.Result, nil
}

// ============================================
// Payload Operations
// ============================================

// UpdatePayload 更新点的payload
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	payload: 要更新的payload数据
//	ids: 点ID列表
//
// 返回:
//
//	error: 错误信息
func (c *Client) UpdatePayload(ctx context.Context, collectionName string,
	payload map[string]interface{}, ids []interface{}) error {

	// Convert IDs
	qdrantIDs := make([]*qdrant_go.PointId, len(ids))
	for i, id := range ids {
		switch v := id.(type) {
		case uint64:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		default:
			return fmt.Errorf("invalid ID type at index %d: must be uint64 or string", i)
		}
	}

	// Convert payload
	qdrantPayload := make(map[string]*qdrant_go.Value)
	for k, v := range payload {
		qdrantPayload[k] = convertToQdrantValue(v)
	}

	_, err := c.points.SetPayload(ctx, &qdrant_go.SetPayloadPoints{
		CollectionName: collectionName,
		Payload:        qdrantPayload,
		PointsSelector: &qdrant_go.PointsSelector{
			PointsSelectorOneOf: &qdrant_go.PointsSelector_Points{
				Points: &qdrant_go.PointsIdsList{Ids: qdrantIDs},
			},
		},
	})

	if err != nil {
		return fmt.Errorf("failed to update payload: %w", err)
	}

	return nil
}

// DeletePayloadFields 删除指定的payload字段
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	keys: 要删除的字段名列表
//	ids: 点ID列表
//
// 返回:
//
//	error: 错误信息
func (c *Client) DeletePayloadFields(ctx context.Context, collectionName string,
	keys []string, ids []interface{}) error {

	// Convert IDs
	qdrantIDs := make([]*qdrant_go.PointId, len(ids))
	for i, id := range ids {
		switch v := id.(type) {
		case uint64:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		default:
			return fmt.Errorf("invalid ID type at index %d: must be uint64 or string", i)
		}
	}

	_, err := c.points.DeletePayload(ctx, &qdrant_go.DeletePayloadPoints{
		CollectionName: collectionName,
		Keys:           keys,
		PointsSelector: &qdrant_go.PointsSelector{
			PointsSelectorOneOf: &qdrant_go.PointsSelector_Points{
				Points: &qdrant_go.PointsIdsList{Ids: qdrantIDs},
			},
		},
	})

	if err != nil {
		return fmt.Errorf("failed to delete payload fields: %w", err)
	}

	return nil
}

// ClearPayload 清除所有payload数据
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	ids: 点ID列表
//
// 返回:
//
//	error: 错误信息
func (c *Client) ClearPayload(ctx context.Context, collectionName string, ids []interface{}) error {

	// Convert IDs
	qdrantIDs := make([]*qdrant_go.PointId, len(ids))
	for i, id := range ids {
		switch v := id.(type) {
		case uint64:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Num{Num: v},
			}
		case string:
			qdrantIDs[i] = &qdrant_go.PointId{
				PointIdOptions: &qdrant_go.PointId_Uuid{Uuid: v},
			}
		default:
			return fmt.Errorf("invalid ID type at index %d: must be uint64 or string", i)
		}
	}

	_, err := c.points.ClearPayload(ctx, &qdrant_go.ClearPayloadPoints{
		CollectionName: collectionName,
		Points: &qdrant_go.PointsSelector{
			PointsSelectorOneOf: &qdrant_go.PointsSelector_Points{
				Points: &qdrant_go.PointsIdsList{Ids: qdrantIDs},
			},
		},
	})

	if err != nil {
		return fmt.Errorf("failed to clear payload: %w", err)
	}

	return nil
}

// ============================================
// Index Management
// ============================================

// CreateFieldIndex 为payload字段创建索引
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	fieldName: 字段名
//	fieldType: 字段类型 (keyword, integer, float, geo, text)
//
// 返回:
//	error: 错误信息
func (c *Client) CreateFieldIndex(ctx context.Context, collectionName string,
	fieldName string, fieldType qdrant_go.FieldType) error {

	_, err := c.points.CreateFieldIndex(ctx, &qdrant_go.CreateFieldIndexCollection{
		CollectionName: collectionName,
		FieldName:      fieldName,
		FieldType:      &fieldType,
	})

	if err != nil {
		return fmt.Errorf("failed to create field index: %w", err)
	}

	return nil
}

// DeleteFieldIndex 删除payload字段索引
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	fieldName: 字段名
//
// 返回:
//
//	error: 错误信息
func (c *Client) DeleteFieldIndex(ctx context.Context, collectionName string, fieldName string) error {

	_, err := c.points.DeleteFieldIndex(ctx, &qdrant_go.DeleteFieldIndexCollection{
		CollectionName: collectionName,
		FieldName:      fieldName,
	})

	if err != nil {
		return fmt.Errorf("failed to delete field index: %w", err)
	}

	return nil
}

// ============================================
// Snapshot Operations
// ============================================

// CreateSnapshot 创建集合快照
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//
// 返回:
//
//	string: 快照名称
//	error: 错误信息
func (c *Client) CreateSnapshot(ctx context.Context, collectionName string) (string, error) {

	resp, err := c.snapshots.Create(ctx, &qdrant_go.CreateSnapshotRequest{
		CollectionName: collectionName,
	})

	if err != nil {
		return "", fmt.Errorf("failed to create snapshot: %w", err)
	}

	return resp.SnapshotDescription.Name, nil
}

// ListSnapshots 列出所有快照
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//
// 返回:
//
//	[]*qdrant_go.SnapshotDescription: 快照列表
//	error: 错误信息
func (c *Client) ListSnapshots(ctx context.Context, collectionName string) ([]*qdrant_go.SnapshotDescription, error) {

	resp, err := c.snapshots.List(ctx, &qdrant_go.ListSnapshotsRequest{
		CollectionName: collectionName,
	})

	if err != nil {
		return nil, fmt.Errorf("failed to list snapshots: %w", err)
	}

	return resp.SnapshotDescriptions, nil
}

// DeleteSnapshot 删除快照
//
// 参数:
//
//	ctx: 上下文
//	collectionName: 集合名称
//	snapshotName: 快照名称
//
// 返回:
//
//	error: 错误信息
func (c *Client) DeleteSnapshot(ctx context.Context, collectionName string, snapshotName string) error {

	_, err := c.snapshots.Delete(ctx, &qdrant_go.DeleteSnapshotRequest{
		CollectionName: collectionName,
		SnapshotName:   snapshotName,
	})

	if err != nil {
		return fmt.Errorf("failed to delete snapshot: %w", err)
	}

	return nil
}
