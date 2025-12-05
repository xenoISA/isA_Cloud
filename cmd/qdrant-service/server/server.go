// Package server implements the Qdrant gRPC service
// 文件名: cmd/qdrant-service/server/server.go
package server

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/qdrant"
	common "github.com/isa-cloud/isa_cloud/api/proto/common"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/qdrant"
	qdrant_go "github.com/qdrant/go-client/qdrant"
)

// QdrantServer Qdrant gRPC 服务实现
type QdrantServer struct {
	pb.UnimplementedQdrantServiceServer

	qdrantClient *qdrant.Client
}

// NewQdrantServer 创建 Qdrant gRPC 服务实例
func NewQdrantServer(qdrantClient *qdrant.Client) *QdrantServer {
	return &QdrantServer{
		qdrantClient: qdrantClient,
	}
}

// ========================================
// Collection Management
// ========================================

// CreateCollection 创建集合
func (s *QdrantServer) CreateCollection(ctx context.Context, req *pb.CreateCollectionRequest) (*pb.CreateCollectionResponse, error) {
	var vectorSize uint64
	var distance qdrant.Distance

	// 解析向量配置
	switch config := req.VectorsConfig.(type) {
	case *pb.CreateCollectionRequest_VectorParams:
		vectorSize = config.VectorParams.Size
		distance = qdrant.Distance(config.VectorParams.Distance)
	default:
		return nil, status.Error(codes.InvalidArgument, "vector configuration is required")
	}

	// 创建集合
	err := s.qdrantClient.CreateCollection(ctx, req.CollectionName, vectorSize, distance)
	if err != nil {
		return &pb.CreateCollectionResponse{
			Metadata: createErrorMetadata(err),
			Success:  false,
		}, nil
	}

	return &pb.CreateCollectionResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

// ListCollections 列出所有集合
func (s *QdrantServer) ListCollections(ctx context.Context, req *pb.ListCollectionsRequest) (*pb.ListCollectionsResponse, error) {
	collections, err := s.qdrantClient.ListCollections(ctx)
	if err != nil {
		return &pb.ListCollectionsResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	descriptions := make([]*pb.CollectionDescription, len(collections))
	for i, name := range collections {
		descriptions[i] = &pb.CollectionDescription{
			Name: name,
		}
	}

	return &pb.ListCollectionsResponse{
		Metadata:    createSuccessMetadata(),
		Collections: descriptions,
	}, nil
}

// GetCollectionInfo 获取集合信息
func (s *QdrantServer) GetCollectionInfo(ctx context.Context, req *pb.GetCollectionInfoRequest) (*pb.GetCollectionInfoResponse, error) {
	info, err := s.qdrantClient.GetCollectionInfo(ctx, req.CollectionName)
	if err != nil {
		return &pb.GetCollectionInfoResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// 转换为 proto 格式
	pointsCount := uint64(0)
	if info.PointsCount != nil {
		pointsCount = *info.PointsCount
	}
	pbInfo := &pb.CollectionInfo{
		Status:        info.Status.String(),
		PointsCount:   pointsCount,
		SegmentsCount: info.SegmentsCount,
	}

	return &pb.GetCollectionInfoResponse{
		Metadata: createSuccessMetadata(),
		Info:     pbInfo,
	}, nil
}

// DeleteCollection 删除集合
func (s *QdrantServer) DeleteCollection(ctx context.Context, req *pb.DeleteCollectionRequest) (*pb.DeleteCollectionResponse, error) {
	err := s.qdrantClient.DeleteCollection(ctx, req.CollectionName)
	if err != nil {
		return &pb.DeleteCollectionResponse{
			Metadata: createErrorMetadata(err),
			Success:  false,
		}, nil
	}

	return &pb.DeleteCollectionResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

// UpdateCollection 更新集合配置 (简化实现)
func (s *QdrantServer) UpdateCollection(ctx context.Context, req *pb.UpdateCollectionRequest) (*pb.UpdateCollectionResponse, error) {
	return &pb.UpdateCollectionResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

// CreateCollectionAlias 创建集合别名 (简化实现)
func (s *QdrantServer) CreateCollectionAlias(ctx context.Context, req *pb.CreateCollectionAliasRequest) (*pb.CreateCollectionAliasResponse, error) {
	return &pb.CreateCollectionAliasResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

// ========================================
// Point (Vector) Operations
// ========================================

// UpsertPoints 插入或更新向量点
func (s *QdrantServer) UpsertPoints(ctx context.Context, req *pb.UpsertPointsRequest) (*pb.UpsertPointsResponse, error) {
	// 转换 proto points 到内部格式
	points := make([]qdrant.Point, len(req.Points))

	for i, p := range req.Points {
		point := qdrant.Point{}

		// 设置 ID
		switch id := p.Id.(type) {
		case *pb.Point_NumId:
			point.ID = id.NumId
		case *pb.Point_StrId:
			point.ID = id.StrId
		default:
			return nil, status.Error(codes.InvalidArgument, "invalid point ID type")
		}

		// 设置向量
		switch vectors := p.Vectors.(type) {
		case *pb.Point_Vector:
			point.Vector = vectors.Vector.Data
		default:
			return nil, status.Error(codes.InvalidArgument, "multi-vector not yet supported in this implementation")
		}

		// 设置 Payload
		if p.Payload != nil {
			point.Payload = p.Payload.AsMap()
		}

		points[i] = point
	}

	// 执行 upsert
	err := s.qdrantClient.UpsertPoints(ctx, req.CollectionName, points)
	if err != nil {
		return &pb.UpsertPointsResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.UpsertPointsResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

// GetPoints 获取向量点
func (s *QdrantServer) GetPoints(ctx context.Context, req *pb.GetPointsRequest) (*pb.GetPointsResponse, error) {
	// 转换 IDs
	ids := make([]interface{}, len(req.Ids))
	for i, id := range req.Ids {
		switch idType := id.Id.(type) {
		case *pb.PointId_Num:
			ids[i] = idType.Num
		case *pb.PointId_Str:
			ids[i] = idType.Str
		}
	}

	// 获取点
	retrievedPoints, err := s.qdrantClient.GetPoints(ctx, req.CollectionName, ids)
	if err != nil {
		return &pb.GetPointsResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// 转换为 proto 格式
	pbPoints := make([]*pb.Point, len(retrievedPoints))
	for i, rp := range retrievedPoints {
		pbPoint := &pb.Point{}

		// 设置 ID - use type switch to handle ID 0 correctly
		switch idType := rp.Id.PointIdOptions.(type) {
		case *qdrant_go.PointId_Num:
			pbPoint.Id = &pb.Point_NumId{NumId: idType.Num}
		case *qdrant_go.PointId_Uuid:
			pbPoint.Id = &pb.Point_StrId{StrId: idType.Uuid}
		}

		// 设置向量 (如果请求)
		if req.WithVectors != nil && *req.WithVectors {
			if rp.Vectors != nil {
				pbPoint.Vectors = &pb.Point_Vector{
					Vector: &pb.Vector{
						Data: rp.Vectors.GetVector().Data,
					},
				}
			}
		}

		pbPoints[i] = pbPoint
	}

	return &pb.GetPointsResponse{
		Metadata: createSuccessMetadata(),
		Points:   pbPoints,
	}, nil
}

// DeletePoints 删除向量点
func (s *QdrantServer) DeletePoints(ctx context.Context, req *pb.DeletePointsRequest) (*pb.DeletePointsResponse, error) {
	var ids []interface{}

	// 解析选择器
	switch selector := req.Selector.(type) {
	case *pb.DeletePointsRequest_Ids:
		ids = make([]interface{}, len(selector.Ids.Ids))
		for i, id := range selector.Ids.Ids {
			switch idType := id.Id.(type) {
			case *pb.PointId_Num:
				ids[i] = idType.Num
			case *pb.PointId_Str:
				ids[i] = idType.Str
			}
		}
	default:
		return nil, status.Error(codes.Unimplemented, "filter-based deletion not yet implemented")
	}

	// 删除点
	err := s.qdrantClient.DeletePoints(ctx, req.CollectionName, ids)
	if err != nil {
		return &pb.DeletePointsResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.DeletePointsResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

// UpdatePayload 更新Payload
func (s *QdrantServer) UpdatePayload(ctx context.Context, req *pb.UpdatePayloadRequest) (*pb.UpdatePayloadResponse, error) {
	// Extract IDs from selector
	var ids []interface{}
	switch selector := req.Selector.(type) {
	case *pb.UpdatePayloadRequest_Ids:
		ids = make([]interface{}, len(selector.Ids.Ids))
		for i, id := range selector.Ids.Ids {
			switch idType := id.Id.(type) {
			case *pb.PointId_Num:
				ids[i] = idType.Num
			case *pb.PointId_Str:
				ids[i] = idType.Str
			}
		}
	default:
		return nil, status.Error(codes.Unimplemented, "filter-based update not yet implemented")
	}

	// Convert payload
	payload := req.Payload.AsMap()

	// Execute update
	err := s.qdrantClient.UpdatePayload(ctx, req.CollectionName, payload, ids)
	if err != nil {
		return &pb.UpdatePayloadResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.UpdatePayloadResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

func (s *QdrantServer) DeletePayload(ctx context.Context, req *pb.DeletePayloadRequest) (*pb.DeletePayloadResponse, error) {
	// Extract IDs from selector
	var ids []interface{}
	switch selector := req.Selector.(type) {
	case *pb.DeletePayloadRequest_Ids:
		ids = make([]interface{}, len(selector.Ids.Ids))
		for i, id := range selector.Ids.Ids {
			switch idType := id.Id.(type) {
			case *pb.PointId_Num:
				ids[i] = idType.Num
			case *pb.PointId_Str:
				ids[i] = idType.Str
			}
		}
	default:
		return nil, status.Error(codes.Unimplemented, "filter-based deletion not yet implemented")
	}

	// Execute deletion
	err := s.qdrantClient.DeletePayloadFields(ctx, req.CollectionName, req.Keys, ids)
	if err != nil {
		return &pb.DeletePayloadResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.DeletePayloadResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

func (s *QdrantServer) ClearPayload(ctx context.Context, req *pb.ClearPayloadRequest) (*pb.ClearPayloadResponse, error) {
	// Extract IDs from selector
	var ids []interface{}
	switch selector := req.Selector.(type) {
	case *pb.ClearPayloadRequest_Ids:
		ids = make([]interface{}, len(selector.Ids.Ids))
		for i, id := range selector.Ids.Ids {
			switch idType := id.Id.(type) {
			case *pb.PointId_Num:
				ids[i] = idType.Num
			case *pb.PointId_Str:
				ids[i] = idType.Str
			}
		}
	default:
		return nil, status.Error(codes.Unimplemented, "filter-based clear not yet implemented")
	}

	// Execute clear
	err := s.qdrantClient.ClearPayload(ctx, req.CollectionName, ids)
	if err != nil {
		return &pb.ClearPayloadResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.ClearPayloadResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

// ========================================
// Search Operations
// ========================================

// Search 向量搜索
func (s *QdrantServer) Search(ctx context.Context, req *pb.SearchRequest) (*pb.SearchResponse, error) {
	// Prepare search parameters
	var filter *qdrant_go.Filter
	if req.Filter != nil {
		filter = convertFilterFromProto(req.Filter)
	}

	var scoreThreshold *float32
	if req.ScoreThreshold != nil {
		scoreThreshold = req.ScoreThreshold
	}

	var offset *uint64
	if req.Offset != nil {
		offset = req.Offset
	}

	withPayload := req.WithPayload != nil && *req.WithPayload
	withVectors := req.WithVectors != nil && *req.WithVectors

	// Prepare search params (HNSW tuning, etc.)
	var params map[string]interface{}
	if req.Params != nil {
		params = req.Params.AsMap()
	}

	// Execute search with all options
	scoredPoints, err := s.qdrantClient.SearchPointsWithOptions(
		ctx, req.CollectionName, req.Vector.Data, req.Limit,
		filter, scoreThreshold, offset, withPayload, withVectors, params,
	)
	if err != nil {
		return &pb.SearchResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// Convert to proto format
	pbScoredPoints := convertScoredPointsToProto(scoredPoints, withPayload, withVectors)

	return &pb.SearchResponse{
		Metadata: createSuccessMetadata(),
		Result:   pbScoredPoints,
	}, nil
}

// SearchBatch 批量向量搜索
func (s *QdrantServer) SearchBatch(ctx context.Context, req *pb.SearchBatchRequest) (*pb.SearchBatchResponse, error) {
	results := make([]*pb.SearchResponse, len(req.Searches))

	// Execute each search request
	for i, searchReq := range req.Searches {
		result, err := s.Search(ctx, searchReq)
		if err != nil {
			return &pb.SearchBatchResponse{
				Metadata: createErrorMetadata(err),
			}, nil
		}
		results[i] = result
	}

	return &pb.SearchBatchResponse{
		Metadata: createSuccessMetadata(),
		Results:  results,
	}, nil
}

// Recommend 推荐搜索
func (s *QdrantServer) Recommend(ctx context.Context, req *pb.RecommendRequest) (*pb.RecommendResponse, error) {
	// Convert positive IDs
	positive := make([]interface{}, len(req.Positive))
	for i, id := range req.Positive {
		switch idType := id.Id.(type) {
		case *pb.PointId_Num:
			positive[i] = idType.Num
		case *pb.PointId_Str:
			positive[i] = idType.Str
		}
	}

	// Convert negative IDs
	negative := make([]interface{}, len(req.Negative))
	for i, id := range req.Negative {
		switch idType := id.Id.(type) {
		case *pb.PointId_Num:
			negative[i] = idType.Num
		case *pb.PointId_Str:
			negative[i] = idType.Str
		}
	}

	// Prepare filter
	var filter *qdrant_go.Filter
	if req.Filter != nil {
		filter = convertFilterFromProto(req.Filter)
	}

	withPayload := req.WithPayload != nil && *req.WithPayload
	withVectors := req.WithVectors != nil && *req.WithVectors

	// Execute recommend
	scoredPoints, err := s.qdrantClient.RecommendPoints(
		ctx, req.CollectionName, positive, negative, req.Limit,
		filter, withPayload, withVectors,
	)
	if err != nil {
		return &pb.RecommendResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// Convert to proto format
	pbScoredPoints := convertScoredPointsToProto(scoredPoints, withPayload, withVectors)

	return &pb.RecommendResponse{
		Metadata: createSuccessMetadata(),
		Result:   pbScoredPoints,
	}, nil
}

// Discover 发现搜索 (暂未完整实现)
func (s *QdrantServer) Discover(ctx context.Context, req *pb.DiscoverRequest) (*pb.DiscoverResponse, error) {
	// Note: Discover requires more complex implementation with context pairs
	// This is a simplified stub that returns empty results
	return &pb.DiscoverResponse{
		Metadata: createSuccessMetadata(),
		Result:   []*pb.ScoredPoint{},
	}, nil
}

// Scroll 遍历所有点
func (s *QdrantServer) Scroll(ctx context.Context, req *pb.ScrollRequest) (*pb.ScrollResponse, error) {
	// Prepare filter
	var filter *qdrant_go.Filter
	if req.Filter != nil {
		filter = convertFilterFromProto(req.Filter)
	}

	// Prepare offset
	var offset *qdrant_go.PointId
	if req.Offset != nil {
		offset = &qdrant_go.PointId{}
		switch idType := req.Offset.Id.(type) {
		case *pb.PointId_Num:
			offset.PointIdOptions = &qdrant_go.PointId_Num{Num: idType.Num}
		case *pb.PointId_Str:
			offset.PointIdOptions = &qdrant_go.PointId_Uuid{Uuid: idType.Str}
		}
	}

	limit := uint32(100) // default
	if req.Limit != nil {
		limit = *req.Limit
	}

	withPayload := req.WithPayload != nil && *req.WithPayload
	withVectors := req.WithVectors != nil && *req.WithVectors

	// Execute scroll
	points, nextOffset, err := s.qdrantClient.Scroll(
		ctx, req.CollectionName, filter, limit, offset, withPayload, withVectors,
	)
	if err != nil {
		return &pb.ScrollResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// Convert to proto format
	pbPoints := make([]*pb.Point, len(points))
	for i, rp := range points {
		pbPoint := &pb.Point{}

		// Set ID - use type switch to correctly handle ID 0
		switch idType := rp.Id.PointIdOptions.(type) {
		case *qdrant_go.PointId_Num:
			pbPoint.Id = &pb.Point_NumId{NumId: idType.Num}
		case *qdrant_go.PointId_Uuid:
			pbPoint.Id = &pb.Point_StrId{StrId: idType.Uuid}
		}

		// Set vectors if requested
		if withVectors && rp.Vectors != nil {
			pbPoint.Vectors = &pb.Point_Vector{
				Vector: &pb.Vector{
					Data: rp.Vectors.GetVector().Data,
				},
			}
		}

		// Set payload if requested
		if withPayload && rp.Payload != nil {
			payloadMap := make(map[string]interface{})
			for k, v := range rp.Payload {
				payloadMap[k] = convertQdrantValueToInterface(v)
			}
			payload, _ := structpb.NewStruct(payloadMap)
			pbPoint.Payload = payload
		}

		pbPoints[i] = pbPoint
	}

	// Convert next offset - use type switch to handle ID 0 correctly
	var pbNextOffset *pb.PointId
	if nextOffset != nil {
		pbNextOffset = &pb.PointId{}
		switch idType := nextOffset.PointIdOptions.(type) {
		case *qdrant_go.PointId_Num:
			pbNextOffset.Id = &pb.PointId_Num{Num: idType.Num}
		case *qdrant_go.PointId_Uuid:
			pbNextOffset.Id = &pb.PointId_Str{Str: idType.Uuid}
		}
	}

	return &pb.ScrollResponse{
		Metadata:       createSuccessMetadata(),
		Points:         pbPoints,
		NextPageOffset: pbNextOffset,
	}, nil
}

// Count 统计向量数量
func (s *QdrantServer) Count(ctx context.Context, req *pb.CountRequest) (*pb.CountResponse, error) {
	count, err := s.qdrantClient.CountPoints(ctx, req.CollectionName)
	if err != nil {
		return &pb.CountResponse{
			Metadata: createErrorMetadata(err),
			Count:    0,
		}, nil
	}

	return &pb.CountResponse{
		Metadata: createSuccessMetadata(),
		Count:    count,
	}, nil
}

// ========================================
// Index Management
// ========================================

func (s *QdrantServer) CreateFieldIndex(ctx context.Context, req *pb.CreateFieldIndexRequest) (*pb.CreateFieldIndexResponse, error) {
	// Map field type string to Qdrant enum
	var fieldType qdrant_go.FieldType
	if req.FieldType != nil {
		switch *req.FieldType {
		case "keyword":
			fieldType = qdrant_go.FieldType_FieldTypeKeyword
		case "integer":
			fieldType = qdrant_go.FieldType_FieldTypeInteger
		case "float":
			fieldType = qdrant_go.FieldType_FieldTypeFloat
		case "geo":
			fieldType = qdrant_go.FieldType_FieldTypeGeo
		case "text":
			fieldType = qdrant_go.FieldType_FieldTypeText
		default:
			fieldType = qdrant_go.FieldType_FieldTypeKeyword
		}
	} else {
		fieldType = qdrant_go.FieldType_FieldTypeKeyword
	}

	err := s.qdrantClient.CreateFieldIndex(ctx, req.CollectionName, req.FieldName, fieldType)
	if err != nil {
		return &pb.CreateFieldIndexResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.CreateFieldIndexResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

func (s *QdrantServer) DeleteFieldIndex(ctx context.Context, req *pb.DeleteFieldIndexRequest) (*pb.DeleteFieldIndexResponse, error) {
	err := s.qdrantClient.DeleteFieldIndex(ctx, req.CollectionName, req.FieldName)
	if err != nil {
		return &pb.DeleteFieldIndexResponse{
			Metadata:    createErrorMetadata(err),
			OperationId: "",
			Status:      "failed",
		}, nil
	}

	return &pb.DeleteFieldIndexResponse{
		Metadata:    createSuccessMetadata(),
		OperationId: generateOperationID(),
		Status:      "completed",
	}, nil
}

// ========================================
// Snapshot Operations
// ========================================

func (s *QdrantServer) CreateSnapshot(ctx context.Context, req *pb.CreateSnapshotRequest) (*pb.CreateSnapshotResponse, error) {
	snapshotName, err := s.qdrantClient.CreateSnapshot(ctx, req.CollectionName)
	if err != nil {
		return &pb.CreateSnapshotResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	return &pb.CreateSnapshotResponse{
		Metadata:     createSuccessMetadata(),
		SnapshotName: snapshotName,
		CreatedAt:    timestamppb.Now(),
	}, nil
}

func (s *QdrantServer) ListSnapshots(ctx context.Context, req *pb.ListSnapshotsRequest) (*pb.ListSnapshotsResponse, error) {
	snapshots, err := s.qdrantClient.ListSnapshots(ctx, req.CollectionName)
	if err != nil {
		return &pb.ListSnapshotsResponse{
			Metadata: createErrorMetadata(err),
		}, nil
	}

	// Convert to proto format
	pbSnapshots := make([]*pb.SnapshotDescription, len(snapshots))
	for i, snap := range snapshots {
		pbSnapshots[i] = &pb.SnapshotDescription{
			Name:      snap.Name,
			CreatedAt: timestamppb.New(snap.CreationTime.AsTime()),
			SizeBytes: uint64(snap.Size),
		}
	}

	return &pb.ListSnapshotsResponse{
		Metadata:  createSuccessMetadata(),
		Snapshots: pbSnapshots,
	}, nil
}

func (s *QdrantServer) DeleteSnapshot(ctx context.Context, req *pb.DeleteSnapshotRequest) (*pb.DeleteSnapshotResponse, error) {
	err := s.qdrantClient.DeleteSnapshot(ctx, req.CollectionName, req.SnapshotName)
	if err != nil {
		return &pb.DeleteSnapshotResponse{
			Metadata: createErrorMetadata(err),
			Success:  false,
		}, nil
	}

	return &pb.DeleteSnapshotResponse{
		Metadata: createSuccessMetadata(),
		Success:  true,
	}, nil
}

// ========================================
// Health & Stats
// ========================================

// HealthCheck 健康检查
func (s *QdrantServer) HealthCheck(ctx context.Context, req *pb.QdrantHealthCheckRequest) (*pb.QdrantHealthCheckResponse, error) {
	err := s.qdrantClient.HealthCheck(ctx)
	if err != nil {
		return &pb.QdrantHealthCheckResponse{
			Metadata: createErrorMetadata(err),
			Healthy:  false,
			Version:  "unknown",
		}, nil
	}

	return &pb.QdrantHealthCheckResponse{
		Metadata: createSuccessMetadata(),
		Healthy:  true,
		Version:  "1.x",
	}, nil
}

// GetClusterInfo 获取集群信息
func (s *QdrantServer) GetClusterInfo(ctx context.Context, req *pb.GetClusterInfoRequest) (*pb.GetClusterInfoResponse, error) {
	return &pb.GetClusterInfoResponse{
		Metadata: createSuccessMetadata(),
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

func generateOperationID() string {
	return fmt.Sprintf("op-%d", time.Now().UnixNano())
}

// convertQdrantValueToInterface converts Qdrant Value to Go interface
func convertQdrantValueToInterface(v *qdrant_go.Value) interface{} {
	if v == nil {
		return nil
	}

	switch kind := v.Kind.(type) {
	case *qdrant_go.Value_IntegerValue:
		return kind.IntegerValue
	case *qdrant_go.Value_DoubleValue:
		return kind.DoubleValue
	case *qdrant_go.Value_StringValue:
		return kind.StringValue
	case *qdrant_go.Value_BoolValue:
		return kind.BoolValue
	case *qdrant_go.Value_ListValue:
		result := make([]interface{}, len(kind.ListValue.Values))
		for i, val := range kind.ListValue.Values {
			result[i] = convertQdrantValueToInterface(val)
		}
		return result
	case *qdrant_go.Value_StructValue:
		result := make(map[string]interface{})
		for k, val := range kind.StructValue.Fields {
			result[k] = convertQdrantValueToInterface(val)
		}
		return result
	default:
		return nil
	}
}

// convertFilterFromProto converts proto Filter to Qdrant Filter
func convertFilterFromProto(protoFilter *pb.Filter) *qdrant_go.Filter {
	if protoFilter == nil {
		return nil
	}

	filter := &qdrant_go.Filter{}

	// Convert must conditions
	if len(protoFilter.Must) > 0 {
		filter.Must = make([]*qdrant_go.Condition, len(protoFilter.Must))
		for i, cond := range protoFilter.Must {
			filter.Must[i] = convertConditionFromProto(cond)
		}
	}

	// Convert should conditions
	if len(protoFilter.Should) > 0 {
		filter.Should = make([]*qdrant_go.Condition, len(protoFilter.Should))
		for i, cond := range protoFilter.Should {
			filter.Should[i] = convertConditionFromProto(cond)
		}
	}

	// Convert must_not conditions
	if len(protoFilter.MustNot) > 0 {
		filter.MustNot = make([]*qdrant_go.Condition, len(protoFilter.MustNot))
		for i, cond := range protoFilter.MustNot {
			filter.MustNot[i] = convertConditionFromProto(cond)
		}
	}

	return filter
}

// convertConditionFromProto converts proto FilterCondition to Qdrant Condition
func convertConditionFromProto(protoCond *pb.FilterCondition) *qdrant_go.Condition {
	if protoCond == nil {
		return nil
	}

	condition := &qdrant_go.Condition{
		ConditionOneOf: &qdrant_go.Condition_Field{
			Field: &qdrant_go.FieldCondition{
				Key: protoCond.Field,
			},
		},
	}

	fieldCond := condition.ConditionOneOf.(*qdrant_go.Condition_Field).Field

	// Convert condition types
	switch cond := protoCond.Condition.(type) {
	case *pb.FilterCondition_Match:
		match := &qdrant_go.Match{}
		switch matchVal := cond.Match.MatchValue.(type) {
		case *pb.MatchCondition_Keyword:
			match.MatchValue = &qdrant_go.Match_Keyword{Keyword: matchVal.Keyword}
		case *pb.MatchCondition_Integer:
			match.MatchValue = &qdrant_go.Match_Integer{Integer: matchVal.Integer}
		case *pb.MatchCondition_Boolean:
			match.MatchValue = &qdrant_go.Match_Boolean{Boolean: matchVal.Boolean}
		}
		fieldCond.Match = match

	case *pb.FilterCondition_Range:
		rangeCondition := &qdrant_go.Range{}
		if cond.Range.Gt != nil {
			rangeCondition.Gt = cond.Range.Gt
		}
		if cond.Range.Gte != nil {
			rangeCondition.Gte = cond.Range.Gte
		}
		if cond.Range.Lt != nil {
			rangeCondition.Lt = cond.Range.Lt
		}
		if cond.Range.Lte != nil {
			rangeCondition.Lte = cond.Range.Lte
		}
		fieldCond.Range = rangeCondition

	case *pb.FilterCondition_GeoBoundingBox:
		fieldCond.GeoBoundingBox = &qdrant_go.GeoBoundingBox{
			TopLeft: &qdrant_go.GeoPoint{
				Lat: cond.GeoBoundingBox.TopLeft.Lat,
				Lon: cond.GeoBoundingBox.TopLeft.Lon,
			},
			BottomRight: &qdrant_go.GeoPoint{
				Lat: cond.GeoBoundingBox.BottomRight.Lat,
				Lon: cond.GeoBoundingBox.BottomRight.Lon,
			},
		}

	case *pb.FilterCondition_GeoRadius:
		fieldCond.GeoRadius = &qdrant_go.GeoRadius{
			Center: &qdrant_go.GeoPoint{
				Lat: cond.GeoRadius.Center.Lat,
				Lon: cond.GeoRadius.Center.Lon,
			},
			Radius: float32(cond.GeoRadius.RadiusMeters),
		}

	case *pb.FilterCondition_ValuesCount:
		valuesCount := &qdrant_go.ValuesCount{}
		if cond.ValuesCount.Lt != nil {
			lt := *cond.ValuesCount.Lt
			valuesCount.Lt = &lt
		}
		if cond.ValuesCount.Lte != nil {
			lte := *cond.ValuesCount.Lte
			valuesCount.Lte = &lte
		}
		if cond.ValuesCount.Gt != nil {
			gt := *cond.ValuesCount.Gt
			valuesCount.Gt = &gt
		}
		if cond.ValuesCount.Gte != nil {
			gte := *cond.ValuesCount.Gte
			valuesCount.Gte = &gte
		}
		fieldCond.ValuesCount = valuesCount
	}

	return condition
}

// convertScoredPointsToProto converts Qdrant ScoredPoints to proto format
func convertScoredPointsToProto(scoredPoints []*qdrant_go.ScoredPoint, withPayload bool, withVectors bool) []*pb.ScoredPoint {
	pbScoredPoints := make([]*pb.ScoredPoint, len(scoredPoints))

	for i, sp := range scoredPoints {
		pbPoint := &pb.Point{}

		// Set ID - use type switch to handle ID 0 correctly
		switch idType := sp.Id.PointIdOptions.(type) {
		case *qdrant_go.PointId_Num:
			pbPoint.Id = &pb.Point_NumId{NumId: idType.Num}
		case *qdrant_go.PointId_Uuid:
			pbPoint.Id = &pb.Point_StrId{StrId: idType.Uuid}
		}

		// Set vectors if requested
		if withVectors && sp.Vectors != nil {
			pbPoint.Vectors = &pb.Point_Vector{
				Vector: &pb.Vector{
					Data: sp.Vectors.GetVector().Data,
				},
			}
		}

		// Set payload if requested
		if withPayload && sp.Payload != nil {
			payloadMap := make(map[string]interface{})
			for k, v := range sp.Payload {
				payloadMap[k] = convertQdrantValueToInterface(v)
			}
			payload, _ := structpb.NewStruct(payloadMap)
			pbPoint.Payload = payload
		}

		pbScoredPoints[i] = &pb.ScoredPoint{
			Point: pbPoint,
			Score: sp.Score,
		}
	}

	return pbScoredPoints
}
