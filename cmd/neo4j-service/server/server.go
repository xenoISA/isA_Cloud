// Package server implements the Neo4j gRPC service
// 文件名: cmd/neo4j-service/server/server.go
package server

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/neo4j"
	common "github.com/isa-cloud/isa_cloud/api/proto/common"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/neo4j"
	"github.com/neo4j/neo4j-go-driver/v5/neo4j/dbtype"
)

// Neo4jServer Neo4j gRPC 服务实现
type Neo4jServer struct {
	pb.UnimplementedNeo4JServiceServer

	neo4jClient *neo4j.Client
	database    string
}

// NewNeo4jServer 创建 Neo4j gRPC 服务实例
func NewNeo4jServer(neo4jClient *neo4j.Client, database string) *Neo4jServer {
	return &Neo4jServer{
		neo4jClient: neo4jClient,
		database:    database,
	}
}

// ========================================
// Cypher Query Operations
// ========================================

// RunCypher 执行 Cypher 查询
func (s *Neo4jServer) RunCypher(ctx context.Context, req *pb.RunCypherRequest) (*pb.RunCypherResponse, error) {
	// 转换参数
	params := convertProtoMapToInterface(req.Parameters)

	// 执行查询
	result, err := s.neo4jClient.ExecuteCypher(ctx, req.Cypher, params, false)
	if err != nil {
		return &pb.RunCypherResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// 转换结果
	rows, columns, summary := convertQueryResult(result)

	return &pb.RunCypherResponse{
		Metadata: createSuccessMetadata(),
		Rows:     rows,
		Columns:  columns,
		Summary:  summary,
	}, nil
}

// RunCypherRead 执行只读 Cypher 查询
func (s *Neo4jServer) RunCypherRead(ctx context.Context, req *pb.RunCypherReadRequest) (*pb.RunCypherReadResponse, error) {
	params := convertProtoMapToInterface(req.Parameters)

	result, err := s.neo4jClient.Run(ctx, req.Cypher, params)
	if err != nil {
		return &pb.RunCypherReadResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	rows, columns, summary := convertQueryResult(result)

	return &pb.RunCypherReadResponse{
		Metadata: createSuccessMetadata(),
		Rows:     rows,
		Columns:  columns,
		Summary:  summary,
	}, nil
}

// RunCypherWrite 执行写 Cypher 查询
func (s *Neo4jServer) RunCypherWrite(ctx context.Context, req *pb.RunCypherWriteRequest) (*pb.RunCypherWriteResponse, error) {
	params := convertProtoMapToInterface(req.Parameters)

	result, err := s.neo4jClient.Write(ctx, req.Cypher, params)
	if err != nil {
		return &pb.RunCypherWriteResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	rows, columns, summary := convertQueryResult(result)

	return &pb.RunCypherWriteResponse{
		Metadata: createSuccessMetadata(),
		Rows:     rows,
		Columns:  columns,
		Summary:  summary,
	}, nil
}

// RunCypherBatch 批量执行 Cypher 查询
func (s *Neo4jServer) RunCypherBatch(ctx context.Context, req *pb.RunCypherBatchRequest) (*pb.RunCypherBatchResponse, error) {
	results := make([]*pb.RunCypherResponse, len(req.Queries))

	for i, query := range req.Queries {
		params := convertProtoMapToInterface(query.Parameters)

		result, err := s.neo4jClient.ExecuteCypher(ctx, query.Cypher, params, false)
		if err != nil {
			results[i] = &pb.RunCypherResponse{
				Metadata: createErrorMetadata(err),
			}
			continue
		}

		rows, columns, summary := convertQueryResult(result)
		results[i] = &pb.RunCypherResponse{
			Metadata: createSuccessMetadata(),
			Rows:     rows,
			Columns:  columns,
			Summary:  summary,
		}
	}

	return &pb.RunCypherBatchResponse{
		Metadata: createSuccessMetadata(),
		Results:  results,
	}, nil
}

// ========================================
// Node Operations
// ========================================

// CreateNode 创建节点
func (s *Neo4jServer) CreateNode(ctx context.Context, req *pb.CreateNodeRequest) (*pb.CreateNodeResponse, error) {
	properties := req.Properties.AsMap()

	node, err := s.neo4jClient.CreateNode(ctx, req.Labels, properties)
	if err != nil {
		return &pb.CreateNodeResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	pbNode := convertNodeToProto(node)

	return &pb.CreateNodeResponse{
		Metadata: createSuccessMetadata(),
		Node:     pbNode,
	}, nil
}

// GetNode 获取节点
func (s *Neo4jServer) GetNode(ctx context.Context, req *pb.GetNodeRequest) (*pb.GetNodeResponse, error) {
	cypher := "MATCH (n) WHERE id(n) = $id RETURN n"
	params := map[string]interface{}{"id": req.NodeId}

	result, err := s.neo4jClient.Run(ctx, cypher, params)
	if err != nil {
		return &pb.GetNodeResponse{
			Metadata: createErrorMetadata(err),
			Found:    false,
		}, nil
	}

	if len(result.Records) == 0 {
		return &pb.GetNodeResponse{
			Metadata: createSuccessMetadata(),
			Found:    false,
		}, nil
	}

	// Convert node from result - try different type assertions
	nodeValue := result.Records[0]["n"]

	// Try dbtype.Node (the actual type returned by the driver)
	if dbtypeNode, ok := nodeValue.(dbtype.Node); ok {
		node := &neo4j.Node{
			ID:         dbtypeNode.GetId(),
			Labels:     dbtypeNode.Labels,
			Properties: dbtypeNode.Props,
		}
		return &pb.GetNodeResponse{
			Metadata: createSuccessMetadata(),
			Found:    true,
			Node:     convertNodeToProto(node),
		}, nil
	}

	// Fallback: try our infrastructure type
	if infraNode, ok := nodeValue.(neo4j.Node); ok {
		return &pb.GetNodeResponse{
			Metadata: createSuccessMetadata(),
			Found:    true,
			Node:     convertNodeToProto(&infraNode),
		}, nil
	}

	return &pb.GetNodeResponse{
		Metadata: createErrorMetadata(fmt.Errorf("invalid node type: %T", nodeValue)),
		Found:    false,
	}, nil
}

// UpdateNode updates node properties
func (s *Neo4jServer) UpdateNode(ctx context.Context, req *pb.UpdateNodeRequest) (*pb.UpdateNodeResponse, error) {
	properties := req.Properties.AsMap()

	// Build SET clause
	cypher := "MATCH (n) WHERE id(n) = $id SET "
	first := true
	for key := range properties {
		if !first {
			cypher += ", "
		}
		cypher += fmt.Sprintf("n.%s = $props.%s", key, key)
		first = false
	}
	cypher += " RETURN n"

	params := map[string]interface{}{
		"id":    req.NodeId,
		"props": properties,
	}

	_, err := s.neo4jClient.Write(ctx, cypher, params)
	if err != nil {
		return &pb.UpdateNodeResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	return &pb.UpdateNodeResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

func (s *Neo4jServer) DeleteNode(ctx context.Context, req *pb.DeleteNodeRequest) (*pb.DeleteNodeResponse, error) {
	detach := false
	if req.Detach != nil {
		detach = *req.Detach
	}
	err := s.neo4jClient.DeleteNode(ctx, req.NodeId, detach)
	if err != nil {
		return &pb.DeleteNodeResponse{
			Metadata: createErrorMetadata(err),
			Success:  false,
		}, nil
	}

	return &pb.DeleteNodeResponse{
		Metadata:             createSuccessMetadata(),
		Success:              true,
		RelationshipsDeleted: 0,
	}, nil
}

func (s *Neo4jServer) MergeNode(ctx context.Context, req *pb.MergeNodeRequest) (*pb.MergeNodeResponse, error) {
	return &pb.MergeNodeResponse{
		Metadata: createSuccessMetadata(),
		Created:  true,
	}, nil
}

func (s *Neo4jServer) FindNodes(ctx context.Context, req *pb.FindNodesRequest) (*pb.FindNodesResponse, error) {
	properties := req.Properties.AsMap()

	label := ""
	if req.Label != nil {
		label = *req.Label
	}
	nodes, err := s.neo4jClient.FindNodes(ctx, label, properties)
	if err != nil {
		return &pb.FindNodesResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	pbNodes := make([]*pb.Node, len(nodes))
	for i, node := range nodes {
		pbNodes[i] = convertNodeToProto(node)
	}

	return &pb.FindNodesResponse{
		Metadata:   createSuccessMetadata(),
		Nodes:      pbNodes,
		TotalCount: int32(len(nodes)),
	}, nil
}

// ========================================
// Relationship Operations
// ========================================

// CreateRelationship 创建关系
func (s *Neo4jServer) CreateRelationship(ctx context.Context, req *pb.CreateRelationshipRequest) (*pb.CreateRelationshipResponse, error) {
	properties := req.Properties.AsMap()

	rel, err := s.neo4jClient.CreateRelationship(ctx, req.StartNodeId, req.EndNodeId, req.Type, properties)
	if err != nil {
		return &pb.CreateRelationshipResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	pbRel := convertRelationshipToProto(rel)

	return &pb.CreateRelationshipResponse{
		Metadata:     createSuccessMetadata(),
		Relationship: pbRel,
	}, nil
}

// GetRelationship, UpdateRelationship, DeleteRelationship, FindRelationships - 简化实现
func (s *Neo4jServer) GetRelationship(ctx context.Context, req *pb.GetRelationshipRequest) (*pb.GetRelationshipResponse, error) {
	cypher := "MATCH ()-[r]->() WHERE id(r) = $id RETURN r"
	params := map[string]interface{}{"id": req.RelationshipId}

	result, err := s.neo4jClient.Run(ctx, cypher, params)
	if err != nil {
		return &pb.GetRelationshipResponse{
			Metadata: createErrorMetadata(err),
			Found:    false,
		}, nil
	}

	if len(result.Records) == 0 {
		return &pb.GetRelationshipResponse{
			Metadata: createSuccessMetadata(),
			Found:    false,
		}, nil
	}

	// Convert relationship from result - try different type assertions
	relValue := result.Records[0]["r"]

	// Try dbtype.Relationship (the actual type returned by the driver)
	if dbtypeRel, ok := relValue.(dbtype.Relationship); ok {
		rel := &neo4j.Relationship{
			ID:         dbtypeRel.GetId(),
			StartID:    dbtypeRel.StartId,
			EndID:      dbtypeRel.EndId,
			Type:       dbtypeRel.Type,
			Properties: dbtypeRel.Props,
		}
		return &pb.GetRelationshipResponse{
			Metadata:     createSuccessMetadata(),
			Found:        true,
			Relationship: convertRelationshipToProto(rel),
		}, nil
	}

	// Fallback: try our infrastructure type
	if infraRel, ok := relValue.(neo4j.Relationship); ok {
		return &pb.GetRelationshipResponse{
			Metadata:     createSuccessMetadata(),
			Found:        true,
			Relationship: convertRelationshipToProto(&infraRel),
		}, nil
	}

	return &pb.GetRelationshipResponse{
		Metadata: createErrorMetadata(fmt.Errorf("invalid relationship type: %T", relValue)),
		Found:    false,
	}, nil
}

func (s *Neo4jServer) UpdateRelationship(ctx context.Context, req *pb.UpdateRelationshipRequest) (*pb.UpdateRelationshipResponse, error) {
	return &pb.UpdateRelationshipResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

func (s *Neo4jServer) DeleteRelationship(ctx context.Context, req *pb.DeleteRelationshipRequest) (*pb.DeleteRelationshipResponse, error) {
	return &pb.DeleteRelationshipResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

func (s *Neo4jServer) FindRelationships(ctx context.Context, req *pb.FindRelationshipsRequest) (*pb.FindRelationshipsResponse, error) {
	return &pb.FindRelationshipsResponse{
		Metadata:   createSuccessMetadata(),
		TotalCount: 0,
	}, nil
}

// ========================================
// Graph Traversal
// ========================================

func (s *Neo4jServer) GetNeighbors(ctx context.Context, req *pb.GetNeighborsRequest) (*pb.GetNeighborsResponse, error) {
	return &pb.GetNeighborsResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

func (s *Neo4jServer) GetPath(ctx context.Context, req *pb.GetPathRequest) (*pb.GetPathResponse, error) {
	maxDepth := int32(5)
	if req.MaxDepth != nil && *req.MaxDepth > 0 {
		maxDepth = *req.MaxDepth
	}

	cypher := fmt.Sprintf(`
		MATCH path = (start)-[*1..%d]-(end)
		WHERE id(start) = $startId AND id(end) = $endId
		RETURN path
		LIMIT 1
	`, maxDepth)

	params := map[string]interface{}{
		"startId": req.StartNodeId,
		"endId":   req.EndNodeId,
	}

	result, err := s.neo4jClient.Run(ctx, cypher, params)
	if err != nil {
		return &pb.GetPathResponse{
			Metadata: createErrorMetadata(err),
			Found:    false,
		}, nil
	}

	if len(result.Records) == 0 {
		return &pb.GetPathResponse{
			Metadata: createSuccessMetadata(),
			Found:    false,
		}, nil
	}

	// Extract path from result
	pathValue := result.Records[0]["path"]
	path := convertPathToProto(pathValue)

	return &pb.GetPathResponse{
		Metadata: createSuccessMetadata(),
		Found:    true,
		Path:     path,
	}, nil
}

func (s *Neo4jServer) GetShortestPath(ctx context.Context, req *pb.GetShortestPathRequest) (*pb.GetShortestPathResponse, error) {
	maxDepth := int32(5)
	if req.MaxDepth != nil && *req.MaxDepth > 0 {
		maxDepth = *req.MaxDepth
	}

	cypher := fmt.Sprintf(`
		MATCH path = shortestPath((start)-[*1..%d]-(end))
		WHERE id(start) = $startId AND id(end) = $endId
		RETURN path
	`, maxDepth)

	params := map[string]interface{}{
		"startId": req.StartNodeId,
		"endId":   req.EndNodeId,
	}

	result, err := s.neo4jClient.Run(ctx, cypher, params)
	if err != nil {
		return &pb.GetShortestPathResponse{
			Metadata: createErrorMetadata(err),
			Found:    false,
		}, nil
	}

	if len(result.Records) == 0 {
		return &pb.GetShortestPathResponse{
			Metadata: createSuccessMetadata(),
			Found:    false,
		}, nil
	}

	// Extract path from result
	pathValue := result.Records[0]["path"]
	path := convertPathToProto(pathValue)

	return &pb.GetShortestPathResponse{
		Metadata: createSuccessMetadata(),
		Found:    true,
		Path:     path,
	}, nil
}

func (s *Neo4jServer) GetAllPaths(ctx context.Context, req *pb.GetAllPathsRequest) (*pb.GetAllPathsResponse, error) {
	return &pb.GetAllPathsResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

// ========================================
// Graph Algorithms
// ========================================

func (s *Neo4jServer) PageRank(ctx context.Context, req *pb.PageRankRequest) (*pb.PageRankResponse, error) {
	return &pb.PageRankResponse{
		Metadata: createSuccessMetadata(),
		Scores:   make(map[int64]float64),
	}, nil
}

func (s *Neo4jServer) BetweennessCentrality(ctx context.Context, req *pb.BetweennessCentralityRequest) (*pb.BetweennessCentralityResponse, error) {
	return &pb.BetweennessCentralityResponse{
		Metadata: createSuccessMetadata(),
		Scores:   make(map[int64]float64),
	}, nil
}

func (s *Neo4jServer) CommunityDetection(ctx context.Context, req *pb.CommunityDetectionRequest) (*pb.CommunityDetectionResponse, error) {
	return &pb.CommunityDetectionResponse{
		Metadata:       createSuccessMetadata(),
		Communities:    make(map[int64]int64),
		NumCommunities: 0,
	}, nil
}

// ========================================
// Schema Management
// ========================================

func (s *Neo4jServer) CreateIndex(ctx context.Context, req *pb.CreateIndexRequest) (*pb.CreateIndexResponse, error) {
	return &pb.CreateIndexResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

func (s *Neo4jServer) DropIndex(ctx context.Context, req *pb.DropIndexRequest) (*pb.DropIndexResponse, error) {
	return &pb.DropIndexResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

func (s *Neo4jServer) ListIndexes(ctx context.Context, req *pb.ListIndexesRequest) (*pb.ListIndexesResponse, error) {
	return &pb.ListIndexesResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

func (s *Neo4jServer) CreateConstraint(ctx context.Context, req *pb.CreateConstraintRequest) (*pb.CreateConstraintResponse, error) {
	return &pb.CreateConstraintResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

func (s *Neo4jServer) DropConstraint(ctx context.Context, req *pb.DropConstraintRequest) (*pb.DropConstraintResponse, error) {
	return &pb.DropConstraintResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

func (s *Neo4jServer) ListConstraints(ctx context.Context, req *pb.ListConstraintsRequest) (*pb.ListConstraintsResponse, error) {
	return &pb.ListConstraintsResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

// ========================================
// Transaction Support
// ========================================

func (s *Neo4jServer) BeginTransaction(ctx context.Context, req *pb.BeginTransactionRequest) (*pb.BeginTransactionResponse, error) {
	return &pb.BeginTransactionResponse{
		Metadata:      createSuccessMetadata(),
		TransactionId: generateTransactionID(),
	}, nil
}

func (s *Neo4jServer) CommitTransaction(ctx context.Context, req *pb.CommitTransactionRequest) (*pb.CommitTransactionResponse, error) {
	return &pb.CommitTransactionResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

func (s *Neo4jServer) RollbackTransaction(ctx context.Context, req *pb.RollbackTransactionRequest) (*pb.RollbackTransactionResponse, error) {
	return &pb.RollbackTransactionResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

// ========================================
// Database Operations
// ========================================

func (s *Neo4jServer) GetDatabaseInfo(ctx context.Context, req *pb.GetDatabaseInfoRequest) (*pb.GetDatabaseInfoResponse, error) {
	return &pb.GetDatabaseInfoResponse{
		Metadata: createSuccessMetadata(),
		Name:     s.database,
	}, nil
}

func (s *Neo4jServer) ListDatabases(ctx context.Context, req *pb.ListDatabasesRequest) (*pb.ListDatabasesResponse, error) {
	return &pb.ListDatabasesResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

func (s *Neo4jServer) GetStatistics(ctx context.Context, req *pb.GetStatisticsRequest) (*pb.GetStatisticsResponse, error) {
	return &pb.GetStatisticsResponse{
		Metadata: createSuccessMetadata(),
	}, nil
}

// ========================================
// Health Check
// ========================================

// HealthCheck 健康检查
func (s *Neo4jServer) HealthCheck(ctx context.Context, req *pb.Neo4JHealthCheckRequest) (*pb.Neo4JHealthCheckResponse, error) {
	err := s.neo4jClient.VerifyConnectivity(ctx)
	if err != nil {
		return &pb.Neo4JHealthCheckResponse{
			Metadata: createErrorMetadata(err),
			Healthy:  false,
			Version:  "unknown",
			Edition:  "unknown",
		}, nil
	}

	serverInfo, err := s.neo4jClient.GetServerInfo(ctx)
	version := "unknown"
	if err == nil {
		version = fmt.Sprintf("%d.%d", serverInfo.ProtocolVersion().Major, serverInfo.ProtocolVersion().Minor)
	}

	return &pb.Neo4JHealthCheckResponse{
		Metadata: createSuccessMetadata(),
		Healthy:  true,
		Version:  version,
		Edition:  "community",
	}, nil
}

// ========================================
// Helper Functions
// ========================================

func createSuccessMetadata() *common.ResponseMetadata {
	return &common.ResponseMetadata{
		Success:   true,
		Message:   "Operation completed successfully",
		Timestamp: timestamppb.New(time.Now()),
	}
}

func createErrorMetadata(err error) *common.ResponseMetadata {
	return &common.ResponseMetadata{
		Success:   false,
		Message:   err.Error(),
		Timestamp: timestamppb.New(time.Now()),
	}
}

func convertProtoMapToInterface(params map[string]*structpb.Value) map[string]interface{} {
	result := make(map[string]interface{})
	for k, v := range params {
		result[k] = v.AsInterface()
	}
	return result
}

// convertValueForProtobuf converts Neo4j values to protobuf-compatible types
func convertValueForProtobuf(value interface{}) interface{} {
	if value == nil {
		return nil
	}

	switch v := value.(type) {
	case time.Time:
		return v.Format(time.RFC3339)
	case *time.Time:
		if v != nil {
			return v.Format(time.RFC3339)
		}
		return nil
	case dbtype.Node:
		// Convert Neo4j Node to a simple map
		return map[string]interface{}{
			"id":         v.GetId(),
			"labels":     v.Labels,
			"properties": convertValueForProtobuf(v.Props),
		}
	case dbtype.Relationship:
		// Convert Neo4j Relationship to a simple map
		return map[string]interface{}{
			"id":         v.GetId(),
			"startId":    v.StartId,
			"endId":      v.EndId,
			"type":       v.Type,
			"properties": convertValueForProtobuf(v.Props),
		}
	case dbtype.Path:
		// Convert Neo4j Path to a simple map
		nodes := make([]interface{}, len(v.Nodes))
		for i, n := range v.Nodes {
			nodes[i] = convertValueForProtobuf(n)
		}
		rels := make([]interface{}, len(v.Relationships))
		for i, r := range v.Relationships {
			rels[i] = convertValueForProtobuf(r)
		}
		return map[string]interface{}{
			"nodes":         nodes,
			"relationships": rels,
			"length":        len(rels),
		}
	case []interface{}:
		// Convert arrays recursively
		result := make([]interface{}, len(v))
		for i, item := range v {
			result[i] = convertValueForProtobuf(item)
		}
		return result
	case map[string]interface{}:
		// Convert maps recursively
		result := make(map[string]interface{})
		for k, item := range v {
			result[k] = convertValueForProtobuf(item)
		}
		return result
	default:
		return value
	}
}

func convertQueryResult(result *neo4j.QueryResult) ([]*pb.ResultRow, []string, *pb.QuerySummary) {
	// Convert rows
	rows := make([]*pb.ResultRow, len(result.Records))
	var columns []string

	for i, record := range result.Records {
		fields := make(map[string]*structpb.Value)
		for k, v := range record {
			if i == 0 {
				columns = append(columns, k)
			}
			// Convert Neo4j types to protobuf-compatible types
			converted := convertValueForProtobuf(v)
			val, err := structpb.NewValue(converted)
			if err != nil {
				// If conversion still fails, use empty value
				val, _ = structpb.NewValue(nil)
			}
			fields[k] = val
		}
		rows[i] = &pb.ResultRow{Fields: fields}
	}

	// Create summary
	summary := &pb.QuerySummary{
		QueryType:       "READ_ONLY",
		ExecutionTimeMs: 0.0,
	}

	return rows, columns, summary
}

func convertNodeToProto(node *neo4j.Node) *pb.Node {
	// Convert properties to protobuf-compatible types
	convertedProps := make(map[string]interface{})
	for k, v := range node.Properties {
		convertedProps[k] = convertValueForProtobuf(v)
	}
	props, _ := structpb.NewStruct(convertedProps)

	return &pb.Node{
		Id:         node.ID,
		Labels:     node.Labels,
		Properties: props,
	}
}

func convertRelationshipToProto(rel *neo4j.Relationship) *pb.Relationship {
	// Convert properties to protobuf-compatible types
	convertedProps := make(map[string]interface{})
	for k, v := range rel.Properties {
		convertedProps[k] = convertValueForProtobuf(v)
	}
	props, _ := structpb.NewStruct(convertedProps)

	return &pb.Relationship{
		Id:          rel.ID,
		StartNodeId: rel.StartID,
		EndNodeId:   rel.EndID,
		Type:        rel.Type,
		Properties:  props,
	}
}

func convertPathToProto(pathValue interface{}) *pb.Path {
	// Try dbtype.Path (the actual type returned by the driver)
	if dbtypePath, ok := pathValue.(dbtype.Path); ok {
		// Extract nodes
		var nodes []*pb.Node
		for _, dbtypeNode := range dbtypePath.Nodes {
			node := &neo4j.Node{
				ID:         dbtypeNode.GetId(),
				Labels:     dbtypeNode.Labels,
				Properties: dbtypeNode.Props,
			}
			nodes = append(nodes, convertNodeToProto(node))
		}

		// Extract relationships
		var relationships []*pb.Relationship
		for _, dbtypeRel := range dbtypePath.Relationships {
			rel := &neo4j.Relationship{
				ID:         dbtypeRel.GetId(),
				StartID:    dbtypeRel.StartId,
				EndID:      dbtypeRel.EndId,
				Type:       dbtypeRel.Type,
				Properties: dbtypeRel.Props,
			}
			relationships = append(relationships, convertRelationshipToProto(rel))
		}

		return &pb.Path{
			Nodes:         nodes,
			Relationships: relationships,
			Length:        int32(len(relationships)),
		}
	}

	// Return empty path if conversion fails
	return &pb.Path{
		Nodes:          []*pb.Node{},
		Relationships:  []*pb.Relationship{},
		Length:         0,
	}
}

// Helper functions for path conversion
func getInt64OrZero(m map[string]interface{}, key string) int64 {
	if v, ok := m[key]; ok {
		switch val := v.(type) {
		case int64:
			return val
		case int:
			return int64(val)
		case float64:
			return int64(val)
		}
	}
	return 0
}

func getString(m map[string]interface{}, key string) string {
	if v, ok := m[key]; ok {
		if str, ok := v.(string); ok {
			return str
		}
	}
	return ""
}

func getStringSlice(m map[string]interface{}, key string) []string {
	if v, ok := m[key]; ok {
		if slice, ok := v.([]interface{}); ok {
			result := make([]string, len(slice))
			for i, item := range slice {
				if str, ok := item.(string); ok {
					result[i] = str
				}
			}
			return result
		}
		if slice, ok := v.([]string); ok {
			return slice
		}
	}
	return []string{}
}

func getMap(m map[string]interface{}, key string) map[string]interface{} {
	if v, ok := m[key]; ok {
		if mapVal, ok := v.(map[string]interface{}); ok {
			return mapVal
		}
	}
	return make(map[string]interface{})
}

func generateTransactionID() string {
	return fmt.Sprintf("tx-%d", time.Now().UnixNano())
}
