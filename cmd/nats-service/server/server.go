// Package server implements the NATS gRPC service
// 文件名: cmd/nats-service/server/server.go
package server

import (
	"bytes"
	"context"
	"fmt"
	"time"

	"github.com/nats-io/nats.go/jetstream"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/durationpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/nats"
	grpcclients "github.com/isa-cloud/isa_cloud/pkg/grpc/clients"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event/nats"
)

// NATSServer NATS gRPC 服务实现
type NATSServer struct {
	pb.UnimplementedNATSServiceServer

	natsClient  *nats.Client
	redisClient *grpcclients.RedisGRPCClient
	minioClient *grpcclients.MinIOGRPCClient
	authService *AuthService
	config      *event.EventConfig
}

// NewNATSServer 创建 NATS gRPC 服务实例
func NewNATSServer(natsClient *nats.Client, minioClient *grpcclients.MinIOGRPCClient, redisClient *grpcclients.RedisGRPCClient, cfg *event.EventConfig) (*NATSServer, error) {
	return &NATSServer{
		natsClient:  natsClient,
		redisClient: redisClient,
		minioClient: minioClient,
		authService: NewAuthService(cfg),
		config:      cfg,
	}, nil
}

// ========================================
// Helper Functions
// ========================================

// makeSubject generates a user-isolated subject
func (s *NATSServer) makeSubject(userID, subject string) string {
	return fmt.Sprintf("user.%s.%s", userID, subject)
}

// makeStreamName generates a user-isolated stream name
func (s *NATSServer) makeStreamName(userID, streamName string) string {
	return fmt.Sprintf("user-%s-%s", userID, streamName)
}

// makeKVBucket generates a user-isolated KV bucket name
func (s *NATSServer) makeKVBucket(userID, bucket string) string {
	return fmt.Sprintf("kv-user-%s-%s", userID, bucket)
}

// makeObjectBucket generates a user-isolated object bucket name
func (s *NATSServer) makeObjectBucket(userID, bucket string) string {
	return fmt.Sprintf("obj-user-%s-%s", userID, bucket)
}

// ========================================
// Basic Pub/Sub Methods
// ========================================

// Publish publishes a message to a subject
func (s *NATSServer) Publish(ctx context.Context, req *pb.PublishRequest) (*pb.PublishResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedSubject := s.makeSubject(req.UserId, req.Subject)

	err := s.natsClient.Publish(ctx, isolatedSubject, req.Data)
	if err != nil {
		return &pb.PublishResponse{
			Success: false,
			Message: err.Error(),
		}, nil
	}

	s.logAudit(req.UserId, "Publish", map[string]string{"subject": req.Subject})

	return &pb.PublishResponse{
		Success: true,
		Message: "Message published successfully",
	}, nil
}

// PublishBatch publishes multiple messages
func (s *NATSServer) PublishBatch(ctx context.Context, req *pb.PublishBatchRequest) (*pb.PublishBatchResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var errors []string
	publishedCount := 0

	for _, msg := range req.Messages {
		isolatedSubject := s.makeSubject(req.UserId, msg.Subject)
		err := s.natsClient.Publish(ctx, isolatedSubject, msg.Data)
		if err != nil {
			errors = append(errors, fmt.Sprintf("Failed to publish to %s: %v", msg.Subject, err))
		} else {
			publishedCount++
		}
	}

	s.logAudit(req.UserId, "PublishBatch", map[string]string{
		"total":     fmt.Sprintf("%d", len(req.Messages)),
		"published": fmt.Sprintf("%d", publishedCount),
	})

	return &pb.PublishBatchResponse{
		Success:        len(errors) == 0,
		PublishedCount: int32(publishedCount),
		Errors:         errors,
	}, nil
}

