// Package server implements the Supabase gRPC service
// 文件名: cmd/supabase-service/server/server.go
package server

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/isa-cloud/isa_cloud/api/proto"
	pb "github.com/isa-cloud/isa_cloud/api/proto/supabase"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/supabase"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

// SupabaseServer Supabase gRPC 服务实现
type SupabaseServer struct {
	pb.UnimplementedSupabaseServiceServer

	supabaseClient *supabase.Client
	authService    *AuthService
	config         *storage.StorageConfig
}

// NewSupabaseServer 创建 Supabase gRPC 服务实例
func NewSupabaseServer(client *supabase.Client, cfg *storage.StorageConfig) (*SupabaseServer, error) {
	return &SupabaseServer{
		supabaseClient: client,
		authService:    NewAuthService(cfg),
		config:         cfg,
	}, nil
}

// sanitizeDataForProtobuf 清理数据以便转换为 protobuf Struct
// 主要处理 time.Time 等不支持的类型
func sanitizeDataForProtobuf(data map[string]interface{}) map[string]interface{} {
	result := make(map[string]interface{})
	for k, v := range data {
		switch val := v.(type) {
		case time.Time:
			// 转换 time.Time 为 RFC3339 字符串
			result[k] = val.Format(time.RFC3339)
		case *time.Time:
			if val != nil {
				result[k] = val.Format(time.RFC3339)
			} else {
				result[k] = nil
			}
		case []byte:
			// 转换字节数组为字符串
			result[k] = string(val)
		default:
			result[k] = v
		}
	}
	return result
}

// ========================================
// 数据库操作实现
// ========================================

// Query 查询数据
func (s *SupabaseServer) Query(ctx context.Context, req *pb.QueryRequest) (*pb.QueryResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 构建查询选项
	opts := &supabase.QueryOptions{
		Select: req.Select,
		Filter: req.Filter,
		Order:  req.Order,
		Limit:  req.Limit,
		Offset: req.Offset,
		Count:  req.Count,
	}

	// 多租户隔离 - 添加用户过滤
	if opts.Filter != "" {
		opts.Filter = fmt.Sprintf("%s,user_id.eq.%s", opts.Filter, userID)
	} else {
		opts.Filter = fmt.Sprintf("user_id.eq.%s", userID)
	}

	// 执行查询
	results, err := s.supabaseClient.Query(ctx, req.Table, opts)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("query failed: %v", err))
	}

	// 转换为 protobuf Struct
	var dataStructs []*structpb.Struct
	for _, row := range results {
		sanitized := sanitizeDataForProtobuf(row)
		s, err := structpb.NewStruct(sanitized)
		if err != nil {
			return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert data: %v", err))
		}
		dataStructs = append(dataStructs, s)
	}

	return &pb.QueryResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Data:  dataStructs,
		Count: int32(len(results)),
	}, nil
}

// Insert 插入数据
func (s *SupabaseServer) Insert(ctx context.Context, req *pb.InsertRequest) (*pb.InsertResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换数据并添加 user_id
	var data []map[string]interface{}
	for _, item := range req.Data {
		row := item.AsMap()
		row["user_id"] = userID // 多租户隔离
		data = append(data, row)
	}

	// 执行插入
	insertedData, err := s.supabaseClient.Insert(ctx, req.Table, data)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("insert failed: %v", err))
	}

	// 转换响应
	var dataStructs []*structpb.Struct
	if req.ReturnData {
		for _, row := range insertedData {
			sanitized := sanitizeDataForProtobuf(row)
			s, err := structpb.NewStruct(sanitized)
			if err != nil {
				return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert data: %v", err))
			}
			dataStructs = append(dataStructs, s)
		}
	}

	return &pb.InsertResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Data:  dataStructs,
		Count: int32(len(data)),
	}, nil
}

