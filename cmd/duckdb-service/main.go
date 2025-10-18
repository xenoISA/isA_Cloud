// DuckDB gRPC 服务端主程序
// 文件名: cmd/duckdb-service/main.go
package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"

	consulapi "github.com/hashicorp/consul/api"
	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip" // Register gzip compressor
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	pb "github.com/isa-cloud/isa_cloud/api/proto/duckdb"
	"github.com/isa-cloud/isa_cloud/cmd/duckdb-service/server"
	grpcclients "github.com/isa-cloud/isa_cloud/pkg/grpc/clients"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

const (
	serviceName = "duckdb-service"
	defaultPort = 50052
)

func main() {
	factory, err := storage.NewStorageClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.DuckDB.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	// Create MinIO gRPC client for database file storage
	// DuckDB service uses a service account to access MinIO on behalf of all users
	minioGRPCHost := os.Getenv("MINIO_GRPC_HOST")
	if minioGRPCHost == "" {
		minioGRPCHost = "isa-minio-grpc" // Default MinIO gRPC service name
	}
	minioGRPCPort := 50051 // Standard MinIO gRPC port

	minioClient, err := grpcclients.NewMinIOGRPCClient(&grpcclients.MinIOGRPCConfig{
		Host:   minioGRPCHost,
		Port:   minioGRPCPort,
		UserID: "duckdb-service", // Service account
	})
	if err != nil {
		log.Fatalf("Failed to create MinIO gRPC client: %v", err)
	}
	defer minioClient.Close()

	log.Printf("Connected to MinIO gRPC service at %s:%d", minioGRPCHost, minioGRPCPort)

	grpcServer := grpc.NewServer()

	// Create DuckDB server with MinIO gRPC client
	duckdbServer, err := server.NewDuckDBServer(minioClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create DuckDB server: %v", err)
	}

	pb.RegisterDuckDBServiceServer(grpcServer, duckdbServer)

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

	log.Printf("DuckDB gRPC Service listening on :%d", port)
	log.Printf("Database files will be stored in MinIO per-user buckets")

	go handleShutdown(grpcServer, consulClient, serviceID)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

// registerConsul registers the service with Consul
func registerConsul(cfg *storage.StorageConfig, port int) (*consulapi.Client, string, error) {
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
			serviceHostname = "isa-duckdb-grpc"
		} else {
			serviceHostname = hostname
		}
	}

	serviceID := fmt.Sprintf("%s-%s", serviceName, serviceHostname)

	registration := &consulapi.AgentServiceRegistration{
		ID:      serviceID,
		Name:    "duckdb-grpc-service",
		Address: serviceHostname, // 使用 Docker 网络可解析的主机名
		Port:    port,
		Tags:    []string{"grpc", "duckdb", "analytics"},
		Meta: map[string]string{
			"container_name": serviceHostname,
			"service_type":   "grpc",
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
	os.Exit(0)
}
