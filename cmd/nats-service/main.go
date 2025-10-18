// NATS gRPC 服务端主程序
// 文件名: cmd/nats-service/main.go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"

	consulapi "github.com/hashicorp/consul/api"
	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip" // Register gzip compressor
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	pb "github.com/isa-cloud/isa_cloud/api/proto/nats"
	"github.com/isa-cloud/isa_cloud/cmd/nats-service/server"
	grpcclients "github.com/isa-cloud/isa_cloud/pkg/grpc/clients"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event"
)

const (
	serviceName = "nats-service"
	defaultPort = 50056
)

func main() {
	factory, err := event.NewEventClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.NATS.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	ctx := context.Background()
	natsClient, err := factory.NewNATSClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create NATS client: %v", err)
	}
	defer natsClient.Close()

	// Discover and create MinIO gRPC Client
	minioHost, minioPort, err := discoverGRPCService(cfg, "minio-grpc-service", "localhost", 50051)
	if err != nil {
		log.Printf("Warning: Failed to discover MinIO gRPC service from Consul: %v", err)
		log.Printf("Falling back to environment variables or defaults")
		// Fallback to environment variables
		minioHost = os.Getenv("MINIO_GRPC_HOST")
		if minioHost == "" {
			minioHost = "localhost"
		}
		minioPort = 50051
		if portStr := os.Getenv("MINIO_GRPC_PORT"); portStr != "" {
			if p, err := strconv.Atoi(portStr); err == nil {
				minioPort = p
			}
		}
	}

	minioClient, err := grpcclients.NewMinIOGRPCClient(&grpcclients.MinIOGRPCConfig{
		Host:   minioHost,
		Port:   minioPort,
		UserID: "nats-service", // Service-level user ID
	})
	if err != nil {
		log.Fatalf("Failed to create MinIO gRPC client: %v", err)
	}
	defer minioClient.Close()
	log.Printf("Connected to MinIO gRPC service at %s:%d", minioHost, minioPort)

	// Discover and create Redis gRPC Client
	redisHost, redisPort, err := discoverGRPCService(cfg, "redis-grpc-service", "localhost", 50055)
	if err != nil {
		log.Printf("Warning: Failed to discover Redis gRPC service from Consul: %v", err)
		log.Printf("Falling back to environment variables or defaults")
		// Fallback to environment variables
		redisHost = os.Getenv("REDIS_GRPC_HOST")
		if redisHost == "" {
			redisHost = "localhost"
		}
		redisPort = 50055
		if portStr := os.Getenv("REDIS_GRPC_PORT"); portStr != "" {
			if p, err := strconv.Atoi(portStr); err == nil {
				redisPort = p
			}
		}
	}

	redisClient, err := grpcclients.NewRedisGRPCClient(&grpcclients.RedisGRPCConfig{
		Host:   redisHost,
		Port:   redisPort,
		UserID: "nats-service", // Service-level user ID
	})
	if err != nil {
		log.Fatalf("Failed to create Redis gRPC client: %v", err)
	}
	defer redisClient.Close()
	log.Printf("Connected to Redis gRPC service at %s:%d", redisHost, redisPort)

	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(10*1024*1024), // 10MB
		grpc.MaxSendMsgSize(10*1024*1024),
	)

	natsServer, err := server.NewNATSServer(natsClient, minioClient, redisClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create NATS server: %v", err)
	}

	pb.RegisterNATSServiceServer(grpcServer, natsServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)
	reflection.Register(grpcServer)

	// Register with Consul if enabled
	var consulClient *consulapi.Client
	var serviceID string
	if cfg.Consul.Enabled {
		consulClient, serviceID, err = registerConsul(cfg, port)
		if err != nil {
			log.Printf("Warning: Failed to register with Consul: %v", err)
		} else {
			log.Printf("Successfully registered with Consul as: %s", serviceID)
		}
	}

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("NATS gRPC Service listening on :%d", port)
	log.Printf("JetStream enabled: %v", cfg.NATS.JetStreamEnabled)

	go handleShutdown(grpcServer, consulClient, serviceID)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

// discoverGRPCService discovers a gRPC service from Consul
func discoverGRPCService(cfg *event.EventConfig, serviceName, defaultHost string, defaultPort int) (string, int, error) {
	// If Consul is not enabled, return defaults
	if !cfg.Consul.Enabled {
		return defaultHost, defaultPort, fmt.Errorf("consul not enabled")
	}

	// Create Consul client
	consulConfig := consulapi.DefaultConfig()
	consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

	client, err := consulapi.NewClient(consulConfig)
	if err != nil {
		return defaultHost, defaultPort, fmt.Errorf("failed to create Consul client: %w", err)
	}

	// Query for healthy service instances
	services, _, err := client.Health().Service(serviceName, "", true, nil)
	if err != nil {
		return defaultHost, defaultPort, fmt.Errorf("failed to query Consul: %w", err)
	}

	if len(services) == 0 {
		return defaultHost, defaultPort, fmt.Errorf("no healthy instances found for service: %s", serviceName)
	}

	// Return the first healthy instance
	instance := services[0]
	host := instance.Service.Address
	port := instance.Service.Port

	log.Printf("Discovered %s from Consul: %s:%d", serviceName, host, port)
	return host, port, nil
}

// registerConsul registers the service with Consul
func registerConsul(cfg *event.EventConfig, port int) (*consulapi.Client, string, error) {
	consulConfig := consulapi.DefaultConfig()
	consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

	client, err := consulapi.NewClient(consulConfig)
	if err != nil {
		return nil, "", fmt.Errorf("failed to create Consul client: %w", err)
	}

	// 获取服务主机名 (优先使用环境变量，适配 Docker Compose)
	serviceHostname := os.Getenv("SERVICE_HOSTNAME")
	if serviceHostname == "" {
		serviceHostname = os.Getenv("HOSTNAME")
	}
	if serviceHostname == "" {
		hostname, err := os.Hostname()
		if err != nil {
			serviceHostname = "isa-nats-grpc"
		} else {
			serviceHostname = hostname
		}
	}

	serviceID := fmt.Sprintf("%s-%s", serviceName, serviceHostname)

	registration := &consulapi.AgentServiceRegistration{
		ID:      serviceID,
		Name:    "nats-grpc-service",
		Address: serviceHostname, // 使用 Docker 网络可解析的主机名
		Port:    port,
		Tags:    []string{"grpc", "nats", "messaging", "eventbus"},
		Meta: map[string]string{
			"container_name": serviceHostname,
			"service_type":   "grpc",
			"jetstream":      "enabled",
		},
		Check: &consulapi.AgentServiceCheck{
			GRPC:                           fmt.Sprintf("%s:%d/%s", serviceHostname, port, serviceName),
			Interval:                       "10s",
			Timeout:                        "5s",
			DeregisterCriticalServiceAfter: "30s",
		},
	}

	err = client.Agent().ServiceRegister(registration)
	if err != nil {
		return nil, "", fmt.Errorf("failed to register service: %w", err)
	}

	return client, serviceID, nil
}

// handleShutdown handles graceful shutdown
func handleShutdown(grpcServer *grpc.Server, consulClient *consulapi.Client, serviceID string) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	log.Println("Shutting down gracefully...")

	// Deregister from Consul
	if consulClient != nil && serviceID != "" {
		if err := consulClient.Agent().ServiceDeregister(serviceID); err != nil {
			log.Printf("Error deregistering from Consul: %v", err)
		} else {
			log.Printf("Successfully deregistered from Consul: %s", serviceID)
		}
	}

	grpcServer.GracefulStop()
	log.Println("Server stopped")
	os.Exit(0)
}