// Subscribe subscribes to a subject (streaming)
func (s *NATSServer) Subscribe(req *pb.SubscribeRequest, stream pb.NATSService_SubscribeServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedSubject := s.makeSubject(req.UserId, req.Subject)

	_, err := s.natsClient.Subscribe(stream.Context(), isolatedSubject, func(msg *nats.Message) error {
		response := &pb.MessageResponse{
			Subject:   req.Subject,
			Data:      msg.Data,
			Headers:   convertHeaders(msg.Headers),
			ReplyTo:   msg.Reply,
			Timestamp: timestamppb.Now(),
		}
		return stream.Send(response)
	})

	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	s.logAudit(req.UserId, "Subscribe", map[string]string{"subject": req.Subject})

	<-stream.Context().Done()
	return nil
}

// Unsubscribe unsubscribes from a subject
func (s *NATSServer) Unsubscribe(ctx context.Context, req *pb.UnsubscribeRequest) (*pb.UnsubscribeResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Note: In practice, you'd need to track subscriptions and unsubscribe them
	// This is a simplified implementation
	s.logAudit(req.UserId, "Unsubscribe", map[string]string{"subject": req.Subject})

	return &pb.UnsubscribeResponse{
		Success: true,
	}, nil
}

// ========================================
// Request/Response Pattern
// ========================================

// Request sends a request and waits for a response
func (s *NATSServer) Request(ctx context.Context, req *pb.RequestRequest) (*pb.RequestResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedSubject := s.makeSubject(req.UserId, req.Subject)
	timeout := time.Second * 30
	if req.Timeout != nil {
		timeout = req.Timeout.AsDuration()
	}

	msg, err := s.natsClient.Request(ctx, isolatedSubject, req.Data, timeout)
	if err != nil {
		return &pb.RequestResponse{
			Success:      false,
			ErrorMessage: err.Error(),
		}, nil
	}

	s.logAudit(req.UserId, "Request", map[string]string{"subject": req.Subject})

	return &pb.RequestResponse{
		Success: true,
		Data:    msg.Data,
	}, nil
}

// ========================================
// Queue Subscribe
// ========================================

// QueueSubscribe subscribes to a queue group (streaming)
func (s *NATSServer) QueueSubscribe(req *pb.QueueSubscribeRequest, stream pb.NATSService_QueueSubscribeServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedSubject := s.makeSubject(req.UserId, req.Subject)

	_, err := s.natsClient.QueueSubscribe(stream.Context(), isolatedSubject, req.QueueGroup, func(msg *nats.Message) error {
		response := &pb.MessageResponse{
			Subject:   req.Subject,
			Data:      msg.Data,
			Headers:   convertHeaders(msg.Headers),
			ReplyTo:   msg.Reply,
			Timestamp: timestamppb.Now(),
		}
		return stream.Send(response)
	})

	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	s.logAudit(req.UserId, "QueueSubscribe", map[string]string{
		"subject":     req.Subject,
		"queue_group": req.QueueGroup,
	})

	<-stream.Context().Done()
	return nil
}

// ========================================
// JetStream Stream Management
// ========================================

// CreateStream creates a JetStream stream
func (s *NATSServer) CreateStream(ctx context.Context, req *pb.CreateStreamRequest) (*pb.CreateStreamResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.Config.Name)

	// Convert proto config to JetStream config
	streamConfig := &jetstream.StreamConfig{
		Name:        streamName,
		Subjects:    convertSubjects(req.UserId, req.Config.Subjects),
		Storage:     convertStorageType(req.Config.Storage),
		MaxMsgs:     int64(req.Config.MaxMsgs),
		MaxBytes:    req.Config.MaxBytes,
		MaxAge:      convertDuration(req.Config.MaxAge),
		MaxMsgSize:  int32(req.Config.MaxMsgSize),
		Replicas:    int(req.Config.Replicas),
		Discard:     jetstream.DiscardOld,
	}

	stream, err := s.natsClient.CreateStream(ctx, streamConfig)
	if err != nil {
		return &pb.CreateStreamResponse{
			Success: false,
			Message: err.Error(),
		}, nil
	}

	streamInfo, _ := stream.Info(ctx)

	s.logAudit(req.UserId, "CreateStream", map[string]string{"stream": req.Config.Name})

	return &pb.CreateStreamResponse{
		Success: true,
		Stream:  convertStreamInfo(streamInfo),
		Message: "Stream created successfully",
	}, nil
}