// Update 更新数据
func (s *SupabaseServer) Update(ctx context.Context, req *pb.UpdateRequest) (*pb.UpdateResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换数据
	data := req.Data.AsMap()

	// 多租户隔离 - 添加用户过滤
	filter := req.Filter
	if filter != "" {
		filter = fmt.Sprintf("%s,user_id.eq.%s", filter, userID)
	} else {
		filter = fmt.Sprintf("user_id.eq.%s", userID)
	}

	// 执行更新
	updatedData, err := s.supabaseClient.Update(ctx, req.Table, data, filter)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("update failed: %v", err))
	}

	// 转换响应
	var dataStructs []*structpb.Struct
	if req.ReturnData {
		for _, row := range updatedData {
			sanitized := sanitizeDataForProtobuf(row)
			s, err := structpb.NewStruct(sanitized)
			if err != nil {
				return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert data: %v", err))
			}
			dataStructs = append(dataStructs, s)
		}
	}

	return &pb.UpdateResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Data:  dataStructs,
		Count: int32(len(updatedData)),
	}, nil
}

// Delete 删除数据
func (s *SupabaseServer) Delete(ctx context.Context, req *pb.DeleteRequest) (*pb.DeleteResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 多租户隔离 - 添加用户过滤
	filter := req.Filter
	if filter != "" {
		filter = fmt.Sprintf("%s,user_id.eq.%s", filter, userID)
	} else {
		filter = fmt.Sprintf("user_id.eq.%s", userID)
	}

	// 执行删除
	deletedData, err := s.supabaseClient.Delete(ctx, req.Table, filter)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("delete failed: %v", err))
	}

	// 转换响应
	var dataStructs []*structpb.Struct
	if req.ReturnData {
		for _, row := range deletedData {
			sanitized := sanitizeDataForProtobuf(row)
			s, err := structpb.NewStruct(sanitized)
			if err != nil {
				return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert data: %v", err))
			}
			dataStructs = append(dataStructs, s)
		}
	}

	return &pb.DeleteResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Data:  dataStructs,
		Count: int32(len(deletedData)),
	}, nil
}

// Upsert 插入或更新数据
func (s *SupabaseServer) Upsert(ctx context.Context, req *pb.UpsertRequest) (*pb.UpsertResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换数据并添加 user_id
	var data []map[string]interface{}
	for _, item := range req.Data {
		row := item.AsMap()
		row["user_id"] = userID // 多租户隔离
		data = append(data, row)
	}

	// 执行 upsert
	upsertedData, err := s.supabaseClient.Upsert(ctx, req.Table, data, req.OnConflict)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("upsert failed: %v", err))
	}

	// 转换响应
	var dataStructs []*structpb.Struct
	if req.ReturnData {
		for _, row := range upsertedData {
			sanitized := sanitizeDataForProtobuf(row)
			s, err := structpb.NewStruct(sanitized)
			if err != nil {
				return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert data: %v", err))
			}
			dataStructs = append(dataStructs, s)
		}
	}

	return &pb.UpsertResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Data:  dataStructs,
		Count: int32(len(data)),
	}, nil
}

// ExecuteRPC 调用 PostgreSQL 函数
func (s *SupabaseServer) ExecuteRPC(ctx context.Context, req *pb.RPCRequest) (*pb.RPCResponse, error) {
	// 认证检查
	_, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换参数
	params := req.Params.AsMap()

	// 执行 RPC
	result, err := s.supabaseClient.ExecuteRPC(ctx, req.FunctionName, params)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("rpc failed: %v", err))
	}

	// 转换响应
	resultValue, err := structpb.NewValue(result)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert result: %v", err))
	}

	return &pb.RPCResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Data: resultValue,
	}, nil
}

// ========================================
// 向量操作实现
// ========================================

// UpsertEmbedding 插入或更新向量
func (s *SupabaseServer) UpsertEmbedding(ctx context.Context, req *pb.UpsertEmbeddingRequest) (*pb.UpsertEmbeddingResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换向量为 float32
	embedding := make([]float32, len(req.Embedding))
	for i, v := range req.Embedding {
		embedding[i] = v
	}

	// 添加用户隔离
	metadata := req.MetadataJson.AsMap()
	metadata["user_id"] = userID

	// 执行向量插入
	err = s.supabaseClient.UpsertEmbedding(ctx, req.Table, req.Id, embedding, metadata)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("upsert embedding failed: %v", err))
	}

	return &pb.UpsertEmbeddingResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Id:      req.Id,
		Success: true,
	}, nil
}

