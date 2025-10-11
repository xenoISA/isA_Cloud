// Redis gRPC 服务端主程序
// 提供 Redis 缓存的统一 gRPC 接口
//
// 文件名: cmd/redis-service/main.go
//
// 功能：
// - 启动 gRPC 服务器
// - 注册到 Consul
// - 提供健康检查
// - 优雅关闭
//
// 使用方法:
//
//	go run cmd/redis-service/main.go
//
// 环境变量:
//
//	GRPC_PORT - gRPC 服务端口（默认 50055）
//	REDIS_HOST - Redis 服务地址
//	CONSUL_ENABLED - 是否启用 Consul 注册
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	"github.com/hashicorp/consul/api"
	pb "github.com/isa-cloud/isa_cloud/pkg/proto/redis"
	"github.com/isa-cloud/isa_cloud/cmd/redis-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/cache"
)

const (
	serviceName = "redis-service"
	defaultPort = 50055
)

func main() {
	// 加载配置
	factory, err := cache.NewCacheClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()

	// 获取端口
	port := cfg.Redis.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	// 创建 Redis 客户端
	ctx := context.Background()
	redisClient, err := factory.NewRedisClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create Redis client: %v", err)
	}
	defer redisClient.Close()

	log.Printf("Redis client connected to %s:%d", cfg.Redis.Host, cfg.Redis.Port)

	// 创建 gRPC 服务器
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(10*1024*1024), // 10MB
		grpc.MaxSendMsgSize(10*1024*1024),
	)

	// 创建 Redis gRPC 服务实现
	redisServer, err := server.NewRedisServer(redisClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create Redis server: %v", err)
	}

	// 注册服务
	pb.RegisterRedisServiceServer(grpcServer, redisServer)

	// 注册健康检查
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)

	// 注册反射服务（用于 grpcurl 等工具）
	reflection.Register(grpcServer)

	// 启动监听
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("Redis gRPC Service listening on :%d", port)

	// 注册到 Consul
	var consulClient *api.Client
	var serviceID string
	if cfg.Consul.Enabled {
		consulClient, serviceID, err = registerConsul(cfg, port)
		if err != nil {
			log.Printf("Warning: Failed to register to Consul: %v", err)
		} else {
			log.Printf("Registered to Consul with service ID: %s", serviceID)
			defer deregisterConsul(consulClient, serviceID)
		}
	}

	// 优雅关闭
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh

		log.Println("Shutting down gracefully...")

		// 从 Consul 注销
		if consulClient != nil && serviceID != "" {
			deregisterConsul(consulClient, serviceID)
		}

		// 停止 gRPC 服务器
		grpcServer.GracefulStop()

		log.Println("Server stopped")
		os.Exit(0)
	}()

	// 启动服务
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

// registerConsul 注册服务到 Consul
func registerConsul(cfg *cache.CacheConfig, port int) (*api.Client, string, error) {
	consulConfig := api.DefaultConfig()
	consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

	client, err := api.NewClient(consulConfig)
	if err != nil {
		return nil, "", err
	}

	// 获取本机 IP
	hostname, _ := os.Hostname()

	serviceID := fmt.Sprintf("%s-%s-%d", serviceName, hostname, port)

	// 注册服务
	registration := &api.AgentServiceRegistration{
		ID:      serviceID,
		Name:    serviceName,
		Port:    port,
		Address: getLocalIP(),
		Tags:    []string{"grpc", "cache", "redis"},
		Check: &api.AgentServiceCheck{
			GRPC:                           fmt.Sprintf("%s:%d", getLocalIP(), port),
			Interval:                       "10s",
			Timeout:                        "5s",
			DeregisterCriticalServiceAfter: "30s",
		},
	}

	if err := client.Agent().ServiceRegister(registration); err != nil {
		return nil, "", err
	}

	return client, serviceID, nil
}

// deregisterConsul 从 Consul 注销服务
func deregisterConsul(client *api.Client, serviceID string) {
	if err := client.Agent().ServiceDeregister(serviceID); err != nil {
		log.Printf("Failed to deregister from Consul: %v", err)
	} else {
		log.Printf("Deregistered from Consul: %s", serviceID)
	}
}

// getLocalIP 获取本机 IP
func getLocalIP() string {
	// 简化版，实际应该更健壮
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return "localhost"
	}
	defer conn.Close()

	localAddr := conn.LocalAddr().(*net.UDPAddr)
	return localAddr.IP.String()
}


