// Package server implements the MQTT gRPC service
// 文件名: cmd/mqtt-service/server/server.go
package server

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/mqtt"
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
	devices     map[string]*DeviceState
	topics      map[string]*TopicState
	retained    map[string]*pb.MQTTMessage
	webhooks    map[string]*WebhookState  // 新增：webhook 管理
	mu          sync.RWMutex
}

// WebhookState Webhook 状态
type WebhookState struct {
	WebhookID       string
	UserID          string
	OrganizationID  string
	URL             string
	MessageTypes    []pb.DeviceMessageType
	DeviceIDs       []string
	TopicPatterns   []string
	Headers         map[string]string
	Secret          string
	Enabled         bool
	CreatedAt       time.Time
	UpdatedAt       time.Time
	SuccessCount    int64
	FailureCount    int64
	cancelFunc      context.CancelFunc  // 用于停止 webhook
}

// Session 用户会话
type Session struct {
	UserID         string
	OrganizationID string
	ClientID       string
	ConnectedAt    time.Time
	MessagesSent   int64
	MessagesRecv   int64
	Subscriptions  []string
}

// DeviceState 设备状态
type DeviceState struct {
	DeviceID       string
	DeviceName     string
	DeviceType     string
	UserID         string
	OrganizationID string
	Status         pb.DeviceStatus
	RegisteredAt   time.Time
	LastSeen       time.Time
	Metadata       map[string]string
	Topics         []string
	MessagesSent   int64
	MessagesRecv   int64
}

// TopicState 主题状态
type TopicState struct {
	Topic            string
	UserID           string
	OrganizationID   string
	SubscriberCount  int64
	MessageCount     int64
	LastMessageTime  time.Time
	HasRetainedMsg   bool
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
		devices:     make(map[string]*DeviceState),
		topics:      make(map[string]*TopicState),
		retained:    make(map[string]*pb.MQTTMessage),
		webhooks:    make(map[string]*WebhookState),
	}, nil
}

// ========================================
// 连接管理
// ========================================

// Connect 建立连接
func (s *MQTTServer) Connect(ctx context.Context, req *pb.ConnectRequest) (*pb.ConnectResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	sessionID := fmt.Sprintf("session-%s-%d", req.ClientId, time.Now().UnixNano())

	s.mu.Lock()
	s.sessions[sessionID] = &Session{
		UserID:        req.UserId,
		ClientID:      req.ClientId,
		ConnectedAt:   time.Now(),
		Subscriptions: []string{},
	}
	s.mu.Unlock()

	s.logAudit(req.UserId, "Connect", map[string]string{
		"client_id":  req.ClientId,
		"session_id": sessionID,
	})

	return &pb.ConnectResponse{
		Success:        true,
		SessionId:      sessionID,
		Message:        "Connected successfully",
		SessionPresent: false,
	}, nil
}

// Disconnect 断开连接
func (s *MQTTServer) Disconnect(ctx context.Context, req *pb.DisconnectRequest) (*pb.DisconnectResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.Lock()
	delete(s.sessions, req.SessionId)
	s.mu.Unlock()

	s.logAudit(req.UserId, "Disconnect", map[string]string{
		"session_id": req.SessionId,
	})

	return &pb.DisconnectResponse{
		Success: true,
		Message: "Disconnected successfully",
	}, nil
}

// GetConnectionStatus 获取连接状态
func (s *MQTTServer) GetConnectionStatus(ctx context.Context, req *pb.ConnectionStatusRequest) (*pb.ConnectionStatusResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	session, exists := s.sessions[req.SessionId]
	s.mu.RUnlock()

	if !exists {
		return &pb.ConnectionStatusResponse{
			Connected: false,
		}, nil
	}

	return &pb.ConnectionStatusResponse{
		Connected:        true,
		ConnectedAt:      timestamppb.New(session.ConnectedAt),
		MessagesSent:     session.MessagesSent,
		MessagesReceived: session.MessagesRecv,
	}, nil
}