// SimilaritySearch 向量相似度搜索
func (s *SupabaseServer) SimilaritySearch(ctx context.Context, req *pb.SimilaritySearchRequest) (*pb.SimilaritySearchResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换向量为 float32
	queryEmbedding := make([]float32, len(req.QueryEmbedding))
	for i, v := range req.QueryEmbedding {
		queryEmbedding[i] = v
	}

	// 多租户隔离 - 添加用户过滤
	filter := req.Filter
	if filter != "" {
		filter = fmt.Sprintf("%s,user_id.eq.%s", filter, userID)
	} else {
		filter = fmt.Sprintf("user_id.eq.%s", userID)
	}

	// 构建搜索选项
	opts := &supabase.VectorSearchOptions{
		Table:          req.Table,
		QueryEmbedding: queryEmbedding,
		Limit:          req.Limit,
		Filter:         filter,
		Metric:         req.Metric,
		Threshold:      req.Threshold,
	}

	// 执行搜索
	results, err := s.supabaseClient.SimilaritySearch(ctx, opts)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("similarity search failed: %v", err))
	}

	// 转换响应
	var pbResults []*pb.VectorSearchResult
	for _, result := range results {
		sanitized := sanitizeDataForProtobuf(result.Metadata)
		metadata, err := structpb.NewStruct(sanitized)
		if err != nil {
			return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert metadata: %v", err))
		}

		pbResults = append(pbResults, &pb.VectorSearchResult{
			Id:         result.ID,
			Similarity: result.Similarity,
			Metadata:   metadata,
		})
	}

	return &pb.SimilaritySearchResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Results: pbResults,
	}, nil
}

// HybridSearch 混合搜索 (全文 + 向量)
func (s *SupabaseServer) HybridSearch(ctx context.Context, req *pb.HybridSearchRequest) (*pb.HybridSearchResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换向量为 float32
	vectorQuery := make([]float32, len(req.VectorQuery))
	for i, v := range req.VectorQuery {
		vectorQuery[i] = v
	}

	// 多租户隔离 - 添加用户过滤
	filter := req.Filter
	if filter != "" {
		filter = fmt.Sprintf("%s,user_id.eq.%s", filter, userID)
	} else {
		filter = fmt.Sprintf("user_id.eq.%s", userID)
	}

	// 执行混合搜索
	results, err := s.supabaseClient.HybridSearch(
		ctx,
		req.Table,
		req.TextQuery,
		vectorQuery,
		req.Limit,
		req.TextWeight,
		req.VectorWeight,
		filter,
	)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("hybrid search failed: %v", err))
	}

	// 转换响应
	var pbResults []*pb.VectorSearchResult
	for _, result := range results {
		sanitized := sanitizeDataForProtobuf(result.Metadata)
		metadata, err := structpb.NewStruct(sanitized)
		if err != nil {
			return nil, status.Error(codes.Internal, fmt.Sprintf("failed to convert metadata: %v", err))
		}

		pbResults = append(pbResults, &pb.VectorSearchResult{
			Id:         result.ID,
			Similarity: result.Similarity,
			Metadata:   metadata,
		})
	}

	return &pb.HybridSearchResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Results: pbResults,
	}, nil
}

// DeleteEmbedding 删除向量
func (s *SupabaseServer) DeleteEmbedding(ctx context.Context, req *pb.DeleteEmbeddingRequest) (*pb.DeleteEmbeddingResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 多租户隔离检查 - 先验证该向量属于该用户
	filter := fmt.Sprintf("id.eq.%s,user_id.eq.%s", req.Id, userID)
	queryOpts := &supabase.QueryOptions{
		Select: "id",
		Filter: filter,
		Limit:  1,
	}

	results, err := s.supabaseClient.Query(ctx, req.Table, queryOpts)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("failed to verify ownership: %v", err))
	}

	if len(results) == 0 {
		return nil, status.Error(codes.PermissionDenied, "embedding not found or access denied")
	}

	// 删除向量
	err = s.supabaseClient.DeleteEmbedding(ctx, req.Table, req.Id)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Sprintf("delete embedding failed: %v", err))
	}

	return &pb.DeleteEmbeddingResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Success: true,
	}, nil
}

// ========================================
// 批量操作实现
// ========================================