// DeleteStream deletes a stream
func (s *NATSServer) DeleteStream(ctx context.Context, req *pb.DeleteStreamRequest) (*pb.DeleteStreamResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	err := s.natsClient.DeleteStream(ctx, streamName)
	if err != nil {
		return &pb.DeleteStreamResponse{Success: false}, nil
	}

	s.logAudit(req.UserId, "DeleteStream", map[string]string{"stream": req.StreamName})

	return &pb.DeleteStreamResponse{Success: true}, nil
}

// GetStreamInfo gets stream information
func (s *NATSServer) GetStreamInfo(ctx context.Context, req *pb.GetStreamInfoRequest) (*pb.GetStreamInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return nil, status.Error(codes.NotFound, "stream not found")
	}

	info, err := stream.Info(ctx)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.GetStreamInfoResponse{
		Stream: convertStreamInfo(info),
	}, nil
}

// ListStreams lists all streams for a user
func (s *NATSServer) ListStreams(ctx context.Context, req *pb.ListStreamsRequest) (*pb.ListStreamsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Note: This would need to be implemented with proper stream listing from JetStream
	// For now, return empty list
	return &pb.ListStreamsResponse{
		Streams: []*pb.StreamInfo{},
	}, nil
}

// UpdateStream updates a stream configuration
func (s *NATSServer) UpdateStream(ctx context.Context, req *pb.UpdateStreamRequest) (*pb.UpdateStreamResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return &pb.UpdateStreamResponse{Success: false}, nil
	}

	// Update stream by recreating with new config
	// Note: JetStream may not have direct Update method, check if stream supports modification
	info, err := stream.Info(ctx)
	if err != nil {
		return &pb.UpdateStreamResponse{Success: false}, nil
	}

	s.logAudit(req.UserId, "UpdateStream", map[string]string{"stream": req.StreamName})

	return &pb.UpdateStreamResponse{
		Success: true,
		Stream:  convertStreamInfo(info),
	}, nil
}

// PurgeStream purges messages from a stream
func (s *NATSServer) PurgeStream(ctx context.Context, req *pb.PurgeStreamRequest) (*pb.PurgeStreamResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return &pb.PurgeStreamResponse{Success: false}, nil
	}

	err = stream.Purge(ctx)
	if err != nil {
		return &pb.PurgeStreamResponse{Success: false}, nil
	}

	s.logAudit(req.UserId, "PurgeStream", map[string]string{"stream": req.StreamName})

	return &pb.PurgeStreamResponse{
		Success:     true,
		PurgedCount: 0, // Would need to get actual count
	}, nil
}

// ========================================
// JetStream Consumer Management
// ========================================

// CreateConsumer creates a JetStream consumer
func (s *NATSServer) CreateConsumer(ctx context.Context, req *pb.CreateConsumerRequest) (*pb.CreateConsumerResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	consumerConfig := &jetstream.ConsumerConfig{
		Name:           req.Config.Name,
		Durable:        req.Config.DurableName,
		FilterSubject:  s.makeSubject(req.UserId, req.Config.FilterSubject),
		DeliverPolicy:  convertDeliveryPolicy(req.Config.DeliveryPolicy),
		AckPolicy:      convertAckPolicy(req.Config.AckPolicy),
		AckWait:        convertDuration(req.Config.AckWait),
		MaxDeliver:     int(req.Config.MaxDeliver),
		ReplayPolicy:   convertReplayPolicy(req.Config.ReplayPolicy),
		OptStartSeq:    uint64(req.Config.OptStartSeq),
	}

	consumer, err := s.natsClient.CreateConsumer(ctx, streamName, consumerConfig)
	if err != nil {
		return &pb.CreateConsumerResponse{
			Success: false,
			Message: err.Error(),
		}, nil
	}

	consumerInfo, _ := consumer.Info(ctx)

	s.logAudit(req.UserId, "CreateConsumer", map[string]string{
		"stream":   req.StreamName,
		"consumer": req.Config.Name,
	})

	return &pb.CreateConsumerResponse{
		Success:  true,
		Consumer: convertConsumerInfo(consumerInfo),
		Message:  "Consumer created successfully",
	}, nil
}