// Publish 发布消息
func (s *MQTTServer) Publish(ctx context.Context, req *pb.PublishRequest) (*pb.PublishResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 主题隔离: user-{id}/{topic}
	isolatedTopic := fmt.Sprintf("user-%s/%s", req.UserId, req.Topic)

	err := s.mqttClient.PublishWithQoS(isolatedTopic, req.Payload, byte(req.Qos), req.Retained)
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

// PublishBatch 批量发布消息
func (s *MQTTServer) PublishBatch(ctx context.Context, req *pb.PublishBatchRequest) (*pb.PublishBatchResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var publishedCount, failedCount int32
	var messageIDs []string
	var errors []string

	for _, msg := range req.Messages {
		isolatedTopic := fmt.Sprintf("user-%s/%s", req.UserId, msg.Topic)
		err := s.mqttClient.PublishWithQoS(isolatedTopic, msg.Payload, byte(msg.Qos), msg.Retained)

		if err != nil {
			failedCount++
			errors = append(errors, err.Error())
		} else {
			publishedCount++
			messageIDs = append(messageIDs, generateMessageID())
		}
	}

	return &pb.PublishBatchResponse{
		Success:        failedCount == 0,
		PublishedCount: publishedCount,
		FailedCount:    failedCount,
		MessageIds:     messageIDs,
		Errors:         errors,
	}, nil
}

// PublishJSON 发布 JSON 消息
func (s *MQTTServer) PublishJSON(ctx context.Context, req *pb.PublishJSONRequest) (*pb.PublishResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Convert protobuf Struct to JSON bytes
	jsonData, err := req.Data.MarshalJSON()
	if err != nil {
		return nil, status.Error(codes.InvalidArgument, "failed to marshal JSON")
	}

	isolatedTopic := fmt.Sprintf("user-%s/%s", req.UserId, req.Topic)
	err = s.mqttClient.PublishWithQoS(isolatedTopic, jsonData, byte(req.Qos), req.Retained)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

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

// SubscribeMultiple 批量订阅
func (s *MQTTServer) SubscribeMultiple(req *pb.SubscribeMultipleRequest, stream pb.MQTTService_SubscribeMultipleServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	msgChan := make(chan *pb.MessageResponse, 100)

	for _, sub := range req.Subscriptions {
		isolatedFilter := fmt.Sprintf("user-%s/%s", req.UserId, sub.TopicFilter)

		err := s.mqttClient.Subscribe(isolatedFilter, func(topic string, payload []byte) error {
			originalTopic := strings.TrimPrefix(topic, fmt.Sprintf("user-%s/", req.UserId))

			msg := &pb.MessageResponse{
				Topic:     originalTopic,
				Payload:   payload,
				Qos:       sub.Qos,
				Timestamp: timestamppb.Now(),
				MessageId: generateMessageID(),
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

// Unsubscribe 取消订阅
func (s *MQTTServer) Unsubscribe(ctx context.Context, req *pb.UnsubscribeRequest) (*pb.UnsubscribeResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var unsubscribedCount int32
	for _, topicFilter := range req.TopicFilters {
		isolatedFilter := fmt.Sprintf("user-%s/%s", req.UserId, topicFilter)
		err := s.mqttClient.Unsubscribe(isolatedFilter)
		if err == nil {
			unsubscribedCount++
		}
	}

	return &pb.UnsubscribeResponse{
		Success:           true,
		UnsubscribedCount: unsubscribedCount,
		Message:           fmt.Sprintf("Unsubscribed from %d topics", unsubscribedCount),
	}, nil
}

// ListSubscriptions 列出订阅
func (s *MQTTServer) ListSubscriptions(ctx context.Context, req *pb.ListSubscriptionsRequest) (*pb.ListSubscriptionsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	session, exists := s.sessions[req.SessionId]
	s.mu.RUnlock()

	if !exists {
		return &pb.ListSubscriptionsResponse{
			Subscriptions: []*pb.TopicSubscription{},
		}, nil
	}

	var subscriptions []*pb.TopicSubscription
	for _, topic := range session.Subscriptions {
		subscriptions = append(subscriptions, &pb.TopicSubscription{
			TopicFilter: topic,
			Qos:         pb.QoSLevel_QOS_AT_LEAST_ONCE,
		})
	}

	return &pb.ListSubscriptionsResponse{
		Subscriptions: subscriptions,
	}, nil
}

// ========================================
// 设备管理
// ========================================

// RegisterDevice 注册设备
func (s *MQTTServer) RegisterDevice(ctx context.Context, req *pb.RegisterDeviceRequest) (*pb.RegisterDeviceResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	device := &DeviceState{
		DeviceID:       req.DeviceId,
		DeviceName:     req.DeviceName,
		DeviceType:     req.DeviceType,
		UserID:         req.UserId,
		OrganizationID: req.OrganizationId,
		Status:         pb.DeviceStatus_DEVICE_OFFLINE,
		RegisteredAt:   time.Now(),
		LastSeen:       time.Now(),
		Metadata:       req.Metadata,
		Topics:         []string{},
	}

	s.mu.Lock()
	s.devices[req.DeviceId] = device
	s.mu.Unlock()

	s.logAudit(req.UserId, "RegisterDevice", map[string]string{
		"device_id":   req.DeviceId,
		"device_type": req.DeviceType,
	})

	return &pb.RegisterDeviceResponse{
		Success: true,
		Device: &pb.DeviceInfo{
			DeviceId:       device.DeviceID,
			DeviceName:     device.DeviceName,
			DeviceType:     device.DeviceType,
			UserId:         device.UserID,
			OrganizationId: device.OrganizationID,
			Status:         device.Status,
			RegisteredAt:   timestamppb.New(device.RegisteredAt),
			LastSeen:       timestamppb.New(device.LastSeen),
			Metadata:       device.Metadata,
		},
		Message: "Device registered successfully",
	}, nil
}

// UnregisterDevice 注销设备
func (s *MQTTServer) UnregisterDevice(ctx context.Context, req *pb.UnregisterDeviceRequest) (*pb.UnregisterDeviceResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.Lock()
	delete(s.devices, req.DeviceId)
	s.mu.Unlock()

	return &pb.UnregisterDeviceResponse{
		Success: true,
		Message: "Device unregistered successfully",
	}, nil
}

// ListDevices 列出设备
func (s *MQTTServer) ListDevices(ctx context.Context, req *pb.ListDevicesRequest) (*pb.ListDevicesResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	defer s.mu.RUnlock()

	var devices []*pb.DeviceInfo
	for _, device := range s.devices {
		// Filter by user/org
		if device.UserID != req.UserId {
			continue
		}
		if req.OrganizationId != "" && device.OrganizationID != req.OrganizationId {
			continue
		}
		// Filter by status
		if req.Status != pb.DeviceStatus_DEVICE_UNKNOWN && device.Status != req.Status {
			continue
		}

		devices = append(devices, &pb.DeviceInfo{
			DeviceId:         device.DeviceID,
			DeviceName:       device.DeviceName,
			DeviceType:       device.DeviceType,
			UserId:           device.UserID,
			OrganizationId:   device.OrganizationID,
			Status:           device.Status,
			RegisteredAt:     timestamppb.New(device.RegisteredAt),
			LastSeen:         timestamppb.New(device.LastSeen),
			Metadata:         device.Metadata,
			SubscribedTopics: device.Topics,
			MessagesSent:     device.MessagesSent,
			MessagesReceived: device.MessagesRecv,
		})
	}

	return &pb.ListDevicesResponse{
		Devices:    devices,
		TotalCount: int32(len(devices)),
		Page:       req.Page,
		PageSize:   req.PageSize,
	}, nil
}

// GetDeviceInfo 获取设备信息
func (s *MQTTServer) GetDeviceInfo(ctx context.Context, req *pb.GetDeviceInfoRequest) (*pb.GetDeviceInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	device, exists := s.devices[req.DeviceId]
	s.mu.RUnlock()

	if !exists || device.UserID != req.UserId {
		return nil, status.Error(codes.NotFound, "device not found")
	}

	return &pb.GetDeviceInfoResponse{
		Device: &pb.DeviceInfo{
			DeviceId:         device.DeviceID,
			DeviceName:       device.DeviceName,
			DeviceType:       device.DeviceType,
			UserId:           device.UserID,
			OrganizationId:   device.OrganizationID,
			Status:           device.Status,
			RegisteredAt:     timestamppb.New(device.RegisteredAt),
			LastSeen:         timestamppb.New(device.LastSeen),
			Metadata:         device.Metadata,
			SubscribedTopics: device.Topics,
			MessagesSent:     device.MessagesSent,
			MessagesReceived: device.MessagesRecv,
		},
	}, nil
}

// UpdateDeviceStatus 更新设备状态
func (s *MQTTServer) UpdateDeviceStatus(ctx context.Context, req *pb.UpdateDeviceStatusRequest) (*pb.UpdateDeviceStatusResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.Lock()
	device, exists := s.devices[req.DeviceId]
	if exists && device.UserID == req.UserId {
		device.Status = req.Status
		device.LastSeen = time.Now()
		if req.Metadata != nil {
			for k, v := range req.Metadata {
				device.Metadata[k] = v
			}
		}
	}
	s.mu.Unlock()

	if !exists {
		return nil, status.Error(codes.NotFound, "device not found")
	}

	return &pb.UpdateDeviceStatusResponse{
		Success: true,
		Device: &pb.DeviceInfo{
			DeviceId:       device.DeviceID,
			DeviceName:     device.DeviceName,
			DeviceType:     device.DeviceType,
			UserId:         device.UserID,
			OrganizationId: device.OrganizationID,
			Status:         device.Status,
			RegisteredAt:   timestamppb.New(device.RegisteredAt),
			LastSeen:       timestamppb.New(device.LastSeen),
			Metadata:       device.Metadata,
		},
	}, nil
}

// ========================================
// 主题管理
// ========================================

// GetTopicInfo 获取主题信息
func (s *MQTTServer) GetTopicInfo(ctx context.Context, req *pb.GetTopicInfoRequest) (*pb.GetTopicInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	topicKey := fmt.Sprintf("%s:%s", req.UserId, req.Topic)

	s.mu.RLock()
	topic, exists := s.topics[topicKey]
	s.mu.RUnlock()

	if !exists {
		topic = &TopicState{
			Topic:  req.Topic,
			UserID: req.UserId,
		}
	}

	return &pb.GetTopicInfoResponse{
		TopicInfo: &pb.TopicInfo{
			Topic:            topic.Topic,
			SubscriberCount:  topic.SubscriberCount,
			MessageCount:     topic.MessageCount,
			LastMessageTime:  timestamppb.New(topic.LastMessageTime),
			HasRetainedMessage: topic.HasRetainedMsg,
			UserId:           topic.UserID,
			OrganizationId:   topic.OrganizationID,
		},
	}, nil
}

// ListTopics 列出主题
func (s *MQTTServer) ListTopics(ctx context.Context, req *pb.ListTopicsRequest) (*pb.ListTopicsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	defer s.mu.RUnlock()

	var topics []*pb.TopicInfo
	for _, topic := range s.topics {
		if topic.UserID != req.UserId {
			continue
		}
		if req.Prefix != "" && !strings.HasPrefix(topic.Topic, req.Prefix) {
			continue
		}

		topics = append(topics, &pb.TopicInfo{
			Topic:            topic.Topic,
			SubscriberCount:  topic.SubscriberCount,
			MessageCount:     topic.MessageCount,
			LastMessageTime:  timestamppb.New(topic.LastMessageTime),
			HasRetainedMessage: topic.HasRetainedMsg,
			UserId:           topic.UserID,
			OrganizationId:   topic.OrganizationID,
		})
	}

	return &pb.ListTopicsResponse{
		Topics:     topics,
		TotalCount: int32(len(topics)),
	}, nil
}

// ValidateTopic 验证主题
func (s *MQTTServer) ValidateTopic(ctx context.Context, req *pb.ValidateTopicRequest) (*pb.ValidateTopicResponse, error) {
	violations := []string{}

	// MQTT topic validation rules
	if req.Topic == "" {
		violations = append(violations, "Topic cannot be empty")
	}
	if strings.Contains(req.Topic, " ") {
		violations = append(violations, "Topic cannot contain spaces")
	}
	if !req.AllowWildcards {
		if strings.Contains(req.Topic, "+") || strings.Contains(req.Topic, "#") {
			violations = append(violations, "Wildcards not allowed")
		}
	}

	valid := len(violations) == 0
	message := "Topic is valid"
	if !valid {
		message = "Topic validation failed"
	}

	return &pb.ValidateTopicResponse{
		Valid:      valid,
		Message:    message,
		Violations: violations,
	}, nil
}

// ========================================
// 保留消息
// ========================================

// SetRetainedMessage 设置保留消息
func (s *MQTTServer) SetRetainedMessage(ctx context.Context, req *pb.SetRetainedMessageRequest) (*pb.SetRetainedMessageResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	topicKey := fmt.Sprintf("%s:%s", req.UserId, req.Topic)

	s.mu.Lock()
	s.retained[topicKey] = &pb.MQTTMessage{
		Topic:     req.Topic,
		Payload:   req.Payload,
		Qos:       req.Qos,
		Retained:  true,
		Timestamp: timestamppb.Now(),
		MessageId: generateMessageID(),
	}
	s.mu.Unlock()

	return &pb.SetRetainedMessageResponse{
		Success: true,
		Message: "Retained message set successfully",
	}, nil
}

// GetRetainedMessage 获取保留消息
func (s *MQTTServer) GetRetainedMessage(ctx context.Context, req *pb.GetRetainedMessageRequest) (*pb.GetRetainedMessageResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	topicKey := fmt.Sprintf("%s:%s", req.UserId, req.Topic)

	s.mu.RLock()
	msg, found := s.retained[topicKey]
	s.mu.RUnlock()

	return &pb.GetRetainedMessageResponse{
		Found:   found,
		Message: msg,
	}, nil
}

// DeleteRetainedMessage 删除保留消息
func (s *MQTTServer) DeleteRetainedMessage(ctx context.Context, req *pb.DeleteRetainedMessageRequest) (*pb.DeleteRetainedMessageResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	topicKey := fmt.Sprintf("%s:%s", req.UserId, req.Topic)

	s.mu.Lock()
	delete(s.retained, topicKey)
	s.mu.Unlock()

	return &pb.DeleteRetainedMessageResponse{
		Success: true,
		Message: "Retained message deleted successfully",
	}, nil
}

// ========================================
// 统计和监控
// ========================================

// GetStatistics 获取统计信息
func (s *MQTTServer) GetStatistics(ctx context.Context, req *pb.GetStatisticsRequest) (*pb.GetStatisticsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	defer s.mu.RUnlock()

	var totalDevices, onlineDevices int64
	deviceTypes := make(map[string]int64)

	for _, device := range s.devices {
		if device.UserID != req.UserId {
			continue
		}
		totalDevices++
		if device.Status == pb.DeviceStatus_DEVICE_ONLINE {
			onlineDevices++
		}
		deviceTypes[device.DeviceType]++
	}

	var totalTopics int64
	for _, topic := range s.topics {
		if topic.UserID == req.UserId {
			totalTopics++
		}
	}

	var activeSessions int64
	for _, session := range s.sessions {
		if session.UserID == req.UserId {
			activeSessions++
		}
	}

	return &pb.GetStatisticsResponse{
		TotalDevices:            totalDevices,
		OnlineDevices:           onlineDevices,
		TotalTopics:             totalTopics,
		TotalSubscriptions:      0, // TODO: track subscriptions
		MessagesSentToday:       0, // TODO: track daily stats
		MessagesReceivedToday:   0, // TODO: track daily stats
		ActiveSessions:          activeSessions,
		DeviceTypeDistribution:  deviceTypes,
	}, nil
}

// GetDeviceMetrics 获取设备指标
func (s *MQTTServer) GetDeviceMetrics(ctx context.Context, req *pb.GetDeviceMetricsRequest) (*pb.GetDeviceMetricsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.mu.RLock()
	device, exists := s.devices[req.DeviceId]
	s.mu.RUnlock()

	if !exists || device.UserID != req.UserId {
		return nil, status.Error(codes.NotFound, "device not found")
	}

	return &pb.GetDeviceMetricsResponse{
		DeviceId:         device.DeviceID,
		MessagesSent:     device.MessagesSent,
		MessagesReceived: device.MessagesRecv,
		BytesSent:        0, // TODO: track bytes
		BytesReceived:    0, // TODO: track bytes
		MessageRate:      []*pb.TimeSeriesPoint{}, // TODO: implement time series
		ErrorRate:        []*pb.TimeSeriesPoint{}, // TODO: implement time series
	}, nil
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

// ========================================
// 设备消息监听（新增 - 替代 Gateway MQTT Adapter）
// ========================================

// SubscribeDeviceMessages 订阅所有设备消息流
func (s *MQTTServer) SubscribeDeviceMessages(req *pb.SubscribeDeviceMessagesRequest, stream pb.MQTTService_SubscribeDeviceMessagesServer) error {
	fmt.Printf("[STREAM] SubscribeDeviceMessages called by user: %s\n", req.UserId)

	// 构建要订阅的 topic 列表
	var topics []string

	if len(req.TopicPatterns) > 0 {
		// 使用自定义 topic 模式
		topics = req.TopicPatterns
		fmt.Printf("[STREAM] Using custom topic patterns: %v\n", topics)
	} else {
		// 默认订阅所有设备相关 topic
		topics = []string{
			"devices/+/telemetry",
			"devices/+/status",
			"devices/+/auth",
			"devices/+/registration",
			"devices/+/commands/response",
			"notifications/users/+/ack",
			"notifications/system/+",
		}
		fmt.Printf("[STREAM] Using default topics: %v\n", topics)
	}

	// 创建消息通道
	messageChan := make(chan *pb.DeviceMessage, 100)
	done := make(chan bool)
	fmt.Printf("[STREAM] Message channel created with buffer size 100\n")

	// 订阅每个 topic
	for _, topic := range topics {
		topicPattern := topic // 避免闭包问题
		fmt.Printf("[STREAM] Attempting to subscribe to: %s\n", topicPattern)

		err := s.mqttClient.SubscribeWithQoS(topicPattern, 1, func(msgTopic string, payload []byte) error {
			fmt.Printf("[MQTT-CALLBACK] ✅ Message received! Topic: %s, Size: %d bytes\n", msgTopic, len(payload))

			// 解析设备 ID 和消息类型
			deviceID := extractDeviceIDFromTopic(msgTopic)
			messageType := classifyDeviceMessage(msgTopic)
			fmt.Printf("[MQTT-CALLBACK] Parsed - DeviceID: %s, Type: %v\n", deviceID, messageType)

			// 过滤：如果指定了设备 ID，只处理匹配的
			if len(req.DeviceIds) > 0 {
				if !contains(req.DeviceIds, deviceID) {
					return nil
				}
			}

			// 过滤：如果指定了消息类型，只处理匹配的
			if len(req.MessageTypes) > 0 {
				if !containsMessageType(req.MessageTypes, messageType) {
					return nil
				}
			}

			// 构建设备消息
			deviceMessage := &pb.DeviceMessage{
				DeviceId:    deviceID,
				MessageType: messageType,
				Topic:       msgTopic,
				Payload:     payload,
				Timestamp:   timestamppb.Now(),
				Metadata: map[string]string{
					"qos": "1",
				},
				Qos: pb.QoSLevel_QOS_AT_LEAST_ONCE,
			}

			// 发送到通道
			select {
			case messageChan <- deviceMessage:
				fmt.Printf("[MQTT-CALLBACK] Message sent to channel successfully\n")
			case <-done:
				fmt.Printf("[MQTT-CALLBACK] Stream closed, dropping message\n")
				return nil
			default:
				fmt.Printf("[MQTT-CALLBACK] ⚠️ Channel full, dropping message\n")
			}
			return nil
		})

		if err != nil {
			fmt.Printf("[STREAM] ❌ Failed to subscribe to %s: %v\n", topicPattern, err)
			close(done)
			return status.Errorf(codes.Internal, "failed to subscribe to topic %s: %v", topicPattern, err)
		}
		fmt.Printf("[STREAM] ✅ Successfully subscribed to: %s\n", topicPattern)
	}

	// 监听客户端断开和消息发送
	go func() {
		<-stream.Context().Done()
		fmt.Printf("[STREAM] Client disconnected, cleaning up\n")
		close(done)
	}()

	fmt.Printf("[STREAM] Entering message forwarding loop...\n")

	// 持续发送消息到客户端
	for {
		select {
		case msg := <-messageChan:
			fmt.Printf("[STREAM] Forwarding message to client: %s - %s\n", msg.DeviceId, msg.Topic)
			if err := stream.Send(msg); err != nil {
				fmt.Printf("[STREAM] ❌ Error sending to client: %v\n", err)
				// 清理订阅
				for _, topic := range topics {
					s.mqttClient.Unsubscribe(topic)
				}
				return err
			}
			fmt.Printf("[STREAM] ✅ Message sent to client successfully\n")
		case <-done:
			fmt.Printf("[STREAM] Stream done, unsubscribing from all topics\n")
			// 清理订阅
			for _, topic := range topics {
				s.mqttClient.Unsubscribe(topic)
				fmt.Printf("[STREAM] Unsubscribed from: %s\n", topic)
			}
			return nil
		}
	}
}

// extractDeviceIDFromTopic 从 topic 中提取设备 ID
func extractDeviceIDFromTopic(topic string) string {
	parts := strings.Split(topic, "/")
	if len(parts) >= 2 && parts[0] == "devices" {
		return parts[1]
	}
	if len(parts) >= 3 && parts[0] == "notifications" && parts[1] == "users" {
		return parts[2] // 用户 ID 作为设备 ID
	}
	if len(parts) >= 3 && parts[0] == "notifications" && parts[1] == "system" {
		return parts[2] // 系统 ID
	}
	return "unknown"
}

// classifyDeviceMessage 根据 topic 分类消息类型
func classifyDeviceMessage(topic string) pb.DeviceMessageType {
	if strings.Contains(topic, "/telemetry") {
		return pb.DeviceMessageType_DEVICE_MESSAGE_TELEMETRY
	}
	if strings.Contains(topic, "/status") {
		return pb.DeviceMessageType_DEVICE_MESSAGE_STATUS
	}
	if strings.Contains(topic, "/auth") {
		return pb.DeviceMessageType_DEVICE_MESSAGE_AUTH
	}
	if strings.Contains(topic, "/registration") {
		return pb.DeviceMessageType_DEVICE_MESSAGE_REGISTRATION
	}
	if strings.Contains(topic, "/commands/response") {
		return pb.DeviceMessageType_DEVICE_MESSAGE_COMMAND_RESPONSE
	}
	if strings.Contains(topic, "/ack") {
		return pb.DeviceMessageType_DEVICE_MESSAGE_NOTIFICATION_ACK
	}
	return pb.DeviceMessageType_DEVICE_MESSAGE_UNKNOWN
}

// contains 检查字符串切片是否包含某个值
func contains(slice []string, val string) bool {
	for _, item := range slice {
		if item == val {
			return true
		}
	}
	return false
}

// containsMessageType 检查消息类型切片是否包含某个类型
func containsMessageType(types []pb.DeviceMessageType, val pb.DeviceMessageType) bool {
	for _, t := range types {
		if t == val {
			return true
		}
	}
	return false
}

// ========================================
// Webhook 回调（新增）
// ========================================

// RegisterWebhook 注册 webhook
func (s *MQTTServer) RegisterWebhook(ctx context.Context, req *pb.RegisterWebhookRequest) (*pb.RegisterWebhookResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 生成 webhook ID
	webhookID := uuid.New().String()

	// 创建 webhook 状态
	webhook := &WebhookState{
		WebhookID:      webhookID,
		UserID:         req.UserId,
		OrganizationID: req.OrganizationId,
		URL:            req.Url,
		MessageTypes:   req.MessageTypes,
		DeviceIDs:      req.DeviceIds,
		TopicPatterns:  req.TopicPatterns,
		Headers:        req.Headers,
		Secret:         req.Secret,
		Enabled:        true,
		CreatedAt:      time.Now(),
		UpdatedAt:      time.Now(),
		SuccessCount:   0,
		FailureCount:   0,
	}

	// 启动 webhook 监听器
	webhookCtx, cancel := context.WithCancel(context.Background())
	webhook.cancelFunc = cancel

	go s.runWebhookListener(webhookCtx, webhook)

	// 保存 webhook
	s.webhooks[webhookID] = webhook

	// 构建响应
	webhookInfo := &pb.WebhookInfo{
		WebhookId:      webhook.WebhookID,
		UserId:         webhook.UserID,
		Url:            webhook.URL,
		MessageTypes:   webhook.MessageTypes,
		DeviceIds:      webhook.DeviceIDs,
		TopicPatterns:  webhook.TopicPatterns,
		Headers:        webhook.Headers,
		Enabled:        webhook.Enabled,
		CreatedAt:      timestamppb.New(webhook.CreatedAt),
		UpdatedAt:      timestamppb.New(webhook.UpdatedAt),
		SuccessCount:   webhook.SuccessCount,
		FailureCount:   webhook.FailureCount,
	}

	return &pb.RegisterWebhookResponse{
		Success:   true,
		WebhookId: webhookID,
		Webhook:   webhookInfo,
		Message:   "Webhook registered successfully",
	}, nil
}

// UnregisterWebhook 注销 webhook
func (s *MQTTServer) UnregisterWebhook(ctx context.Context, req *pb.UnregisterWebhookRequest) (*pb.UnregisterWebhookResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	webhook, exists := s.webhooks[req.WebhookId]
	if !exists {
		return nil, status.Errorf(codes.NotFound, "webhook not found: %s", req.WebhookId)
	}

	// 检查权限
	if webhook.UserID != req.UserId {
		return nil, status.Errorf(codes.PermissionDenied, "permission denied")
	}

	// 停止 webhook 监听器
	if webhook.cancelFunc != nil {
		webhook.cancelFunc()
	}

	// 删除 webhook
	delete(s.webhooks, req.WebhookId)

	return &pb.UnregisterWebhookResponse{
		Success: true,
		Message: "Webhook unregistered successfully",
	}, nil
}

// ListWebhooks 列出 webhooks
func (s *MQTTServer) ListWebhooks(ctx context.Context, req *pb.ListWebhooksRequest) (*pb.ListWebhooksResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var webhookInfos []*pb.WebhookInfo
	for _, webhook := range s.webhooks {
		// 过滤：只返回当前用户的 webhooks
		if webhook.UserID != req.UserId {
			continue
		}

		// 过滤：如果指定了组织，只返回该组织的
		if req.OrganizationId != "" && webhook.OrganizationID != req.OrganizationId {
			continue
		}

		// 过滤：是否包含已禁用的
		if !req.IncludeDisabled && !webhook.Enabled {
			continue
		}

		webhookInfo := &pb.WebhookInfo{
			WebhookId:      webhook.WebhookID,
			UserId:         webhook.UserID,
			Url:            webhook.URL,
			MessageTypes:   webhook.MessageTypes,
			DeviceIds:      webhook.DeviceIDs,
			TopicPatterns:  webhook.TopicPatterns,
			Headers:        webhook.Headers,
			Enabled:        webhook.Enabled,
			CreatedAt:      timestamppb.New(webhook.CreatedAt),
			UpdatedAt:      timestamppb.New(webhook.UpdatedAt),
			SuccessCount:   webhook.SuccessCount,
			FailureCount:   webhook.FailureCount,
		}
		webhookInfos = append(webhookInfos, webhookInfo)
	}

	return &pb.ListWebhooksResponse{
		Webhooks:   webhookInfos,
		TotalCount: int32(len(webhookInfos)),
	}, nil
}

// runWebhookListener 运行 webhook 监听器
func (s *MQTTServer) runWebhookListener(ctx context.Context, webhook *WebhookState) {
	// 构建要订阅的 topic 列表
	var topics []string
	if len(webhook.TopicPatterns) > 0 {
		topics = webhook.TopicPatterns
	} else {
		// 默认订阅所有设备 topic
		topics = []string{
			"devices/+/telemetry",
			"devices/+/status",
			"devices/+/auth",
			"devices/+/registration",
			"devices/+/commands/response",
		}
	}

	// HTTP 客户端
	httpClient := &http.Client{Timeout: 30 * time.Second}

	// 订阅每个 topic
	for _, topic := range topics {
		topicPattern := topic
		s.mqttClient.SubscribeWithQoS(topicPattern, 1, func(msgTopic string, msgPayload []byte) error {
			// 检查 context 是否已取消
			select {
			case <-ctx.Done():
				return nil
			default:
			}

			// 过滤设备 ID
			deviceID := extractDeviceIDFromTopic(msgTopic)
			if len(webhook.DeviceIDs) > 0 && !contains(webhook.DeviceIDs, deviceID) {
				return nil
			}

			// 过滤消息类型
			messageType := classifyDeviceMessage(msgTopic)
			if len(webhook.MessageTypes) > 0 && !containsMessageType(webhook.MessageTypes, messageType) {
				return nil
			}

			// 构建 webhook payload
			payload := map[string]interface{}{
				"webhook_id":   webhook.WebhookID,
				"device_id":    deviceID,
				"message_type": messageType.String(),
				"topic":        msgTopic,
				"payload":      string(msgPayload),
				"timestamp":    time.Now().UTC().Format(time.RFC3339),
				"qos":          1,
			}

			// 发送 HTTP 请求
			go s.sendWebhookRequest(httpClient, webhook, payload)
			return nil
		})
	}

	// 等待 context 取消
	<-ctx.Done()

	// 清理订阅
	for _, topic := range topics {
		s.mqttClient.Unsubscribe(topic)
	}
}

// sendWebhookRequest 发送 webhook HTTP 请求
func (s *MQTTServer) sendWebhookRequest(client *http.Client, webhook *WebhookState, payload map[string]interface{}) {
	// 序列化 payload
	jsonData, err := json.Marshal(payload)
	if err != nil {
		s.incrementWebhookFailure(webhook.WebhookID)
		return
	}

	// 创建 HTTP 请求
	req, err := http.NewRequest("POST", webhook.URL, bytes.NewBuffer(jsonData))
	if err != nil {
		s.incrementWebhookFailure(webhook.WebhookID)
		return
	}

	// 设置 Headers
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "isA-MQTT-Webhook/1.0")
	req.Header.Set("X-Webhook-ID", webhook.WebhookID)
	req.Header.Set("X-Timestamp", time.Now().UTC().Format(time.RFC3339))

	// 添加自定义 headers
	for key, value := range webhook.Headers {
		req.Header.Set(key, value)
	}

	// 添加签名（如果有 secret）
	if webhook.Secret != "" {
		signature := generateHMACSHA256(jsonData, webhook.Secret)
		req.Header.Set("X-Webhook-Signature", signature)
	}

	// 发送请求
	resp, err := client.Do(req)
	if err != nil {
		s.incrementWebhookFailure(webhook.WebhookID)
		return
	}
	defer resp.Body.Close()

	// 检查响应状态
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		s.incrementWebhookSuccess(webhook.WebhookID)
	} else {
		s.incrementWebhookFailure(webhook.WebhookID)
	}
}

// incrementWebhookSuccess 增加 webhook 成功计数
func (s *MQTTServer) incrementWebhookSuccess(webhookID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if webhook, exists := s.webhooks[webhookID]; exists {
		webhook.SuccessCount++
		webhook.UpdatedAt = time.Now()
	}
}

// incrementWebhookFailure 增加 webhook 失败计数
func (s *MQTTServer) incrementWebhookFailure(webhookID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if webhook, exists := s.webhooks[webhookID]; exists {
		webhook.FailureCount++
		webhook.UpdatedAt = time.Now()
	}
}

// generateHMACSHA256 生成 HMAC-SHA256 签名
func generateHMACSHA256(data []byte, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(data)
	return hex.EncodeToString(h.Sum(nil))
}

// ========================================
// 辅助函数
// ========================================

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