// BatchInsert 批量插入
func (s *SupabaseServer) BatchInsert(ctx context.Context, req *pb.BatchInsertRequest) (*pb.BatchInsertResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换数据并添加 user_id
	var data []map[string]interface{}
	for _, item := range req.Data {
		row := item.AsMap()
		row["user_id"] = userID // 多租户隔离
		data = append(data, row)
	}

	// 执行批量插入
	batchSize := int(req.BatchSize)
	if batchSize <= 0 {
		batchSize = 100
	}

	count, err := s.supabaseClient.BatchInsert(ctx, req.Table, data, batchSize)
	if err != nil {
		return &pb.BatchInsertResponse{
			Metadata: &proto.ResponseMetadata{
				Success:   false,
				Timestamp: timestamppb.Now(),
				Error:     err.Error(),
			},
			TotalCount:   int32(len(data)),
			SuccessCount: int32(count),
			ErrorCount:   int32(len(data) - count),
			Errors:       []string{err.Error()},
		}, nil
	}

	return &pb.BatchInsertResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		TotalCount:   int32(len(data)),
		SuccessCount: int32(count),
		ErrorCount:   0,
	}, nil
}

// BatchUpsertEmbeddings 批量插入向量
func (s *SupabaseServer) BatchUpsertEmbeddings(ctx context.Context, req *pb.BatchUpsertEmbeddingsRequest) (*pb.BatchUpsertEmbeddingsResponse, error) {
	// 认证检查
	userID, err := s.authService.AuthenticateRequest(ctx, req.Metadata)
	if err != nil {
		return nil, status.Error(codes.Unauthenticated, err.Error())
	}

	// 转换向量数据
	var embeddings []map[string]interface{}
	for _, emb := range req.Embeddings {
		embedding := make([]float32, len(emb.Embedding))
		for i, v := range emb.Embedding {
			embedding[i] = v
		}

		metadata := emb.Metadata.AsMap()
		metadata["user_id"] = userID // 多租户隔离

		embeddings = append(embeddings, map[string]interface{}{
			"id":        emb.Id,
			"embedding": embedding,
			"metadata":  metadata,
		})
	}

	// 执行批量插入
	count, err := s.supabaseClient.BatchUpsertEmbeddings(ctx, req.Table, embeddings)
	if err != nil {
		return &pb.BatchUpsertEmbeddingsResponse{
			Metadata: &proto.ResponseMetadata{
				Success:   false,
				Timestamp: timestamppb.Now(),
				Error:     err.Error(),
			},
			TotalCount:   int32(len(embeddings)),
			SuccessCount: int32(count),
			ErrorCount:   int32(len(embeddings) - count),
			Errors:       []string{err.Error()},
		}, nil
	}

	return &pb.BatchUpsertEmbeddingsResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		TotalCount:   int32(len(embeddings)),
		SuccessCount: int32(count),
		ErrorCount:   0,
	}, nil
}

// ========================================
// 健康检查
// ========================================

// HealthCheck 服务健康检查
func (s *SupabaseServer) HealthCheck(ctx context.Context, req *pb.HealthCheckRequest) (*pb.HealthCheckResponse, error) {
	// 检查 Supabase 连接
	healthy, statusMsg, err := s.supabaseClient.HealthCheck(ctx)
	if err != nil {
		return &pb.HealthCheckResponse{
			Metadata: &proto.ResponseMetadata{
				Success:   false,
				Timestamp: timestamppb.Now(),
				Error:     err.Error(),
			},
			Healthy:        false,
			SupabaseStatus: "unhealthy: " + err.Error(),
		}, nil
	}

	// 获取 PostgreSQL 版本
	pgVersion := "unknown"
	version, err := s.supabaseClient.GetPostgresVersion(ctx)
	if err == nil {
		pgVersion = version
	}

	// 检查 pgvector
	pgvectorEnabled := false
	enabled, err := s.supabaseClient.CheckPgVectorEnabled(ctx)
	if err == nil {
		pgvectorEnabled = enabled
	}

	return &pb.HealthCheckResponse{
		Metadata: &proto.ResponseMetadata{
			Success:   true,
			Timestamp: timestamppb.Now(),
		},
		Healthy:         healthy,
		SupabaseStatus:  statusMsg,
		PostgresVersion: pgVersion,
		PgvectorEnabled: pgvectorEnabled,
	}, nil
}