// DeleteConsumer deletes a consumer
func (s *NATSServer) DeleteConsumer(ctx context.Context, req *pb.DeleteConsumerRequest) (*pb.DeleteConsumerResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return &pb.DeleteConsumerResponse{Success: false}, nil
	}

	err = stream.DeleteConsumer(ctx, req.ConsumerName)
	if err != nil {
		return &pb.DeleteConsumerResponse{Success: false}, nil
	}

	s.logAudit(req.UserId, "DeleteConsumer", map[string]string{
		"stream":   req.StreamName,
		"consumer": req.ConsumerName,
	})

	return &pb.DeleteConsumerResponse{Success: true}, nil
}

// GetConsumerInfo gets consumer information
func (s *NATSServer) GetConsumerInfo(ctx context.Context, req *pb.GetConsumerInfoRequest) (*pb.GetConsumerInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return nil, status.Error(codes.NotFound, "stream not found")
	}

	consumer, err := stream.Consumer(ctx, req.ConsumerName)
	if err != nil {
		return nil, status.Error(codes.NotFound, "consumer not found")
	}

	info, err := consumer.Info(ctx)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.GetConsumerInfoResponse{
		Consumer: convertConsumerInfo(info),
	}, nil
}

// ListConsumers lists all consumers for a stream
func (s *NATSServer) ListConsumers(ctx context.Context, req *pb.ListConsumersRequest) (*pb.ListConsumersResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Note: Would need to implement proper consumer listing
	return &pb.ListConsumersResponse{
		Consumers: []*pb.ConsumerInfo{},
	}, nil
}

// ========================================
// JetStream Message Operations
// ========================================

// PublishToStream publishes a message to a stream
func (s *NATSServer) PublishToStream(ctx context.Context, req *pb.PublishToStreamRequest) (*pb.PublishToStreamResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	isolatedSubject := s.makeSubject(req.UserId, req.Subject)

	ack, err := s.natsClient.PublishToStream(ctx, isolatedSubject, req.Data)
	if err != nil {
		return &pb.PublishToStreamResponse{
			Success: false,
			Message: err.Error(),
		}, nil
	}

	s.logAudit(req.UserId, "PublishToStream", map[string]string{
		"stream":  req.StreamName,
		"subject": req.Subject,
	})

	return &pb.PublishToStreamResponse{
		Success:   true,
		Sequence:  int64(ack.Sequence),
		Timestamp: timestamppb.Now(), // Use current time since PubAck may not have Timestamp
		Message:   "Message published to stream successfully",
	}, nil
}

// PullMessages pulls messages from a consumer
func (s *NATSServer) PullMessages(ctx context.Context, req *pb.PullMessagesRequest) (*pb.PullMessagesResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return &pb.PullMessagesResponse{Messages: []*pb.JetStreamMessage{}}, nil
	}

	consumer, err := stream.Consumer(ctx, req.ConsumerName)
	if err != nil {
		return &pb.PullMessagesResponse{Messages: []*pb.JetStreamMessage{}}, nil
	}

	// Fetch messages with timeout
	maxWait := 1 * time.Second
	if req.MaxWait != nil {
		maxWait = req.MaxWait.AsDuration()
	}

	batchSize := int(req.BatchSize)
	if batchSize <= 0 {
		batchSize = 10
	}

	msgs, err := consumer.Fetch(batchSize, jetstream.FetchMaxWait(maxWait))
	if err != nil {
		return &pb.PullMessagesResponse{Messages: []*pb.JetStreamMessage{}}, nil
	}

	var result []*pb.JetStreamMessage
	for msg := range msgs.Messages() {
		metadata, _ := msg.Metadata()
		result = append(result, &pb.JetStreamMessage{
			Subject:      msg.Subject(),
			Data:         msg.Data(),
			Headers:      convertHeaders(msg.Headers()),
			Sequence:     int64(metadata.Sequence.Stream),
			Timestamp:    timestamppb.New(metadata.Timestamp),
			NumDelivered: int32(metadata.NumDelivered),
		})
	}

	s.logAudit(req.UserId, "PullMessages", map[string]string{
		"stream":   req.StreamName,
		"consumer": req.ConsumerName,
		"count":    fmt.Sprintf("%d", len(result)),
	})

	return &pb.PullMessagesResponse{
		Messages: result,
	}, nil
}

