// Supabase gRPC 服务端主程序
// 文件名: cmd/supabase-service/main.go
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

	pb "github.com/isa-cloud/isa_cloud/api/proto/supabase"
	"github.com/isa-cloud/isa_cloud/cmd/supabase-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/supabase"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

const (
	serviceName = "supabase-service"
	defaultPort = 50057
)

func main() {
	// 加载配置 - 优先从环境变量加载
	cfg := storage.LoadFromEnv()

	port := cfg.Supabase.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	ctx := context.Background()

	// 创建 Supabase 客户端
	supabaseClient, err := supabase.NewClientFromStorageConfig(cfg)
	if err != nil {
		log.Fatalf("Failed to create Supabase client: %v", err)
	}
	defer supabaseClient.Close()

	log.Printf("✅ Supabase client initialized: %s", cfg.Supabase.URL)

	// 健康检查
	healthy, status, err := supabaseClient.HealthCheck(ctx)
	if err != nil {
		log.Printf("⚠️  Supabase health check warning: %v", err)
	} else if healthy {
		log.Printf("✅ Supabase connection: %s", status)
	}

	// 检查 pgvector
	if supabaseClient != nil {
		pgvectorEnabled, err := supabaseClient.CheckPgVectorEnabled(ctx)
		if err != nil {
			log.Printf("⚠️  Failed to check pgvector: %v", err)
		} else if pgvectorEnabled {
			log.Printf("✅ pgvector extension: ENABLED")
		} else {
			log.Printf("⚠️  pgvector extension: DISABLED (vector operations will fail)")
		}
	}

	// 创建 gRPC Server
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(10*1024*1024), // 10 MB
		grpc.MaxSendMsgSize(10*1024*1024), // 10 MB
	)

	// 创建 Supabase Server
	supabaseServer, err := server.NewSupabaseServer(supabaseClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create Supabase server: %v", err)
	}

	// 注册 Supabase Service
	pb.RegisterSupabaseServiceServer(grpcServer, supabaseServer)

	// 注册健康检查
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)

	// 注册 reflection (用于 grpcurl 等工具)
	reflection.Register(grpcServer)

	// 注册到 Consul (如果启用)
	var consulClient *consulapi.Client
	var serviceID string
	if cfg.Consul.Enabled {
		consulClient, serviceID, err = registerConsul(cfg, port)
		if err != nil {
			log.Printf("⚠️  Warning: Failed to register with Consul: %v", err)
		} else {
			log.Printf("✅ Successfully registered with Consul as: %s", serviceID)
		}
	}

	// 启动 gRPC 服务
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("🚀 Supabase gRPC Service listening on :%d", port)

	// 优雅关闭
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
		<-sigChan

		log.Println("🛑 Shutting down Supabase gRPC Service...")

		// 从 Consul 注销
		if consulClient != nil && serviceID != "" {
			if err := consulClient.Agent().ServiceDeregister(serviceID); err != nil {
				log.Printf("Failed to deregister from Consul: %v", err)
			} else {
				log.Println("✅ Deregistered from Consul")
			}
		}

		// 关闭 gRPC 服务
		grpcServer.GracefulStop()
		log.Println("✅ Supabase gRPC Service stopped")
		os.Exit(0)
	}()

	// 启动服务
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

// registerConsul 注册服务到 Consul
func registerConsul(cfg *storage.StorageConfig, port int) (*consulapi.Client, string, error) {
	consulConfig := consulapi.DefaultConfig()
	consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

	client, err := consulapi.NewClient(consulConfig)
	if err != nil {
		return nil, "", fmt.Errorf("failed to create consul client: %w", err)
	}

	// 获取服务主机名 (优先使用环境变量，适配 Docker Compose)
	// SERVICE_HOSTNAME 应该设置为 Docker Compose 的 service name 或 container_name
	serviceHostname := os.Getenv("SERVICE_HOSTNAME")
	if serviceHostname == "" {
		// 回退到 HOSTNAME 环境变量
		serviceHostname = os.Getenv("HOSTNAME")
	}
	if serviceHostname == "" {
		// 最后回退到 os.Hostname (返回容器ID，不推荐)
		hostname, err := os.Hostname()
		if err != nil {
			serviceHostname = "localhost"
		} else {
			serviceHostname = hostname
		}
	}

	serviceID := fmt.Sprintf("%s-%s-%d", cfg.Supabase.ServiceName, serviceHostname, port)

	// 注册服务
	registration := &consulapi.AgentServiceRegistration{
		ID:      serviceID,
		Name:    cfg.Supabase.ServiceName,
		Port:    port,
		Address: serviceHostname, // 使用 Docker 网络可解析的主机名
		Tags:    []string{"grpc", "supabase", "database", "vector"},
		Meta: map[string]string{
			"container_name": serviceHostname,
			"service_type":   "grpc",
		},
		Check: &consulapi.AgentServiceCheck{
			GRPC:                           fmt.Sprintf("%s:%d", serviceHostname, port),
			Interval:                       "10s",
			Timeout:                        "5s",
			DeregisterCriticalServiceAfter: "1m",
		},
	}

	if err := client.Agent().ServiceRegister(registration); err != nil {
		return nil, "", fmt.Errorf("failed to register service: %w", err)
	}

	return client, serviceID, nil
}
