// Neo4j gRPC 服务端主程序
// 文件名: cmd/neo4j-service/main.go
package main

import (
	"context"
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/neo4j"
	"github.com/isa-cloud/isa_cloud/cmd/neo4j-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/neo4j"
)

const (
	serviceName = "neo4j-service"
	defaultPort = 50063
)

// Config 配置结构
type Config struct {
	Neo4j    Neo4jConfig
	Consul   ConsulConfig
	GRPCPort int
}

type Neo4jConfig struct {
	URI      string
	Username string
	Password string
	Database string
}

type ConsulConfig struct {
	Enabled bool
	Host    string
	Port    int
}

func loadConfig() *Config {
	return &Config{
		Neo4j: Neo4jConfig{
			URI:      getEnv("NEO4J_URI", "bolt://localhost:7687"),
			Username: getEnv("NEO4J_USERNAME", "neo4j"),
			Password: getEnv("NEO4J_PASSWORD", "password"),
			Database: getEnv("NEO4J_DATABASE", "neo4j"),
		},
		Consul: ConsulConfig{
			Enabled: getEnv("CONSUL_ENABLED", "false") == "true",
			Host:    getEnv("CONSUL_HOST", "localhost"),
			Port:    getEnvAsInt("CONSUL_PORT", 8500),
		},
		GRPCPort: getEnvAsInt("GRPC_PORT", defaultPort),
	}
}

func main() {
	cfg := loadConfig()

	ctx := context.Background()

	// 创建 Neo4j 客户端
	neo4jConfig := &neo4j.Config{
		URI:      cfg.Neo4j.URI,
		Username: cfg.Neo4j.Username,
		Password: cfg.Neo4j.Password,
		Database: cfg.Neo4j.Database,
	}

	neo4jClient, err := neo4j.NewClient(ctx, neo4jConfig)
	if err != nil {
		log.Fatalf("Failed to create Neo4j client: %v", err)
	}
	defer neo4jClient.Close(ctx)

	log.Printf("Successfully connected to Neo4j at %s", cfg.Neo4j.URI)

	// 创建 gRPC 服务器
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(50*1024*1024), // 50MB
		grpc.MaxSendMsgSize(50*1024*1024),
	)

	// 创建 Neo4j gRPC 服务
	neo4jServer := server.NewNeo4jServer(neo4jClient, cfg.Neo4j.Database)
	pb.RegisterNeo4JServiceServer(grpcServer, neo4jServer)

	// 注册健康检查
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)

	// 注册反射
	reflection.Register(grpcServer)

	// 监听端口
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("Neo4j gRPC Service listening on :%d", cfg.GRPCPort)

	// 注册到 Consul
	var consulClient *consulapi.Client
	var serviceID string
	if cfg.Consul.Enabled {
		consulClient, serviceID, err = registerConsul(cfg)
		if err != nil {
			log.Printf("Warning: Failed to register with Consul: %v", err)
		} else {
			log.Printf("Successfully registered with Consul as: %s", serviceID)
		}
	}

	// 优雅关闭处理
	go handleShutdown(grpcServer, consulClient, serviceID, neo4jClient)

	// 启动服务
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

func registerConsul(cfg *Config) (*consulapi.Client, string, error) {
	consulConfig := consulapi.DefaultConfig()
	consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

	client, err := consulapi.NewClient(consulConfig)
	if err != nil {
		return nil, "", fmt.Errorf("failed to create Consul client: %w", err)
	}

	serviceHostname := os.Getenv("SERVICE_HOSTNAME")
	if serviceHostname == "" {
		serviceHostname = os.Getenv("HOSTNAME")
	}
	if serviceHostname == "" {
		hostname, err := os.Hostname()
		if err != nil {
			serviceHostname = "isa-neo4j-grpc"
		} else {
			serviceHostname = hostname
		}
	}

	serviceID := fmt.Sprintf("%s-%s", serviceName, serviceHostname)

	registration := &consulapi.AgentServiceRegistration{
		ID:      serviceID,
		Name:    "neo4j-grpc-service",
		Address: serviceHostname,
		Port:    cfg.GRPCPort,
		Tags:    []string{"grpc", "neo4j", "graph-database"},
		Meta: map[string]string{
			"container_name": serviceHostname,
			"service_type":   "grpc",
			"database_type":  "graph",
			"database":       cfg.Neo4j.Database,
		},
		Check: &consulapi.AgentServiceCheck{
			GRPC:                           fmt.Sprintf("%s:%d/%s", serviceHostname, cfg.GRPCPort, serviceName),
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

func handleShutdown(grpcServer *grpc.Server, consulClient *consulapi.Client, serviceID string, neo4jClient *neo4j.Client) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	log.Println("Shutting down gracefully...")

	if consulClient != nil && serviceID != "" {
		if err := consulClient.Agent().ServiceDeregister(serviceID); err != nil {
			log.Printf("Error deregistering from Consul: %v", err)
		} else {
			log.Printf("Deregistered from Consul: %s", serviceID)
		}
	}

	ctx := context.Background()
	neo4jClient.Close(ctx)
	grpcServer.GracefulStop()
	log.Println("Server stopped")
	os.Exit(0)
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		var intValue int
		fmt.Sscanf(value, "%d", &intValue)
		if intValue > 0 {
			return intValue
		}
	}
	return defaultValue
}