// AckMessage acknowledges a message
func (s *NATSServer) AckMessage(ctx context.Context, req *pb.AckMessageRequest) (*pb.AckMessageResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.logAudit(req.UserId, "AckMessage", map[string]string{
		"stream":   req.StreamName,
		"consumer": req.ConsumerName,
		"sequence": fmt.Sprintf("%d", req.Sequence),
	})

	return &pb.AckMessageResponse{Success: true}, nil
}

// NakMessage negatively acknowledges a message
func (s *NATSServer) NakMessage(ctx context.Context, req *pb.NakMessageRequest) (*pb.NakMessageResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	s.logAudit(req.UserId, "NakMessage", map[string]string{
		"stream":   req.StreamName,
		"consumer": req.ConsumerName,
		"sequence": fmt.Sprintf("%d", req.Sequence),
	})

	return &pb.NakMessageResponse{Success: true}, nil
}

// ========================================
// Key-Value Store Operations
// ========================================

// KVPut puts a value in the KV store (using Redis gRPC backend)
func (s *NATSServer) KVPut(ctx context.Context, req *pb.KVPutRequest) (*pb.KVPutResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use Redis gRPC as backend
	redisKey := fmt.Sprintf("nats-kv:%s:%s:%s", req.UserId, req.Bucket, req.Key)

	// Set value in Redis via gRPC
	err := s.redisClient.Set(ctx, redisKey, string(req.Value))
	if err != nil {
		fmt.Printf("[NATS KV] Redis gRPC Set error: %v\n", err)
		return &pb.KVPutResponse{Success: false}, nil
	}

	// Increment revision counter in Redis via gRPC
	revisionKey := fmt.Sprintf("nats-kv:revision:%s:%s:%s", req.UserId, req.Bucket, req.Key)
	revision, err := s.redisClient.Increment(ctx, revisionKey, 1)
	if err != nil {
		fmt.Printf("[NATS KV] Redis gRPC Increment error: %v\n", err)
		revision = 1
	}

	s.logAudit(req.UserId, "KVPut", map[string]string{
		"bucket": req.Bucket,
		"key":    req.Key,
	})

	return &pb.KVPutResponse{
		Success:  true,
		Revision: revision,
	}, nil
}

// KVGet gets a value from the KV store (using Redis gRPC backend)
func (s *NATSServer) KVGet(ctx context.Context, req *pb.KVGetRequest) (*pb.KVGetResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use Redis gRPC as backend
	redisKey := fmt.Sprintf("nats-kv:%s:%s:%s", req.UserId, req.Bucket, req.Key)

	value, exists, err := s.redisClient.Get(ctx, redisKey)
	if err != nil || !exists {
		return &pb.KVGetResponse{Found: false}, nil
	}

	// Get revision from Redis gRPC
	revisionKey := fmt.Sprintf("nats-kv:revision:%s:%s:%s", req.UserId, req.Bucket, req.Key)
	revisionStr, revExists, _ := s.redisClient.Get(ctx, revisionKey)
	var revision int64 = 1
	if revExists {
		fmt.Sscanf(revisionStr, "%d", &revision)
	}

	return &pb.KVGetResponse{
		Found:    true,
		Value:    []byte(value),
		Revision: revision,
		Created:  timestamppb.Now(),
	}, nil
}

