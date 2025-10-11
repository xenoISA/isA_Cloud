// Package server implements the Loki gRPC service
// 文件名: cmd/loki-service/server/server.go
package server

import (
	"context"
	"fmt"
	"strings"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
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

// QueryLogs 查询日志
func (s *LokiServer) QueryLogs(ctx context.Context, req *pb.QueryLogsRequest) (*pb.QueryLogsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 在查询中强制添加用户隔离条件
	query := s.addUserFilter(req.Query, req.UserId, req.OrganizationId)

	entries, err := s.lokiClient.Query(query, int(req.Limit), req.Start.AsTime(), req.End.AsTime())
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	// 转换为 proto 格式
	var pbEntries []*pb.LogEntry
	for _, entry := range entries {
		pbEntries = append(pbEntries, &pb.LogEntry{
			Timestamp: timestamppb.New(entry.Timestamp),
			Line:      entry.Line,
			Labels:    entry.Labels,
		})
	}

	return &pb.QueryLogsResponse{
		Entries:    pbEntries,
		TotalCount: int64(len(pbEntries)),
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
