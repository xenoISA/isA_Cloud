// Package server implements the MQTT gRPC service
// 文件名: cmd/mqtt-service/server/server.go
package server

import (
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging/mqtt"
)

// MQTTServer MQTT gRPC 服务实现
type MQTTServer struct {
	pb.UnimplementedMQTTServiceServer

	mqttClient  *mqtt.Client
	lokiClient  *loki.Client
	authService *AuthService
	config      *messaging.MessagingConfig
	sessions    map[string]*Session
	mu          sync.RWMutex
}

// Session 用户会话
type Session struct {
	UserID         string
	OrganizationID string
	ConnectedAt    timestamppb.Timestamp
}

// NewMQTTServer 创建 MQTT gRPC 服务实例
func NewMQTTServer(mqttClient *mqtt.Client, cfg *messaging.MessagingConfig) (*MQTTServer, error) {
	lokiClient, err := createLokiClient()
	if err != nil {
		fmt.Printf("Warning: Failed to create Loki client: %v\n", err)
	}

	return &MQTTServer{
		mqttClient:  mqttClient,
		lokiClient:  lokiClient,
		authService: NewAuthService(cfg),
		config:      cfg,
		sessions:    make(map[string]*Session),
	}, nil
}

// Publish 发布消息
func (s *MQTTServer) Publish(ctx context.Context, req *pb.PublishRequest) (*pb.PublishResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 主题隔离: user-{id}/{topic}
	isolatedTopic := fmt.Sprintf("user-%s/%s", req.UserId, req.Topic)

	err := s.mqttClient.Publish(isolatedTopic, req.Payload, byte(req.Qos), req.Retained)
	if err != nil {
		s.logError(req.UserId, "Publish", err)
		return nil, status.Error(codes.Internal, err.Error())
	}

	s.logAudit(req.UserId, "Publish", map[string]string{
		"topic": req.Topic,
		"size":  fmt.Sprintf("%d", len(req.Payload)),
	})

	return &pb.PublishResponse{
		Success:     true,
		MessageId:   generateMessageID(),
		PublishedAt: timestamppb.Now(),
	}, nil
}

// Subscribe 订阅主题（流式）
func (s *MQTTServer) Subscribe(req *pb.SubscribeRequest, stream pb.MQTTService_SubscribeServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedFilter := fmt.Sprintf("user-%s/%s", req.UserId, req.TopicFilter)

	msgChan := make(chan *pb.MessageResponse, 100)

	err := s.mqttClient.Subscribe(isolatedFilter, func(topic string, payload []byte) error {
		originalTopic := strings.TrimPrefix(topic, fmt.Sprintf("user-%s/", req.UserId))

		msg := &pb.MessageResponse{
			Topic:     originalTopic,
			Payload:   payload,
			Timestamp: timestamppb.Now(),
		}

		select {
		case msgChan <- msg:
		case <-stream.Context().Done():
			return stream.Context().Err()
		}

		return nil
	})

	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	// 流式发送消息
	for {
		select {
		case msg := <-msgChan:
			if err := stream.Send(msg); err != nil {
				return err
			}
		case <-stream.Context().Done():
			return nil
		}
	}
}

// HealthCheck 健康检查
func (s *MQTTServer) HealthCheck(ctx context.Context, req *pb.MQTTHealthCheckRequest) (*pb.MQTTHealthCheckResponse, error) {
	healthy := s.mqttClient.IsConnected()

	return &pb.MQTTHealthCheckResponse{
		Healthy:      healthy,
		BrokerStatus: getBrokerStatus(healthy),
		CheckedAt:    timestamppb.Now(),
		Message:      "MQTT broker status checked",
	}, nil
}

func (s *MQTTServer) logAudit(userID, operation string, metadata map[string]string) {
	if s.lokiClient == nil {
		return
	}
	labels := map[string]string{"service": "mqtt-grpc-service", "user_id": userID, "operation": operation}
	for k, v := range metadata {
		labels[k] = v
	}
	s.lokiClient.PushLog("mqtt", "info", fmt.Sprintf("User %s executed %s", userID, operation), labels)
}

func (s *MQTTServer) logError(userID, operation string, err error) {
	if s.lokiClient == nil {
		return
	}
	s.lokiClient.PushLog("mqtt", "error", fmt.Sprintf("Error: %v", err), map[string]string{
		"service": "mqtt-grpc-service", "user_id": userID, "operation": operation,
	})
}

func generateMessageID() string {
	return fmt.Sprintf("msg-%d", time.Now().UnixNano())
}

func getBrokerStatus(connected bool) string {
	if connected {
		return "connected"
	}
	return "disconnected"
}

func createLokiClient() (*loki.Client, error) {
	lokiURL := os.Getenv("LOKI_URL")
	if lokiURL == "" {
		lokiURL = "http://localhost:3100"
	}
	return loki.NewClient(&loki.Config{
		URL:          lokiURL,
		BatchSize:    100,
		StaticLabels: map[string]string{"service": "mqtt-grpc-service"},
	})
}