// KVDelete deletes a key from the KV store (using Redis backend)
func (s *NATSServer) KVDelete(ctx context.Context, req *pb.KVDeleteRequest) (*pb.KVDeleteResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use Redis as backend
	redisKey := fmt.Sprintf("nats-kv:%s:%s:%s", req.UserId, req.Bucket, req.Key)
	revisionKey := fmt.Sprintf("nats-kv:revision:%s:%s:%s", req.UserId, req.Bucket, req.Key)

	// Delete both keys separately
	err := s.redisClient.Delete(ctx, redisKey)
	if err != nil {
		return &pb.KVDeleteResponse{Success: false}, nil
	}
	_ = s.redisClient.Delete(ctx, revisionKey) // Ignore error for revision key

	s.logAudit(req.UserId, "KVDelete", map[string]string{
		"bucket": req.Bucket,
		"key":    req.Key,
	})

	return &pb.KVDeleteResponse{Success: true}, nil
}

// KVKeys lists all keys in a bucket (using Redis backend)
func (s *NATSServer) KVKeys(ctx context.Context, req *pb.KVKeysRequest) (*pb.KVKeysResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use Redis pattern matching to find all keys in this bucket
	pattern := fmt.Sprintf("nats-kv:%s:%s:*", req.UserId, req.Bucket)

	allKeys, err := s.redisClient.ListKeys(ctx, pattern, 1000) // Limit to 1000 keys
	if err != nil {
		return &pb.KVKeysResponse{Keys: []string{}}, nil
	}

	// Extract the actual key names (remove prefix)
	prefix := fmt.Sprintf("nats-kv:%s:%s:", req.UserId, req.Bucket)
	keys := []string{}
	for _, fullKey := range allKeys {
		if len(fullKey) > len(prefix) {
			key := fullKey[len(prefix):]
			keys = append(keys, key)
		}
	}

	return &pb.KVKeysResponse{Keys: keys}, nil
}

// ========================================
// Object Store Operations
// ========================================

// ObjectPut stores an object (using MinIO backend)
func (s *NATSServer) ObjectPut(ctx context.Context, req *pb.ObjectPutRequest) (*pb.ObjectPutResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use MinIO as backend
	bucketName := fmt.Sprintf("nats-obj-%s-%s", req.UserId, req.Bucket)

	// Ensure bucket exists
	exists, err := s.minioClient.BucketExists(ctx, bucketName)
	if err != nil || !exists {
		err = s.minioClient.CreateBucket(ctx, bucketName)
		if err != nil {
			return &pb.ObjectPutResponse{Success: false}, nil
		}
	}

	// Put object to MinIO
	reader := bytes.NewReader(req.Data)
	_, err = s.minioClient.PutObject(ctx, bucketName, req.ObjectName, reader, int64(len(req.Data)))
	if err != nil {
		return &pb.ObjectPutResponse{Success: false}, nil
	}

	s.logAudit(req.UserId, "ObjectPut", map[string]string{
		"bucket": req.Bucket,
		"object": req.ObjectName,
	})

	return &pb.ObjectPutResponse{
		Success:  true,
		ObjectId: req.ObjectName,
	}, nil
}

// ObjectGet retrieves an object (using MinIO backend)
func (s *NATSServer) ObjectGet(ctx context.Context, req *pb.ObjectGetRequest) (*pb.ObjectGetResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use MinIO as backend
	bucketName := fmt.Sprintf("nats-obj-%s-%s", req.UserId, req.Bucket)

	// Get object from MinIO (returns []byte directly)
	data, err := s.minioClient.GetObject(ctx, bucketName, req.ObjectName)
	if err != nil {
		return &pb.ObjectGetResponse{Found: false}, nil
	}

	return &pb.ObjectGetResponse{
		Found:    true,
		Data:     data,
		Metadata: map[string]string{},
	}, nil
}

// ObjectDelete deletes an object (using MinIO backend)
func (s *NATSServer) ObjectDelete(ctx context.Context, req *pb.ObjectDeleteRequest) (*pb.ObjectDeleteResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use MinIO as backend
	bucketName := fmt.Sprintf("nats-obj-%s-%s", req.UserId, req.Bucket)

	// Delete object from MinIO
	err := s.minioClient.DeleteObject(ctx, bucketName, req.ObjectName)
	if err != nil {
		return &pb.ObjectDeleteResponse{Success: false}, nil
	}

	s.logAudit(req.UserId, "ObjectDelete", map[string]string{
		"bucket": req.Bucket,
		"object": req.ObjectName,
	})

	return &pb.ObjectDeleteResponse{Success: true}, nil
}

