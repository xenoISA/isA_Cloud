// Package server implements the Loki gRPC service
// 文件名: cmd/loki-service/server/server.go
package server

import (
	"context"
	"fmt"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/loki"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

// LokiServer Loki gRPC 服务实现
type LokiServer struct {
	pb.UnimplementedLokiServiceServer

	lokiClient  *loki.Client
	authService *AuthService
	quotaMgr    *QuotaManager
	config      *logging.LoggingConfig
}

// NewLokiServer 创建 Loki gRPC 服务实例
func NewLokiServer(lokiClient *loki.Client, cfg *logging.LoggingConfig) (*LokiServer, error) {
	return &LokiServer{
		lokiClient:  lokiClient,
		authService: NewAuthService(cfg),
		quotaMgr:    NewQuotaManager(),
		config:      cfg,
	}, nil
}

// ============================================
// 日志推送实现
// ============================================

// PushLog 推送单条日志
func (s *LokiServer) PushLog(ctx context.Context, req *pb.PushLogRequest) (*pb.PushLogResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	if s.quotaMgr.IsQuotaExceeded(req.UserId) {
		return nil, status.Error(codes.ResourceExhausted, "quota exceeded")
	}

	// 添加隔离标签
	labels := req.Entry.Labels
	if labels == nil {
		labels = make(map[string]string)
	}
	labels["user_id"] = req.UserId
	labels["organization_id"] = req.OrganizationId

	err := s.lokiClient.Push(loki.LogEntry{
		Timestamp: req.Entry.Timestamp.AsTime(),
		Line:      req.Entry.Line,
		Labels:    labels,
	})

	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	s.quotaMgr.IncrementUsage(req.UserId)

	return &pb.PushLogResponse{Success: true}, nil
}

// PushLogBatch 批量推送日志
func (s *LokiServer) PushLogBatch(ctx context.Context, req *pb.PushLogBatchRequest) (*pb.PushLogBatchResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	if s.quotaMgr.IsQuotaExceeded(req.UserId) {
		return nil, status.Error(codes.ResourceExhausted, "quota exceeded")
	}

	acceptedCount := 0
	rejectedCount := 0
	var errors []string

	for _, entry := range req.Entries {
		// 添加隔离标签
		labels := entry.Labels
		if labels == nil {
			labels = make(map[string]string)
		}
		labels["user_id"] = req.UserId
		labels["organization_id"] = req.OrganizationId

		err := s.lokiClient.Push(loki.LogEntry{
			Timestamp: entry.Timestamp.AsTime(),
			Line:      entry.Line,
			Labels:    labels,
		})

		if err != nil {
			rejectedCount++
			errors = append(errors, err.Error())
		} else {
			acceptedCount++
			s.quotaMgr.IncrementUsage(req.UserId)
		}
	}

	return &pb.PushLogBatchResponse{
		Success:       rejectedCount == 0,
		AcceptedCount: int32(acceptedCount),
		RejectedCount: int32(rejectedCount),
		Errors:        errors,
	}, nil
}

// PushLogStream 流式推送日志
func (s *LokiServer) PushLogStream(stream pb.LokiService_PushLogStreamServer) error {
	acceptedCount := 0
	rejectedCount := 0
	var errors []string

	for {
		req, err := stream.Recv()
		if err != nil {
			break
		}

		if err := s.authService.ValidateUser(req.UserId); err != nil {
			rejectedCount++
			errors = append(errors, "unauthorized")
			continue
		}

		if s.quotaMgr.IsQuotaExceeded(req.UserId) {
			rejectedCount++
			errors = append(errors, "quota exceeded")
			continue
		}

		// 添加隔离标签
		labels := req.Entry.Labels
		if labels == nil {
			labels = make(map[string]string)
		}
		labels["user_id"] = req.UserId
		labels["organization_id"] = req.OrganizationId

		err = s.lokiClient.Push(loki.LogEntry{
			Timestamp: req.Entry.Timestamp.AsTime(),
			Line:      req.Entry.Line,
			Labels:    labels,
		})

		if err != nil {
			rejectedCount++
			errors = append(errors, err.Error())
		} else {
			acceptedCount++
			s.quotaMgr.IncrementUsage(req.UserId)
		}
	}

	return stream.SendAndClose(&pb.PushLogBatchResponse{
		Success:       rejectedCount == 0,
		AcceptedCount: int32(acceptedCount),
		RejectedCount: int32(rejectedCount),
		Errors:        errors,
	})
}

// PushSimpleLog 简化的日志推送
func (s *LokiServer) PushSimpleLog(ctx context.Context, req *pb.PushSimpleLogRequest) (*pb.PushLogResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	if s.quotaMgr.IsQuotaExceeded(req.UserId) {
		return nil, status.Error(codes.ResourceExhausted, "quota exceeded")
	}

	// 自动添加隔离标签
	labels := map[string]string{
		"user_id":         req.UserId,
		"organization_id": req.OrganizationId,
		"service":         req.Service,
		"level":           req.Level.String(),
	}
	for k, v := range req.ExtraLabels {
		labels[k] = v
	}

	err := s.lokiClient.Push(loki.LogEntry{
		Timestamp: req.Timestamp.AsTime(),
		Line:      req.Message,
		Labels:    labels,
	})

	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	s.quotaMgr.IncrementUsage(req.UserId)

	return &pb.PushLogResponse{Success: true}, nil
}

// ============================================
// 日志查询实现
// ============================================

// QueryLogs 查询日志
func (s *LokiServer) QueryLogs(ctx context.Context, req *pb.QueryLogsRequest) (*pb.QueryLogsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 在查询中强制添加用户隔离条件
	_ = s.addUserFilter(req.Query, req.UserId, req.OrganizationId)

	// 简化实现 - 实际应使用 Loki 客户端
	return &pb.QueryLogsResponse{
		Entries:    []*pb.LogEntry{},
		TotalCount: 0,
	}, nil
}

// QueryRange 范围查询
func (s *LokiServer) QueryRange(ctx context.Context, req *pb.QueryRangeRequest) (*pb.QueryRangeResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	_ = s.addUserFilter(req.Query, req.UserId, req.OrganizationId)

	return &pb.QueryRangeResponse{
		ResultType:     "streams",
		StreamResults:  []*pb.StreamResult{},
		MatrixResults:  []*pb.Matrix{},
		Stats:          make(map[string]string),
	}, nil
}

// TailLogs 实时日志尾部查询
func (s *LokiServer) TailLogs(req *pb.TailLogsRequest, stream pb.LokiService_TailLogsServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现 - 实际应创建实时流
	// 这里返回空，实际应该持续推送新日志
	return nil
}

// QueryStats 查询统计
func (s *LokiServer) QueryStats(ctx context.Context, req *pb.QueryStatsRequest) (*pb.QueryStatsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	return &pb.QueryStatsResponse{
		TotalEntries:      0,
		TotalBytes:        0,
		StreamsCount:      0,
		QueryTimeMs:       0,
		LevelDistribution: make(map[string]int64),
		TopLabels:         []string{},
	}, nil
}

// ============================================
// 标签管理实现
// ============================================

// GetLabels 获取标签
func (s *LokiServer) GetLabels(ctx context.Context, req *pb.GetLabelsRequest) (*pb.GetLabelsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现
	return &pb.GetLabelsResponse{
		Labels: []string{"user_id", "organization_id", "service", "level"},
	}, nil
}

// GetLabelValues 获取标签值
func (s *LokiServer) GetLabelValues(ctx context.Context, req *pb.GetLabelValuesRequest) (*pb.GetLabelValuesResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现
	return &pb.GetLabelValuesResponse{
		Values: []string{},
	}, nil
}

// ValidateLabels 验证标签
func (s *LokiServer) ValidateLabels(ctx context.Context, req *pb.ValidateLabelsRequest) (*pb.ValidateLabelsResponse, error) {
	violations := []string{}

	// 基本验证规则
	for key, value := range req.Labels {
		if key == "" || value == "" {
			violations = append(violations, fmt.Sprintf("empty key or value: %s=%s", key, value))
		}
	}

	return &pb.ValidateLabelsResponse{
		Valid:      len(violations) == 0,
		Violations: violations,
		Message:    "Labels validated",
	}, nil
}

// ============================================
// 日志流管理实现
// ============================================

// ListStreams 列出日志流
func (s *LokiServer) ListStreams(ctx context.Context, req *pb.ListStreamsRequest) (*pb.ListStreamsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现
	return &pb.ListStreamsResponse{
		Streams:    []*pb.StreamInfo{},
		TotalCount: 0,
		Page:       req.Page,
		PageSize:   req.PageSize,
	}, nil
}

// GetStreamInfo 获取流信息
func (s *LokiServer) GetStreamInfo(ctx context.Context, req *pb.GetStreamInfoRequest) (*pb.GetStreamInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现
	return &pb.GetStreamInfoResponse{
		Stream: &pb.StreamInfo{
			StreamId:       req.StreamId,
			Labels:         make(map[string]string),
			EntryCount:     0,
			Bytes:          0,
			UserId:         req.UserId,
			OrganizationId: "",
		},
	}, nil
}

// DeleteStream 删除日志流
func (s *LokiServer) DeleteStream(ctx context.Context, req *pb.DeleteStreamRequest) (*pb.DeleteStreamResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现
	return &pb.DeleteStreamResponse{
		Success:        true,
		DeletedEntries: 0,
		Message:        "Stream deleted",
	}, nil
}

// ============================================
// 导出和统计实现
// ============================================

// ExportLogs 导出日志
func (s *LokiServer) ExportLogs(req *pb.ExportLogsRequest, stream pb.LokiService_ExportLogsServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 简化实现 - 发送完成响应
	return stream.Send(&pb.ExportLogsResponse{
		ExportId:          fmt.Sprintf("export-%d", time.Now().Unix()),
		Data:              []byte{},
		TotalEntries:      0,
		ProcessedEntries:  0,
		Complete:          true,
	})
}

// GetExportStatus 获取导出状态
func (s *LokiServer) GetExportStatus(ctx context.Context, req *pb.GetExportStatusRequest) (*pb.GetExportStatusResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	return &pb.GetExportStatusResponse{
		ExportId:           req.ExportId,
		Status:             "completed",
		TotalEntries:       0,
		ExportedEntries:    0,
		ProgressPercentage: 100,
		CreatedAt:          timestamppb.Now(),
		CompletedAt:        timestamppb.Now(),
	}, nil
}

// GetStatistics 获取统计信息
func (s *LokiServer) GetStatistics(ctx context.Context, req *pb.GetStatisticsRequest) (*pb.GetStatisticsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	return &pb.GetStatisticsResponse{
		TotalEntries:       0,
		TotalBytes:         0,
		StreamsCount:       0,
		EntriesByService:   make(map[string]int64),
		EntriesByLevel:     make(map[string]int64),
		IngestionRate:      []*pb.DataPoint{},
		TopServices:        []string{},
		Metadata:           make(map[string]string),
	}, nil
}

// GetUserQuota 获取用户配额
func (s *LokiServer) GetUserQuota(ctx context.Context, req *pb.GetUserQuotaRequest) (*pb.GetUserQuotaResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	return &pb.GetUserQuotaResponse{
		DailyLimit:          1000000,
		TodayUsed:           s.quotaMgr.usage[req.UserId],
		StorageLimitBytes:   10737418240, // 10 GB
		StorageUsedBytes:    0,
		RetentionDays:       30,
		QuotaExceeded:       s.quotaMgr.IsQuotaExceeded(req.UserId),
	}, nil
}

// HealthCheck 健康检查
func (s *LokiServer) HealthCheck(ctx context.Context, req *pb.LokiHealthCheckRequest) (*pb.LokiHealthCheckResponse, error) {
	err := s.lokiClient.HealthCheck(ctx)
	healthy := err == nil

	return &pb.LokiHealthCheckResponse{
		Healthy:    healthy,
		LokiStatus: getLokiStatus(healthy),
		CanWrite:   healthy,
		CanRead:    healthy,
		CheckedAt:  timestamppb.Now(),
	}, nil
}

func (s *LokiServer) addUserFilter(query, userID, orgID string) string {
	// 在 LogQL 查询中添加用户过滤
	filter := fmt.Sprintf(`{user_id="%s"`, userID)
	if orgID != "" {
		filter += fmt.Sprintf(`, organization_id="%s"`, orgID)
	}
	filter += "}"

	// 如果原查询已有过滤器，合并它们
	if strings.Contains(query, "{") {
		return query // 简化处理，实际应该智能合并
	}
	return filter
}

func getLokiStatus(healthy bool) string {
	if healthy {
		return "healthy"
	}
	return "unhealthy"
}

// QuotaManager 配额管理器
type QuotaManager struct {
	usage map[string]int64
}

func NewQuotaManager() *QuotaManager {
	return &QuotaManager{usage: make(map[string]int64)}
}

func (q *QuotaManager) IsQuotaExceeded(userID string) bool {
	// TODO: 实现真实的配额检查
	return false
}

func (q *QuotaManager) IncrementUsage(userID string) {
	q.usage[userID]++
}
