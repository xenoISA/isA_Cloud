// PostgreSQL gRPC 服务端主程序
// 文件名: cmd/postgres-service/main.go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	consulapi "github.com/hashicorp/consul/api"
	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip" // Register gzip compressor
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/keepalive"
	"google.golang.org/grpc/reflection"

	pb "github.com/isa-cloud/isa_cloud/api/proto/postgres"
	"github.com/isa-cloud/isa_cloud/cmd/postgres-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/postgres"
)

const (
	serviceName = "postgres-service"
	defaultPort = 50061
)

// Config 配置结构
type Config struct {
	Postgres PostgresConfig
	Consul   ConsulConfig
	GRPCPort int
}

type PostgresConfig struct {
	Host     string
	Port     int
	Database string
	User     string
	Password string
	SSLMode  string
}

type ConsulConfig struct {
	Enabled bool
	Host    string
	Port    int
}

func loadConfig() *Config {
	return &Config{
		Postgres: PostgresConfig{
			Host:     getEnv("POSTGRES_HOST", "localhost"),
			Port:     getEnvAsInt("POSTGRES_PORT", 5432),
			Database: getEnv("POSTGRES_DB", "postgres"),
			User:     getEnv("POSTGRES_USER", "postgres"),
			Password: getEnv("POSTGRES_PASSWORD", "postgres"),
			SSLMode:  getEnv("POSTGRES_SSL_MODE", "disable"),
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

	// 创建 PostgreSQL 客户端
	pgConfig := &postgres.Config{
		Host:     cfg.Postgres.Host,
		Port:     cfg.Postgres.Port,
		Database: cfg.Postgres.Database,
		User:     cfg.Postgres.User,
		Password: cfg.Postgres.Password,
		SSLMode:  cfg.Postgres.SSLMode,
	}

	pgClient, err := postgres.NewClient(ctx, pgConfig)
	if err != nil {
		log.Fatalf("Failed to create PostgreSQL client: %v", err)
	}
	defer pgClient.Close()

	log.Printf("Successfully connected to PostgreSQL at %s:%d", cfg.Postgres.Host, cfg.Postgres.Port)

	// 创建 gRPC 服务器
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(50*1024*1024), // 50MB
		grpc.MaxSendMsgSize(50*1024*1024),

		// Keepalive enforcement policy - 允许客户端的 keepalive ping
		grpc.KeepaliveEnforcementPolicy(keepalive.EnforcementPolicy{
			MinTime:             10 * time.Second, // 允许客户端最小10秒一次ping
			PermitWithoutStream: true,              // 允许无活动流时发送ping
		}),

		// Server keepalive parameters - 服务端主动检测死连接
		grpc.KeepaliveParams(keepalive.ServerParameters{
			Time:    60 * time.Second, // 服务端每60秒发送一次ping
			Timeout: 10 * time.Second, // 10秒无响应视为死连接
		}),

		// 并发限制 - 防止资源耗尽
		grpc.MaxConcurrentStreams(1000), // 最多1000个并发流

		// 连接超时 - 防止慢连接占用资源
		grpc.ConnectionTimeout(10 * time.Second),
	)

	// 创建 PostgreSQL gRPC 服务
	postgresServer := server.NewPostgresServer(pgClient, cfg.Postgres.Database)
	pb.RegisterPostgresServiceServer(grpcServer, postgresServer)

	// 注册健康检查
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)

	// 注册反射 (用于 grpcurl 等工具)
	reflection.Register(grpcServer)

	// 监听端口
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("PostgreSQL gRPC Service listening on :%d", cfg.GRPCPort)

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
	go handleShutdown(grpcServer, consulClient, serviceID, pgClient)

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

	// 获取服务主机名
	serviceHostname := os.Getenv("SERVICE_HOSTNAME")
	if serviceHostname == "" {
		serviceHostname = os.Getenv("HOSTNAME")
	}
	if serviceHostname == "" {
		hostname, err := os.Hostname()
		if err != nil {
			serviceHostname = "isa-postgres-grpc"
		} else {
			serviceHostname = hostname
		}
	}

	serviceID := fmt.Sprintf("%s-%s", serviceName, serviceHostname)

	registration := &consulapi.AgentServiceRegistration{
		ID:      serviceID,
		Name:    "postgres-grpc-service",
		Address: serviceHostname,
		Port:    cfg.GRPCPort,
		Tags:    []string{"grpc", "postgres", "database"},
		Meta: map[string]string{
			"container_name": serviceHostname,
			"service_type":   "grpc",
			"database":       cfg.Postgres.Database,
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

func handleShutdown(grpcServer *grpc.Server, consulClient *consulapi.Client, serviceID string, pgClient *postgres.Client) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	log.Println("Shutting down gracefully...")

	// 从 Consul 注销
	if consulClient != nil && serviceID != "" {
		if err := consulClient.Agent().ServiceDeregister(serviceID); err != nil {
			log.Printf("Error deregistering from Consul: %v", err)
		} else {
			log.Printf("Deregistered from Consul: %s", serviceID)
		}
	}

	// 关闭 PostgreSQL 连接
	pgClient.Close()

	// 停止 gRPC 服务器
	grpcServer.GracefulStop()
	log.Println("Server stopped")
	os.Exit(0)
}

// Helper functions
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