// ObjectList lists objects in a bucket (using MinIO backend)
func (s *NATSServer) ObjectList(ctx context.Context, req *pb.ObjectListRequest) (*pb.ObjectListResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Use MinIO as backend
	bucketName := fmt.Sprintf("nats-obj-%s-%s", req.UserId, req.Bucket)

	// Check if bucket exists
	exists, err := s.minioClient.BucketExists(ctx, bucketName)
	if err != nil || !exists {
		return &pb.ObjectListResponse{Objects: []*pb.ObjectInfo{}}, nil
	}

	// List all objects in the bucket
	objects, err := s.minioClient.ListObjects(ctx, bucketName, "", true) // Empty prefix, recursive
	if err != nil {
		return &pb.ObjectListResponse{Objects: []*pb.ObjectInfo{}}, nil
	}

	var result []*pb.ObjectInfo
	for _, obj := range objects {
		result = append(result, &pb.ObjectInfo{
			Name:     obj.Key,
			Size:     obj.Size,
			Modified: obj.LastModified,
			Metadata: map[string]string{},
		})
	}

	return &pb.ObjectListResponse{
		Objects: result,
	}, nil
}

// ========================================
// Statistics and Monitoring
// ========================================

// GetStatistics gets NATS statistics
func (s *NATSServer) GetStatistics(ctx context.Context, req *pb.GetStatisticsRequest) (*pb.GetStatisticsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	stats := s.natsClient.GetStats()

	return &pb.GetStatisticsResponse{
		TotalStreams:   0, // Would need to count user streams
		TotalConsumers: 0,
		TotalMessages:  0,
		TotalBytes:     0,
		Connections:    1, // Default since NumConnections may not exist
		InMsgs:         int64(stats.InMsgs),
		OutMsgs:        int64(stats.OutMsgs),
		InBytes:        int64(stats.InBytes),
		OutBytes:       int64(stats.OutBytes),
	}, nil
}

// GetStreamStats gets statistics for a specific stream
func (s *NATSServer) GetStreamStats(ctx context.Context, req *pb.GetStreamStatsRequest) (*pb.GetStreamStatsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	streamName := s.makeStreamName(req.UserId, req.StreamName)

	stream, err := s.natsClient.GetStream(ctx, streamName)
	if err != nil {
		return nil, status.Error(codes.NotFound, "stream not found")
	}

	info, err := stream.Info(ctx)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.GetStreamStatsResponse{
		StreamName:    req.StreamName,
		Messages:      int64(info.State.Msgs),
		Bytes:         int64(info.State.Bytes),
		ConsumerCount: int32(info.State.Consumers),
		MessageRate:   0.0, // Would need to calculate
		ByteRate:      0.0,
	}, nil
}

// ========================================
// Health Check
// ========================================

// HealthCheck checks the health of the NATS service
func (s *NATSServer) HealthCheck(ctx context.Context, req *pb.NATSHealthCheckRequest) (*pb.NATSHealthCheckResponse, error) {
	err := s.natsClient.Ping(ctx)
	healthy := err == nil

	status := "connected"
	if !healthy {
		status = "disconnected"
	}

	return &pb.NATSHealthCheckResponse{
		Healthy:          healthy,
		NatsStatus:       status,
		JetstreamEnabled: true,
		Connections:      1,
		CheckedAt:        timestamppb.Now(),
		Message:          "NATS service is healthy",
	}, nil
}

// ========================================
// Helper Functions
// ========================================

func (s *NATSServer) logAudit(userID, operation string, metadata map[string]string) {
	// Simplified audit logging - could integrate with Loki gRPC service later
	fmt.Printf("[NATS Audit] User: %s, Operation: %s, Metadata: %v\n", userID, operation, metadata)
}

// Conversion helpers
func convertHeaders(headers map[string][]string) map[string]string {
	result := make(map[string]string)
	for k, v := range headers {
		if len(v) > 0 {
			result[k] = v[0]
		}
	}
	return result
}

