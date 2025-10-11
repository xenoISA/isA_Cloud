// Package server implements the NATS gRPC service
// 文件名: cmd/nats-service/server/server.go
package server

import (
	"context"
	"fmt"
	"os"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event/nats"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

// NATSServer NATS gRPC 服务实现
type NATSServer struct {
	pb.UnimplementedNATSServiceServer

	natsClient  *nats.Client
	lokiClient  *loki.Client
	authService *AuthService
	config      *event.EventConfig
}

// NewNATSServer 创建 NATS gRPC 服务实例
func NewNATSServer(natsClient *nats.Client, cfg *event.EventConfig) (*NATSServer, error) {
	lokiClient, _ := createLokiClient()

	return &NATSServer{
		natsClient:  natsClient,
		lokiClient:  lokiClient,
		authService: NewAuthService(cfg),
		config:      cfg,
	}, nil
}

// Publish 发布消息
func (s *NATSServer) Publish(ctx context.Context, req *pb.PublishRequest) (*pb.PublishResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 主题隔离
	isolatedSubject := fmt.Sprintf("user.%s.%s", req.UserId, req.Subject)

	err := s.natsClient.Publish(ctx, isolatedSubject, req.Data)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	s.logAudit(req.UserId, "Publish", map[string]string{"subject": req.Subject})

	return &pb.PublishResponse{Success: true}, nil
}

// Subscribe 订阅主题（流式）
func (s *NATSServer) Subscribe(req *pb.SubscribeRequest, stream pb.NATSService_SubscribeServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedSubject := fmt.Sprintf("user.%s.%s", req.UserId, req.Subject)

	_, err := s.natsClient.Subscribe(stream.Context(), isolatedSubject, func(msg *nats.Message) error {
		response := &pb.MessageResponse{
			Subject:   req.Subject,
			Data:      msg.Data,
			Timestamp: timestamppb.Now(),
		}
		return stream.Send(response)
	})

	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	<-stream.Context().Done()
	return nil
}

// HealthCheck 健康检查
func (s *NATSServer) HealthCheck(ctx context.Context, req *pb.NATSHealthCheckRequest) (*pb.NATSHealthCheckResponse, error) {
	err := s.natsClient.Ping(ctx)
	healthy := err == nil

	return &pb.NATSHealthCheckResponse{
		Healthy:          healthy,
		NatsStatus:       getNATSStatus(healthy),
		JetstreamEnabled: true,
		CheckedAt:        timestamppb.Now(),
	}, nil
}

func (s *NATSServer) logAudit(userID, operation string, metadata map[string]string) {
	if s.lokiClient == nil {
		return
	}
	labels := map[string]string{"service": "nats-grpc-service", "user_id": userID, "operation": operation}
	for k, v := range metadata {
		labels[k] = v
	}
	s.lokiClient.PushLog("nats", "info", fmt.Sprintf("User %s: %s", userID, operation), labels)
}

func getNATSStatus(healthy bool) string {
	if healthy {
		return "connected"
	}
	return "disconnected"
}

func createLokiClient() (*loki.Client, error) {
	lokiURL := os.Getenv("LOKI_URL")
	if lokiURL == "" {
		lokiURL = "http://localhost:3100"
	}
	return loki.NewClient(&loki.Config{URL: lokiURL, BatchSize: 100})
}