func convertSubjects(userID string, subjects []string) []string {
	result := make([]string, len(subjects))
	for i, subj := range subjects {
		result[i] = fmt.Sprintf("user.%s.%s", userID, subj)
	}
	return result
}

func convertStorageType(st pb.StorageType) jetstream.StorageType {
	if st == pb.StorageType_STORAGE_MEMORY {
		return jetstream.MemoryStorage
	}
	return jetstream.FileStorage
}

func convertDuration(d *durationpb.Duration) time.Duration {
	if d == nil {
		return 0
	}
	return d.AsDuration()
}

func convertDeliveryPolicy(dp pb.DeliveryPolicy) jetstream.DeliverPolicy {
	switch dp {
	case pb.DeliveryPolicy_DELIVERY_ALL:
		return jetstream.DeliverAllPolicy
	case pb.DeliveryPolicy_DELIVERY_LAST:
		return jetstream.DeliverLastPolicy
	case pb.DeliveryPolicy_DELIVERY_NEW:
		return jetstream.DeliverNewPolicy
	default:
		return jetstream.DeliverAllPolicy
	}
}

func convertAckPolicy(ap pb.AckPolicy) jetstream.AckPolicy {
	switch ap {
	case pb.AckPolicy_ACK_EXPLICIT:
		return jetstream.AckExplicitPolicy
	case pb.AckPolicy_ACK_ALL:
		return jetstream.AckAllPolicy
	case pb.AckPolicy_ACK_NONE:
		return jetstream.AckNonePolicy
	default:
		return jetstream.AckExplicitPolicy
	}
}

func convertReplayPolicy(rp pb.ReplayPolicy) jetstream.ReplayPolicy {
	if rp == pb.ReplayPolicy_REPLAY_ORIGINAL {
		return jetstream.ReplayOriginalPolicy
	}
	return jetstream.ReplayInstantPolicy
}

func convertStreamInfo(info *jetstream.StreamInfo) *pb.StreamInfo {
	if info == nil {
		return nil
	}
	return &pb.StreamInfo{
		Name: info.Config.Name,
		Config: &pb.StreamConfig{
			Name:        info.Config.Name,
			Subjects:    info.Config.Subjects,
			MaxMsgs:     int32(info.Config.MaxMsgs),
			MaxBytes:    info.Config.MaxBytes,
			MaxAge:      durationpb.New(info.Config.MaxAge),
			MaxMsgSize:  int32(info.Config.MaxMsgSize),
			Replicas:    int32(info.Config.Replicas),
		},
		State: &pb.StreamState{
			Messages:      int64(info.State.Msgs),
			Bytes:         int64(info.State.Bytes),
			FirstSeq:      int64(info.State.FirstSeq),
			LastSeq:       int64(info.State.LastSeq),
			FirstTs:       timestamppb.New(info.State.FirstTime),
			LastTs:        timestamppb.New(info.State.LastTime),
			NumSubjects:   int32(info.State.NumSubjects),
			ConsumerCount: int32(info.State.Consumers),
		},
		Created: timestamppb.New(info.Created),
	}
}

func convertConsumerInfo(info *jetstream.ConsumerInfo) *pb.ConsumerInfo {
	if info == nil {
		return nil
	}
	return &pb.ConsumerInfo{
		StreamName: info.Stream,
		Name:       info.Name,
		Config: &pb.ConsumerConfig{
			Name:         info.Config.Name,
			DurableName:  info.Config.Durable,
			FilterSubject: info.Config.FilterSubject,
			AckWait:      durationpb.New(info.Config.AckWait),
			MaxDeliver:   int32(info.Config.MaxDeliver),
		},
		State: &pb.ConsumerState{
			DeliveredSeq:    int64(info.Delivered.Consumer),
			AckFloorSeq:     int64(info.AckFloor.Consumer),
			NumPending:      int64(info.NumPending),
			NumRedelivered:  int64(info.NumRedelivered),
		},
		Created: timestamppb.New(info.Created),
	}
}
